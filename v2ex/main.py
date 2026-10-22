"""
new Env('V2EX 每日签到');
cron: 15 8 * * *
version: v2.0.0
updated: 2026-10-22
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

3. 调试: V2EX_DEBUG=1
   打印签到相关页面的原文摘要，用于排查「签到未生效」的真实原因。

判定原则: 只有签到页回读确认「今日奖励已领取」，才算成功。
领取请求发了但没确认到账，一律按失败上报 —— 宁可误报失败，也不要谎报成功。

版本变更:
  v2.0.0 (2026-10-22) 修复谎报成功与入口误匹配，见 v2ex/HANDOFF.md
  v1.x                旧版，success 恒为 True 且会把 /signout 当签到入口
"""

VERSION = "2.0.0"
UPDATED = "2026-10-22"

import json
import os
import random
import re
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlparse

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


def env_flag(name: str) -> bool:
    """解析环境变量开关。

    注意不能用 bool(os.getenv(...)): 字符串 "0" / "false" / "no" 在 Python 里
    都是真值, 那样设成 0 反而关不掉, 只能靠删变量。
    """
    return os.getenv(name, "").strip().lower() in ("1", "true", "yes", "on")


DEBUG = env_flag("V2EX_DEBUG")
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
    # 显式只声明 gzip/deflate，避免服务端返回 br/zstd 而容器缺解码库导致乱码。
    # 抓包里浏览器发的是 gzip, deflate, br, zstd，这里故意收窄。
    "Accept-Encoding": "gzip, deflate",
    "Upgrade-Insecure-Requests": "1",
    # 补齐抓包里的 sec-ch-ua / Sec-Fetch-*，让请求更像一次真实的页面导航
    "sec-ch-ua": '"Microsoft Edge";v="155", "Chromium";v="155", "Not(A:Brand";v="24"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"Windows"',
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "same-origin",
    "Sec-Fetch-User": "?1",
}

# ---- 页面判定关键词 ----
# 只在「今日已领取」时出现的文案。宁可窄也不能宽:
# 「已连续登录」未签到时同样存在，「已领取」这类半截文案容易撞到别的任务。
CLAIMED_MARKERS = (
    "每日登录奖励已领取",
    "今日的登录奖励已领取",
    "daily login reward has been claimed",
)
# 领取成功后 V2EX 会直接给出这句
CLAIM_SUCCESS_MARKERS = (
    "已成功领取每日登录奖励",
    "每日登录奖励已领取",
)
# V2EX 偶发要求再点一次才真正入账
RECLICK_MARKERS = ("请重新点击一次以领取每日登录奖励",)
LOGIN_MARKERS = ("你要查看的页面需要先登录", "you need to sign in first")

# once 值不一定是纯数字，按 [A-Za-z0-9_%.-] 收。
# 必须带完整路径：真实页面里还有 /signout?once= 和 /settings/night/toggle?once=，
# 用宽松的 once=\d+ 会抓到登出/夜间模式的 token。
REDEEM_PATTERN = re.compile(r"/mission/daily/redeem\?once=[A-Za-z0-9_%.-]+")
# 余额区真实结构 (HAR 确认):
#   <div id="money"><a href="/balance" class="balance_area" style="">1 <img alt="G" /> 93 ...</a></div>
# 类名挂在 <a> 上且没有 bigger；旧版是 <div class="balance_area bigger">，两种都收。
BALANCE_AREA_PATTERN = re.compile(
    r'class="[^"]*\bbalance_area\b[^"]*"[^>]*>(.*?)</(?:a|div)>',
    re.S,
)
STREAK_PATTERN = re.compile(r"已连续登录\s*(\d+)\s*天")
# 每日奖励文案: 「已成功领取每日登录奖励 8 铜币」/「20261022 的每日登录奖励 8 铜币」
REWARD_PATTERNS = (
    re.compile(r"已成功领取每日登录奖励\s*(\d+(?:\.\d+)?)\s*铜币"),
    re.compile(r"每日登录奖励\s*(\d+(?:\.\d+)?)\s*铜币"),
    re.compile(r"\d{8}\s*的每日登录奖励\s*(\d+(?:\.\d+)?)\s*铜币"),
)


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


@dataclass
class DailyState:
    """每日任务页面的解析结果。"""

    requires_login: bool
    already_claimed: bool
    redeem_path: str
    streak_days: str
    text: str


def normalize_text(text: str) -> str:
    """压缩 HTML 文本里的空白字符，便于通知展示。"""
    return re.sub(r"\s+", " ", text).strip()


def strip_tags(html: str) -> str:
    text = re.sub(r"<[^>]+>", " ", html)
    return normalize_text(text)


def excerpt(text: str, limit: int = 300) -> str:
    """截取页面摘要用于日志排查，避免刷屏。"""
    return normalize_text(text)[:limit]


def parse_cookie(cookie_text: str) -> dict[str, str]:
    """按 ; 手工拆分 cookie。

    不用 SimpleCookie: 它会改写 / 丢弃含非法字符的值, 而 V2EX 的 A2 可能带
    = % + 等字符, 一旦解析错位, 表现就是「登录态丢失」。
    """
    cookies: dict[str, str] = {}
    for chunk in re.split(r"[;\r\n]+", cookie_text):
        name, separator, value = chunk.strip().partition("=")
        name = name.strip()
        if not separator or not name:
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        cookies[name] = value
    return cookies


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


class BalanceParser(HTMLParser):
    """提取页面可见文本。"""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.text_parts: list[str] = []

    def handle_data(self, data: str) -> None:
        text = normalize_text(data)
        if text:
            self.text_parts.append(text)


def parse_page(html: str) -> BalanceParser:
    parser = BalanceParser()
    try:
        parser.feed(html)
        parser.close()
    except Exception:
        # 页面残缺也不该让整个账号挂掉，退回正则版文本
        parser.text_parts.append(strip_tags(html))
    return parser


def page_text(html: str) -> str:
    return " ".join(parse_page(html).text_parts)


def extract_reward(*texts: str) -> str:
    """从领取页 / 余额页提取当日铜币奖励。"""
    combined = " ".join(texts)
    for pattern in REWARD_PATTERNS:
        matched = pattern.search(combined)
        if matched:
            return f"{matched.group(1)} 铜币"
    return ""


def extract_balance(html: str) -> str:
    """从 balance_area 解析 金/银/铜。

    真实结构 (2026-10 抓包确认):
        <div id="money"><a href="/balance" class="balance_area" style="">
        1 <img ... alt="G" /> 93 <img ... alt="S" /> 84 <img ... alt="B" /></a></div>

    注意余额区是 <a> 而不是 <div>，类名只有 balance_area、没有 bigger，
    所以按「class 含 balance_area 的标签」取整段，再从里面按序取数字。
    只认恰好 3 个数字：少一项时无法判断是哪一种币为 0，宁可不显示也不要标错。
    """
    matched = BALANCE_AREA_PATTERN.search(html)
    if not matched:
        return ""
    # 先剥标签再取数字：img 的 height="16"、src 里的 @2x 都带数字，
    # 直接对原始片段 findall 会把它们一起算进来
    inner_text = strip_tags(matched.group(1))
    numbers = [value for value in re.findall(r"\d+", inner_text) if len(value) <= 12]
    if len(numbers) != 3:
        return ""
    golden, silver, bronze = numbers
    return f"{golden} 金币，{silver} 银币，{bronze} 铜币"


class V2EXClient:
    def __init__(self, account: Account):
        self.account = account
        self.session = requests.Session()
        self.session.headers.update(DEFAULT_HEADERS)

        if account.proxy:
            self.session.proxies.update({"http": account.proxy, "https": account.proxy})

        self.session.cookies.update(parse_cookie(account.cookie))

    def request(self, method: str, path: str, check: bool = True, **kwargs) -> requests.Response:
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

    def inspect_daily(self, html: str, url: str) -> DailyState:
        """解析 /mission/daily: 是否需登录、是否已领取、领取入口、连续天数。"""
        text = strip_tags(html)
        lowered = text.lower()
        requires_login = urlparse(url).path.rstrip("/") == "/signin" or any(
            marker in lowered for marker in LOGIN_MARKERS
        )
        already_claimed = any(marker in lowered for marker in CLAIMED_MARKERS)

        matched = REDEEM_PATTERN.search(html)
        redeem_path = matched.group(0).replace("&amp;", "&") if matched else ""

        streak = STREAK_PATTERN.search(text)
        return DailyState(
            requires_login=requires_login,
            already_claimed=already_claimed,
            redeem_path=redeem_path,
            streak_days=streak.group(1) if streak else "",
            text=text,
        )

    def get_daily_state(self) -> tuple[DailyState, str]:
        response = self.request("GET", "/mission/daily", allow_redirects=True)
        return self.inspect_daily(response.text, response.url), response.text

    def get_balance(self) -> tuple[str, str]:
        """拉取 /balance 页面拿到(今日收益, 余额)。失败不影响签到结果。"""
        try:
            response = self.request("GET", "/balance", allow_redirects=True)
        except requests.RequestException as exc:
            print(f"获取余额失败: {exc}")
            return "", ""
        if "/signin" in response.url:
            print("获取余额被重定向到登录页")
            return "", ""
        return extract_reward(page_text(response.text)), extract_balance(response.text)

    def redeem(self, redeem_path: str) -> tuple[int, str, str]:
        """发起领取，返回 (状态码, 最终 URL, 结果页文本)。

        跟随跳转: V2EX 领取成功会 302 到 /mission/daily，结果页里就是
        「每日登录奖励已领取」，比只看状态码可靠。
        被踢回登录页时最终 URL 会落到 /signin。
        """
        # 硬防护: 只允许打签到入口。历史 bug 曾把页面里的
        # location.href='/signout?once=...' 当成签到链接，等于每次任务都在登出账号。
        if not REDEEM_PATTERN.fullmatch(redeem_path):
            print(f"拒绝请求非签到入口的 URL: {redeem_path}")
            return 0, "", ""

        response = self.request(
            "GET",
            redeem_path,
            allow_redirects=True,
            check=False,
            headers={"Referer": f"{BASE_URL}/mission/daily"},
        )
        return response.status_code, response.url, strip_tags(response.text)

    def build_success_result(
        self,
        message: str,
        username: str,
        daily_html: str,
        claim_texts: tuple[str, ...] = (),
        streak_days: str = "",
    ) -> AccountResult:
        """汇总成功结果。

        daily 页本身就带余额区（HAR 确认 id="money" 里的 balance_area），
        优先就地解析；解析不到再去 /balance 补一次，避免白跑请求。
        """
        daily_text = page_text(daily_html)
        today = extract_reward(*claim_texts, daily_text)
        balance = extract_balance(daily_html)
        if not balance:
            today_from_balance, balance = self.get_balance()
            today = today or today_from_balance
        return AccountResult(
            account_name=self.account.account_name,
            success=True,
            message=message,
            username=username or self.account.account_name,
            today=today,
            balance=balance,
            days=f"已连续登录 {streak_days} 天" if streak_days else "",
        )

    def sign(self) -> AccountResult:
        state, daily_html = self.get_daily_state()

        # 未登录会被重定向到 /signin?next=...
        if state.requires_login:
            return AccountResult(
                account_name=self.account.account_name,
                success=False,
                message="Cookie 已失效或未登录，请重新抓取 V2EX Cookie",
            )

        username = self.get_username(daily_html)

        if state.already_claimed:
            print("页面显示今日奖励已领取，无需重复领取")
            return self.build_success_result(
                "今日已签到",
                username,
                daily_html,
                streak_days=state.streak_days,
            )

        if not state.redeem_path:
            return AccountResult(
                account_name=self.account.account_name,
                success=False,
                message="未找到签到入口，可能页面结构变化或 Cookie 权限不足",
                username=username or self.account.account_name,
            )

        print(f"发现签到入口: {state.redeem_path}")

        # V2EX 偶尔要求「再点一次」才真正入账，最多补一次
        claim_texts: list[str] = []
        redeem_path = state.redeem_path
        for attempt in range(1, 3):
            status_code, final_url, claim_text = self.redeem(redeem_path)
            print(f"第 {attempt} 次领取: HTTP {status_code}，落到 {final_url}")
            if DEBUG:
                print(f"领取结果页摘要: {excerpt(claim_text)}")

            if status_code == 0:
                # redeem() 的硬防护拦截了非签到入口 URL
                return AccountResult(
                    account_name=self.account.account_name,
                    success=False,
                    message="签到入口校验未通过，已阻止请求，请反馈此问题",
                    username=username or self.account.account_name,
                )
            if "/signin" in urlparse(final_url).path:
                return AccountResult(
                    account_name=self.account.account_name,
                    success=False,
                    message="签到被重定向到登录页，Cookie 可能已失效",
                )
            if status_code >= 400:
                return AccountResult(
                    account_name=self.account.account_name,
                    success=False,
                    message=f"签到请求失败，HTTP {status_code}",
                    username=username or self.account.account_name,
                )

            claim_texts.append(claim_text)
            if not any(marker in claim_text for marker in RECLICK_MARKERS):
                break
            if attempt == 2:
                # 已经补过一次仍要求重试，不再重复发请求，交给下面的回读判定
                print("补领取后站点仍要求重新点击，停止重试")
                break

            print("站点要求重新点击一次，刷新页面后重试")
            refreshed, _ = self.get_daily_state()
            if refreshed.already_claimed or not refreshed.redeem_path:
                break
            redeem_path = refreshed.redeem_path

        # 回读签到页确认是否真的到账
        verify_state, verify_html = self.get_daily_state()
        confirmed = any(
            marker in text for text in claim_texts for marker in CLAIM_SUCCESS_MARKERS
        ) or verify_state.already_claimed

        if verify_state.requires_login:
            return AccountResult(
                account_name=self.account.account_name,
                success=False,
                message="签到后登录态失效，请重新抓取 V2EX Cookie",
            )

        if not confirmed:
            # 这条分支就是「页面报成功、网站没签到」的真正原因：不谎报
            reason = "页面仍显示可以领取" if verify_state.redeem_path else "页面未出现已领取文案"
            advice = "领取未生效" if verify_state.redeem_path else "无法确认领取状态"
            print(f"签到未确认：{reason}")
            if DEBUG:
                print(f"签到后页面摘要: {excerpt(verify_state.text)}")
            return AccountResult(
                account_name=self.account.account_name,
                success=False,
                message=f"{advice}（{reason}），请手动核对或稍后重试",
                username=username or self.account.account_name,
            )

        print("已确认今日奖励到账")
        return self.build_success_result(
            "签到成功",
            username,
            verify_html,
            claim_texts=tuple(claim_texts),
            streak_days=verify_state.streak_days,
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
    # 版本号放在推送里，方便确认青龙上跑的是哪一版
    content_parts.append(f"脚本版本: v{VERSION} ({UPDATED})")
    return title, "\n\n".join(content_parts)


def main() -> None:
    start_time = datetime.now()
    print("=" * 50)
    print("V2EX 每日签到脚本")
    print(f"版本: v{VERSION} ({UPDATED})")
    print(f"调试模式: {'开启' if DEBUG else '关闭'}")
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
