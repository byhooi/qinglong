"""
new Env('什么值得买签到');
cron: 10 8 * * *
"""

"""
什么值得买签到脚本

环境变量:
1. 推荐: smzdm (JSON)
   {
     "accounts": [
       {"account_name": "账号1", "cookie": "...", "sk": ""}
     ]
   }
2. 兼容: SMZDM_COOKIE (多账号用 & 或 \n 分隔), SMZDM_SK (可选)

说明:
- 如未安装 pycryptodome，脚本不会自动生成 sk，建议配置 SMZDM_SK。
"""

import base64
import hashlib
import json
import os
import random
import re
import string
import sys
import time
from dataclasses import dataclass
from pathlib import Path

import requests
import urllib3

try:
    from Crypto.Cipher import DES
    from Crypto.Util.Padding import pad
except ModuleNotFoundError:
    DES = None
    pad = None

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

CURRENT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = CURRENT_DIR.parent
sys.path.insert(0, str(PROJECT_ROOT))

try:
    from sendNotify import send
except Exception:
    def send(title: str, content: str) -> None:
        print(f"\n{title}\n{content}")


BASE = "https://user-api.smzdm.com"
APP_VERSION = "10.4.1"
SIGN_KEY = "apr1$AwP!wRRT$gJ/q.X24poeBInlUJC"
USER_AGENT = f"smzdm_android_V{APP_VERSION} rv:841 (MI 8;Android10;zh)smzdmapp"
DES_KEY = b"geZm53XAspb02exN"[:8]
TIMEOUT = 15
RETRIES = 3
PUSH_KEYWORDS = ("签到成功", "签到失败", "失败", "奖励", "金币", "碎银")


@dataclass
class Account:
    account_name: str
    cookie: str
    sk: str = ""


def random_string(length: int = 32) -> str:
    return "".join(random.choices(string.ascii_letters + string.digits, k=length))


def remove_tags(html: str) -> str:
    return re.sub(r"<[^>]+>", "", str(html or "")).strip()


def parse_cookie_field(cookie: str, name: str) -> str:
    match = re.search(rf"{name}=([^;]*)", cookie or "")
    return match.group(1) if match else ""


def sleep_random(min_sec: float = 1, max_sec: float = 5) -> None:
    time.sleep(random.uniform(min_sec, max_sec))


def generate_sk(cookie: str) -> str:
    if DES is None or pad is None:
        print("未安装 pycryptodome，无法自动生成 sk；将使用环境变量 SMZDM_SK 或默认值 1")
        return ""

    user_id = parse_cookie_field(cookie, "smzdm_id")
    if not user_id:
        return ""
    device_id = parse_cookie_field(cookie, "device_id") or random_string()
    try:
        cipher = DES.new(DES_KEY, DES.MODE_ECB)
        encrypted = cipher.encrypt(pad((user_id + device_id).encode("utf-8"), DES.block_size))
        return base64.b64encode(encrypted).decode("utf-8")
    except Exception as exc:
        print(f"生成 sk 失败: {exc}")
        return ""


def sign_form_data(data: dict | None = None) -> dict:
    payload = {
        "weixin": 1,
        "basic_v": 0,
        "f": "android",
        "v": APP_VERSION,
        "time": str(round(time.time() * 1000)),
        **(data or {}),
    }
    keys = sorted(key for key, value in payload.items() if value != "")
    sign_parts = []
    for key in keys:
        value = re.sub(r"\s+", "", str(payload[key]))
        sign_parts.append(f"{key}={value}")
    sign_text = "&".join(sign_parts)
    payload["sign"] = hashlib.md5(f"{sign_text}&key={SIGN_KEY}".encode("utf-8")).hexdigest().upper()
    return payload


def load_accounts() -> list[Account]:
    raw = os.getenv("smzdm", "").strip()
    if raw:
        try:
            config = json.loads(raw)
            items = config.get("accounts", []) if isinstance(config, dict) else []
            accounts = []
            for index, item in enumerate(items):
                if not isinstance(item, dict):
                    continue
                cookie = str(item.get("cookie", "")).strip()
                if not cookie:
                    continue
                accounts.append(Account(
                    account_name=str(item.get("account_name") or f"账号{index + 1}"),
                    cookie=cookie,
                    sk=str(item.get("sk", "")).strip(),
                ))
            if accounts:
                return accounts
        except json.JSONDecodeError as exc:
            print(f"smzdm 环境变量 JSON 解析失败: {exc}")

    cookie_env = os.getenv("SMZDM_COOKIE", "").strip()
    if not cookie_env:
        return []
    cookies = cookie_env.split("\n") if "\n" in cookie_env else cookie_env.split("&")
    cookies = [c.strip() for c in cookies if c.strip()]

    sk_env = os.getenv("SMZDM_SK", "").strip()
    sks = []
    if sk_env:
        sks = sk_env.split("\n") if "\n" in sk_env else sk_env.split("&")
        sks = [s.strip() for s in sks]

    return [
        Account(account_name=f"账号{i + 1}", cookie=cookie, sk=sks[i] if i < len(sks) else "")
        for i, cookie in enumerate(cookies)
    ]


def do_request(session: requests.Session, method: str, url: str, headers: dict,
               data: dict | None = None, retries: int = RETRIES) -> dict:
    last_error = ""
    for attempt in range(retries):
        try:
            response = session.request(method.upper(), url, headers=headers,
                                       data=sign_form_data(data), timeout=TIMEOUT, verify=False)
            try:
                payload = response.json()
            except ValueError:
                payload = {}
            success = str(payload.get("error_code", "")) == "0"
            return {"success": success, "data": payload, "response": response.text}
        except requests.RequestException as exc:
            last_error = str(exc)
            if attempt < retries - 1:
                sleep_random(1, 3)
    return {"success": False, "data": {}, "response": last_error}


class SmzdmCheckin:
    def __init__(self, cookie: str, sk: str = "") -> None:
        self.cookie = cookie.strip()
        self.token = parse_cookie_field(self.cookie, "sess")
        self.sk = (sk or generate_sk(cookie) or "1").strip()
        self.session = requests.Session()

    def headers(self) -> dict:
        return {"User-Agent": USER_AGENT, "Cookie": self.cookie, "Accept": "application/json"}

    def request(self, path: str, data: dict | None = None) -> dict:
        return do_request(self.session, "POST", BASE + path, self.headers(), data)

    def run(self) -> str:
        return self.checkin() + self.all_reward() + self.extra_reward()

    def checkin(self) -> str:
        result = self.request("/checkin", {
            "touchstone_event": "", "sk": self.sk, "token": self.token, "captcha": "",
        })
        if not result["success"]:
            msg = f"⭐签到失败: {result['response'][:200]}"
            print(msg)
            return msg + "\n"

        info = result["data"].get("data", {})
        msg = (
            f"⭐签到成功{info.get('daily_num', '?')}天\n"
            f"🏅金币: {info.get('cgold', '?')}\n"
            f"🏅碎银: {info.get('pre_re_silver', '?')}\n"
            f"🏅补签卡: {info.get('cards', '?')}"
        )

        sleep_random(3, 6)
        vip = self.vip_info().get("vip", {})
        if vip:
            msg += (
                f"\n🏅经验: {vip.get('exp_current', '?')}"
                f"\n🏅值会员等级: {vip.get('exp_level', '?')}"
                f"\n🏅值会员经验: {vip.get('exp_current_level', '?')}"
                f"\n🏅值会员有效期至: {vip.get('exp_level_expire', '?')}"
            )
        print(msg)
        return msg + "\n\n"

    def all_reward(self) -> str:
        result = self.request("/checkin/all_reward")
        if not result["success"]:
            if str(result["data"].get("error_code", "")) != "4":
                print(f"查询奖励失败: {result['response'][:200]}")
            return ""

        normal = result["data"].get("data", {}).get("normal_reward", {})
        reward_add = normal.get("reward_add", {}) or {}
        gift = normal.get("gift", {}) or {}

        line1 = f"{reward_add.get('title', '')}: {reward_add.get('content', '')}".strip(": ")
        line2 = (f"{gift['title']}: {gift.get('content_str', '')}"
                 if gift.get("title") else str(gift.get("sub_content", "")))
        text = "\n".join(filter(None, [line1, line2]))
        if text:
            print(text)
            return text + "\n\n"
        return ""

    def extra_reward(self) -> str:
        if not self.is_continue_checkin():
            msg = "今天没有额外奖励"
            print(msg)
            return msg + "\n"

        sleep_random(5, 10)
        result = self.request("/checkin/extra_reward")
        if not result["success"]:
            print(f"领取额外奖励失败: {result['response'][:200]}")
            return ""
        info = result["data"].get("data", {})
        msg = f"{info.get('title', '额外奖励')}: {remove_tags((info.get('gift') or {}).get('content', ''))}"
        print(msg)
        return msg + "\n"

    def is_continue_checkin(self) -> bool:
        result = self.request("/checkin/show_view_v2")
        if not result["success"]:
            print(f"查询额外奖励状态失败: {result['response'][:200]}")
            return False
        rows = result["data"].get("data", {}).get("rows", []) or []
        target = next((row for row in rows if str(row.get("cell_type")) == "18001"), None)
        if not target:
            return False
        return bool((target.get("cell_data") or {}).get("checkin_continue", {}).get("continue_checkin_reward_show"))

    def vip_info(self) -> dict:
        result = self.request("/vip", {"token": self.token})
        if result["success"]:
            return result["data"].get("data", {}) or {}
        print(f"查询会员信息失败: {result['response'][:200]}")
        return {}


def main() -> None:
    accounts = load_accounts()
    if not accounts:
        print("未配置 smzdm 或 SMZDM_COOKIE 环境变量")
        return

    full_log: list[str] = []
    for index, account in enumerate(accounts):
        if index > 0:
            sleep_random(10, 20)
        header = f"\n****** {account.account_name} ******"
        print(header)
        try:
            full_log.append(header + "\n" + SmzdmCheckin(account.cookie, account.sk).run())
        except Exception as exc:
            err = f"❌ {account.account_name} 异常: {exc}"
            print(err)
            full_log.append(err)

    push = "\n".join(full_log)
    filtered = "\n".join(line for line in push.splitlines() if any(k in line for k in PUSH_KEYWORDS))
    send("什么值得买签到", filtered or push)


if __name__ == "__main__":
    main()
