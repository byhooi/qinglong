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
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
}


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

    def request(self, method: str, path: str, **kwargs: Any) -> requests.Response:
        url = path if path.startswith("http") else f"{BASE_URL}{path}"
        response = self.session.request(method, url, timeout=20, verify=False, **kwargs)
        response.raise_for_status()
        return response

    def get_username(self, html: str) -> str:
        patterns = [
            r'<a href="/member/[^"]+" class="top">([^<]+)</a>',
            r'<a href="/member/[^"]+">([^<]+)</a>',
        ]
        for pattern in patterns:
            matched = re.search(pattern, html)
            if matched:
                return normalize_text(matched.group(1))
        return ""

    def get_daily_url(self, html: str) -> str:
        patterns = [
            r"location\.href\s*=\s*'([^']+)'",
            r'location\.href\s*=\s*"([^"]+)"',
            r'href="(/mission/daily/redeem\?once=\d+)"',
        ]
        for pattern in patterns:
            matched = re.search(pattern, html)
            if matched:
                return matched.group(1)
        return ""

    def parse_balance(self, html: str) -> tuple[str, str]:
        total = re.findall(
            r'<td class="d" style="text-align: right;">\s*([\d.]+)\s*</td>',
            html,
        )
        today = re.findall(r'<td class="d"><span class="gray">(.*?)</span></td>', html)
        balance = total[0] if total else ""
        today_text = strip_tags(today[0]) if today else ""
        return today_text, balance

    def parse_days(self, html: str) -> str:
        for cell_html in re.findall(r'<div class="cell">(.*?)</div>', html, flags=re.S):
            text = strip_tags(cell_html)
            if "已连续登录" in text or "连续登录" in text:
                return text
        return ""

    def sign(self) -> AccountResult:
        daily_response = self.request("GET", "/mission/daily")
        daily_html = daily_response.text
        username = self.get_username(daily_html)

        if not username and ("/signin" in daily_response.url or "登录" in daily_html):
            return AccountResult(
                account_name=self.account.account_name,
                success=False,
                message="Cookie 可能已失效，请重新抓取 V2EX Cookie",
            )

        daily_url = self.get_daily_url(daily_html)
        signed_message = "今日已签到"

        if daily_url and daily_url != "/balance":
            redeem_response = self.request(
                "GET",
                daily_url,
                headers={"Referer": f"{BASE_URL}/mission/daily", **DEFAULT_HEADERS},
            )
            if redeem_response.status_code == 200:
                signed_message = "签到请求已提交"
        elif not daily_url:
            signed_message = "未找到签到入口，可能已签到或页面结构变化"

        balance_response = self.request("GET", "/balance")
        balance_html = balance_response.text
        username = username or self.get_username(balance_html) or self.account.account_name
        today, balance = self.parse_balance(balance_html)

        daily_response = self.request("GET", "/mission/daily")
        days = self.parse_days(daily_response.text)

        success = bool(today or balance or days)
        message = signed_message if success else "签到结果解析失败，请检查 Cookie 或页面结构"
        return AccountResult(
            account_name=self.account.account_name,
            success=success,
            message=message,
            username=username,
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
