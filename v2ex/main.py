"""
new Env('V2EX 每日签到');
cron: 15 8 * * *
"""

"""
V2EX 每日签到脚本

青龙环境变量:
1. 推荐: v2ex
   JSON 格式:
   {
     "accounts": [
       {
         "account_name": "账号1",
         "cookie": "A2=xxx; PB3_SESSION=xxx; V2EX_LANG=zhcn",
         "proxy": ""
       }
     ]
   }

2. 兼容: V2EX_COOKIE / v2ex_cookie
   多账号可用换行或 & 分隔 cookie。
"""

import json
import os
import random
import re
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from http.cookies import SimpleCookie
from pathlib import Path
from typing import Any

import requests
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

CURRENT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = CURRENT_DIR.parent
sys.path.insert(0, str(PROJECT_ROOT))

try:
    from sendNotify import send
except Exception:
    def send(title: str, content: str) -> None:
        print(f"\n{title}\n{content}")


BASE_URL = "https://www.v2ex.com"
ENV_NAMES = ("v2ex", "V2EX_COOKIE", "v2ex_cookie")
DEFAULT_HEADERS = {
    # 与浏览器抓包一致 (Edge 155 / Win10)
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/155.0.0.0 Safari/537.36 Edg/155.0.0.0"
    ),
    "Accept": (
        "text/html,application/xhtml+xml,application/xml;q=0.9,"
        "image/avif,image/webp,image/apng,*/*;q=0.8"
    ),
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    # 显式只声明 gzip/deflate，避免服务端返回 br 而容器缺少 brotli 导致乱码
    "Accept-Encoding": "gzip, deflate",
    "Upgrade-Insecure-Requests": "1",
}

# 页面出现这些文案即认为今日签到已完成 (兼容新旧版页面)
# 注意不能把「已连续登录」放进来: 未签到时该文案同样存在
SIGNED_KEYWORDS = ("已领取", "已签到", "已经领取", "签到过", "今日登录奖励已发放")


@dataclass
class Account:
    account_name: str
    cookie: str
    proxy: str = ""


@dataclass
class AccountResult:
    account_name: str
    success: bool
    message: str
    username: str = ""
    today: str = ""
    balance: str = ""
    days: str = ""


def normalize_text(text: str) -> str:
    """压缩 HTML 文本里的空白字符，便于通知展示。"""
    return re.sub(r"\s+", " ", text).strip()


def strip_tags(html: str) -> str:
    text = re.sub(r"<[^>]+>", " ", html)
    return normalize_text(text)


def parse_cookie(cookie_text: str) -> dict[str, str]:
    parsed = SimpleCookie()
    parsed.load(cookie_text)
    return {key: value.value for key, value in parsed.items()}


def split_cookie_accounts(cookie_text: str) -> list[str]:
    if "\n" in cookie_text:
        parts = cookie_text.splitlines()
    else:
        parts = cookie_text.split("&")
    return [part.strip() for part in parts if part.strip()]


def load_accounts() -> list[Account]:
    env_name = next((name for name in ENV_NAMES if os.getenv(name)), "")
    if not env_name:
        print(f"未获取到环境变量，请配置 {', '.join(ENV_NAMES)} 之一")
        return []

    raw_value = os.getenv(env_name, "").strip()
    accounts: list[Account] = []

    if env_name == "v2ex":
        try:
            config = json.loads(raw_value)
        except json.JSONDecodeError:
            config = None

        if isinstance(config, dict):
            raw_accounts = config.get("accounts", [])
            if isinstance(raw_accounts, list):
                for index, item in enumerate(raw_accounts, start=1):
                    if not isinstance(item, dict):
                        continue
                    cookie = str(item.get("cookie", "")).strip()
                    if not cookie:
                        continue
                    accounts.append(
                        Account(
                            account_name=str(item.get("account_name") or f"账号{index}"),
                            cookie=cookie,
                            proxy=str(item.get("proxy", "")).strip(),
                        )
                    )
        elif isinstance(config, list):
            for index, item in enumerate(config, start=1):
                if isinstance(item, dict):
                    cookie = str(item.get("cookie", "")).strip()
                    proxy = str(item.get("proxy", "")).strip()
                    account_name = str(item.get("account_name") or f"账号{index}")
                else:
                    cookie = str(item).strip()
                    proxy = ""
                    account_name = f"账号{index}"
                if cookie:
                    accounts.append(Account(account_name=account_name, cookie=cookie, proxy=proxy))
        else:
            for index, cookie in enumerate(split_cookie_accounts(raw_value), start=1):
                accounts.append(Account(account_name=f"账号{index}", cookie=cookie))
    else:
        for index, cookie in enumerate(split_cookie_accounts(raw_value), start=1):
            accounts.append(Account(account_name=f"账号{index}", cookie=cookie))

    return accounts


class V2EXClient:
    def __init__(self, account: Account):
        self.account = account
        self.session = requests.Session()
        self.session.headers.update(DEFAULT_HEADERS)

        if account.proxy:
            self.session.proxies.update({"http": account.proxy, "https": account.proxy})

        self.session.cookies.update(parse_cookie(account.cookie))

    def request(self, method: str, path: str, check: bool = True, **kwargs: Any) -> requests.Response:
        url = path if path.startswith("http") else f"{BASE_URL}{path}"
        response = self.session.request(method, url, timeout=20, verify=False, **kwargs)
        if check:
            response.raise_for_status()
        return response

    def get_username(self, html: str) -> str:
        patterns = [
            r'<a href="/member/[^"]+" class="top">([^<]+)</a>',
            r'<a href="/member/[^"]+"[^>]*class="[^"]*top[^"]*"[^>]*>([^<]+)</a>',
            r'<a href="/member/[^"]+">([^<]+)</a>',
        ]
        for pattern in patterns:
            matched = re.search(pattern, html)
            if matched:
                return normalize_text(matched.group(1))
        return ""

    def get_daily_url(self, html: str) -> str:
        # 页面里是一条内联 onclick: location.href = '/mission/daily/redeem?once=xxx'
        patterns = [
            r"""(/mission/daily/redeem\?once=\d+)""",
            r"location\.href\s*=\s*'([^']+)'",
            r'location\.href\s*=\s*"([^"]+)"',
        ]
        for pattern in patterns:
            matched = re.search(pattern, html)
            if matched:
                return matched.group(1)
        return ""

    def is_signed(self, html: str) -> bool:
        """页面出现「已领取/已签到」等文案，说明今日奖励已到账。"""
        text = strip_tags(html)
        return any(keyword in text for keyword in SIGNED_KEYWORDS)

    def parse_balance(self, html: str) -> tuple[str, str]:
        """从 /balance 解析(今日收益, 铜币余额)，解析不到返回空串。

        /balance 是登录后页面：未登录会 302 到 /signin?next=/balance。
        V2EX 改版过几次表单结构，这里按「标签 -> 可见文案」逐级放宽。
        """
        text = strip_tags(html)

        balance = ""
        for pattern in (
            r"铜币余额[^0-9]{0,10}(\d+)",
            r"当前铜币[^0-9]{0,10}(\d+)",
            r"余额[^0-9]{0,10}(\d+)",
        ):
            matched = re.search(pattern, text)
            if matched:
                balance = matched.group(1)
                break

        if not balance:
            # 旧版结构: <td class="d" style="text-align: right;">1234</td>
            matched = re.search(
                r'<td[^>]*class="[^"]*\bd\b[^"]*"[^>]*>\s*([\d.]+)\s*</td>',
                html,
            )
            if matched:
                balance = matched.group(1)

        today = ""
        matched = re.search(r"(?:今日|本日)[^0-9]{0,12}\+?\s*(\d+)", text)
        if matched:
            today = matched.group(1)

        return today, balance

    def parse_daily_summary(self, html: str) -> tuple[str, str]:
        """从 /mission/daily 提取(今日奖励, 连续登录)，解析不到返回空串。"""
        text = strip_tags(html)

        today = ""
        matched = re.search(r"(?:每日|今日)登录奖励[^。；]{0,20}?(\d+)\s*个?\s*铜币", text)
        if matched:
            today = f"{matched.group(1)} 铜币"

        days = ""
        matched = re.search(r"(?:已连续登录|连续登录)\s*(\d+)\s*天", text)
        if matched:
            days = f"已连续登录 {matched.group(1)} 天"
        elif "已连续登录" in text:
            days = "已连续登录"

        return today, days

    def get_balance(self) -> tuple[str, str]:
        """拉取 /balance 页面拿到(今日收益, 铜币余额)。

        /balance 未登录会 302 到 /signin，所以它同时也是登录态的第二道校验。
        这里失败不抛异常：签到结果不以余额解析为准。
        """
        try:
            response = self.request("GET", "/balance", allow_redirects=True)
        except requests.RequestException as exc:
            print(f"获取余额失败: {exc}")
            return "", ""
        if "/signin" in response.url:
            print("获取余额被重定向到登录页")
            return "", ""
        return self.parse_balance(response.text)

    def sign(self) -> AccountResult:
        daily_response = self.request("GET", "/mission/daily", allow_redirects=True)
        daily_html = daily_response.text

        # 未登录会被重定向到 /signin?next=...，比匹配页面里的「登录」字样可靠
        if "/signin" in daily_response.url:
            return AccountResult(
                account_name=self.account.account_name,
                success=False,
                message="Cookie 已失效或未登录，请重新抓取 V2EX Cookie",
            )

        username = self.get_username(daily_html)
        daily_url = self.get_daily_url(daily_html)

        if not daily_url:
            if self.is_signed(daily_html):
                today, days = self.parse_daily_summary(daily_html)
                _, balance = self.get_balance()
                return AccountResult(
                    account_name=self.account.account_name,
                    success=True,
                    message="今日已签到",
                    username=username or self.account.account_name,
                    today=today,
                    balance=balance,
                    days=days,
                )
            return AccountResult(
                account_name=self.account.account_name,
                success=False,
                message="未找到签到入口，可能页面结构变化或 Cookie 权限不足",
                username=username or self.account.account_name,
            )

        # 抓包显示 redeem 正常返回 302 -> /mission/daily，因此不跟随跳转、也不要求 200
        redeem_response = self.request(
            "GET",
            daily_url,
            allow_redirects=False,
            check=False,
            headers={"Referer": f"{BASE_URL}/mission/daily"},
        )
        location = redeem_response.headers.get("location", "")
        if "/signin" in location:
            return AccountResult(
                account_name=self.account.account_name,
                success=False,
                message="签到被重定向到登录页，Cookie 可能已失效",
            )
        if redeem_response.status_code >= 400:
            return AccountResult(
                account_name=self.account.account_name,
                success=False,
                message=f"签到请求失败，HTTP {redeem_response.status_code}",
                username=username or self.account.account_name,
            )

        # 回读签到页确认是否真的到账
        verify_response = self.request("GET", "/mission/daily", allow_redirects=True)
        verify_html = verify_response.text
        verified = self.is_signed(verify_html) and not self.get_daily_url(verify_html)
        message = "签到成功" if verified else "签到请求已提交，但未能确认到账，请手动核对"

        today, days = self.parse_daily_summary(verify_html)
        today_from_balance, balance = self.get_balance()
        today = today or today_from_balance

        return AccountResult(
            account_name=self.account.account_name,
            success=True,
            message=message,
            username=username or self.get_username(verify_html) or self.account.account_name,
            today=today,
            balance=balance,
            days=days,
        )


def process_account(account: Account) -> AccountResult:
    print("=" * 50)
    print(f"账号: {account.account_name}")
    print("=" * 50)

    if not account.cookie:
        print("Cookie 为空，跳过")
        return AccountResult(account.account_name, False, "Cookie 为空")

    try:
        result = V2EXClient(account).sign()
    except requests.RequestException as exc:
        result = AccountResult(account.account_name, False, f"请求失败: {exc}")
    except Exception as exc:
        result = AccountResult(account.account_name, False, f"执行异常: {exc}")

    print(result.message)
    if result.username:
        print(f"用户: {result.username}")
    if result.today:
        print(f"今日: {result.today}")
    if result.balance:
        print(f"余额: {result.balance}")
    if result.days:
        print(f"连续签到: {result.days}")
    return result


def build_notification(results: list[AccountResult], start_time: datetime, end_time: datetime) -> tuple[str, str]:
    total_count = len(results)
    success_count = sum(1 for result in results if result.success)
    failed_count = total_count - success_count
    duration = int((end_time - start_time).total_seconds())

    if total_count == 0:
        title = "V2EX 签到未执行"
    elif failed_count == 0:
        title = "V2EX 签到成功"
    elif success_count == 0:
        title = "V2EX 签到失败"
    else:
        title = "V2EX 签到部分成功"

    content_parts = []
    for result in results:
        status = "成功" if result.success else "失败"
        name = result.username or result.account_name
        lines = [f"[{status}] {name}: {result.message}"]
        if result.today:
            lines.append(f"今日奖励: {result.today}")
        if result.balance:
            lines.append(f"账户余额: {result.balance}")
        if result.days:
            lines.append(f"连续签到: {result.days}")
        content_parts.append("\n".join(lines))

    content_parts.append(f"\n账号数: {total_count}，成功: {success_count}，失败: {failed_count}")
    content_parts.append(f"耗时: {duration} 秒")
    return title, "\n\n".join(content_parts)


def main() -> None:
    start_time = datetime.now()
    print("=" * 50)
    print("V2EX 每日签到脚本")
    print(f"开始时间: {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 50)

    accounts = load_accounts()
    results: list[AccountResult] = []

    if accounts:
        print(f"共获取到 {len(accounts)} 个账号")

        for index, account in enumerate(accounts):
            results.append(process_account(account))
            if index < len(accounts) - 1:
                wait_seconds = random.randint(2, 5)
                print(f"等待 {wait_seconds} 秒后处理下一个账号...")
                time.sleep(wait_seconds)

    end_time = datetime.now()
    print("=" * 50)
    print("执行完成")
    print(f"结束时间: {end_time.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"执行耗时: {int((end_time - start_time).total_seconds())} 秒")
    print("=" * 50)

    try:
        title, content = build_notification(results, start_time, end_time)
        send(title, content)
        print("推送通知发送完成")
    except Exception as exc:
        print(f"推送通知发送失败: {exc}")


if __name__ == "__main__":
    main()
