# -*- coding: utf-8 -*-
"""
青龙签到通用重放框架

作用
    Surge/Loon 的 akino 模块在用户点签到时，把原始请求（url/method/headers/body）
    存成一份 JSON。本框架把这份 JSON 读出来，在青龙上原样重放，从而脱离手机。

    本质是「HTTP 请求重放器」，不做任何 token 刷新——token 由外部抓包提供。

环境变量
    每个站点一个，值为 akino 抓包产出的 JSON 数组；同时兼容：
      - 单个 JSON 对象（单账号）
      - && 分隔的多段 JSON 或纯 cookie 文本（多账号手填）

    示例：
      CHECKIN_MYLINK=[{"url":"https://mylink.komect.com/v1/api/eas/sign/sign_in",
                       "method":"post","headers":{"cookie":"token=xxx"},"body":""}]

依赖
    requests。通知复用仓库根目录 sendNotify.py，导入失败降级为控制台输出。
"""

from __future__ import annotations

import json
import os
import re
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import requests
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# sendNotify.py 的位置随青龙的拉库方式而变：
#   本地开发  -> 仓库根/checkin/replay.py，通知在 仓库根/sendNotify.py（上 1 级）
#   青龙拉库  -> /ql/scripts/byhooi_qinglong/checkin/replay.py，通知在 /ql/scripts/sendNotify.py（上 3 级）
# 所以不写死层级，从当前文件逐级向上找，找到为止。
_NOTIFY_DIR = Path(__file__).resolve().parent
for _ in range(4):
    if (_NOTIFY_DIR / "sendNotify.py").exists():
        break
    _NOTIFY_DIR = _NOTIFY_DIR.parent

if str(_NOTIFY_DIR) not in sys.path:
    sys.path.insert(0, str(_NOTIFY_DIR))

try:
    from sendNotify import send as _notify
except Exception as _exc:  # 通知不可用不应影响签到本身
    _notify = None
    _NOTIFY_ERROR = str(_exc)


# 重放前丢弃的请求头：由 requests 重新生成，沿用原值会导致长度不符等问题
DROP_HEADERS = {
    "content-length",
    "host",
    "connection",
    "accept-encoding",
    "transfer-encoding",
    "proxy-connection",
}

# 抓包数据缺失时的兜底请求头，与 akino 模块内置 UA 保持一致
DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
        "AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "zh-CN,zh;q=0.9",
}

# 通用成功码，各站点可用 SiteConfig.success_codes 覆盖
SUCCESS_CODES = {0, 200, "0", "200", "true", "True", "success", "ok"}

CODE_KEYS = (
    "code",
    "errno",
    "errCode",
    "errcode",
    "ret",
    "retcode",
    "status",
    "resultCode",
)
MESSAGE_KEYS = (
    "msg",
    "message",
    "errmsg",
    "errMsg",
    "info",
    "desc",
    "error",
    "reason",
    "resultMsg",
    "resultMessage",
    "errormsg",
)

REQUEST_TIMEOUT = 15


@dataclass
class Account:
    """一个待重放的账号请求"""

    account_name: str = ""
    url: str = ""
    method: str = "POST"
    headers: dict[str, str] = field(default_factory=dict)
    body: Any = ""
    cookie: str = ""
    proxy: str = ""


@dataclass
class AccountResult:
    """单个账号的重放结果"""

    success: bool
    message: str
    status_code: int = 0


@dataclass
class SiteConfig:
    """站点配置"""

    key: str
    name: str
    env_names: tuple[str, ...]
    default_url: str = ""
    default_method: str = "POST"
    default_headers: dict[str, str] = field(default_factory=dict)
    success_codes: set | None = None
    success_keywords: tuple[str, ...] = ()
    fail_keywords: tuple[str, ...] = ()
    cron: str = ""
    note: str = ""
    enabled: bool = True


def shorten(text: Any, limit: int = 160) -> str:
    """压缩空白并截断，便于日志与通知展示"""
    if text is None:
        return ""
    if isinstance(text, (dict, list)):
        text = json.dumps(text, ensure_ascii=False)
    elif not isinstance(text, str):
        text = str(text)
    text = re.sub(r"\s+", " ", text).strip()
    return text if len(text) <= limit else text[:limit] + "..."


def normalize_body(body: Any) -> Any:
    """统一请求体形态：dict/list 转 JSON 字符串，bytes 解码"""
    if body is None:
        return ""
    if isinstance(body, (dict, list)):
        return json.dumps(body, ensure_ascii=False)
    if isinstance(body, bytes):
        return body.decode("utf-8", "ignore")
    return body


def normalize_headers(raw: Any) -> dict[str, str]:
    """把 akino 存下来的 headers 转成干净字典"""
    if not raw:
        return {}
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except json.JSONDecodeError:
            print(f"headers 不是合法 JSON，已忽略: {shorten(raw, 80)}")
            return {}
    if not isinstance(raw, dict):
        return {}

    cleaned: dict[str, str] = {}
    for key, value in raw.items():
        if not isinstance(key, str) or key.lower() in DROP_HEADERS:
            continue
        cleaned[key] = value if isinstance(value, str) else str(value)
    return cleaned


def parse_account(item: Any, index: int, site: SiteConfig) -> Account | None:
    """解析单个账号：dict 走 akino 格式，str 当纯 cookie 文本"""
    if isinstance(item, dict):
        return Account(
            account_name=str(item.get("account_name") or item.get("name") or f"账号{index + 1}"),
            url=str(item.get("url") or site.default_url),
            method=str(item.get("method") or site.default_method).upper(),
            headers=normalize_headers(item.get("headers") or item.get("header")),
            body=normalize_body(item.get("body")),
            cookie=str(item.get("cookie") or ""),
            proxy=str(item.get("proxy") or ""),
        )

    if isinstance(item, str):
        text = item.strip()
        if not text:
            return None
        return Account(
            account_name=f"账号{index + 1}",
            url=site.default_url,
            method=site.default_method.upper(),
            cookie=text,
        )

    print(f"第 {index + 1} 个账号格式无法识别，已跳过")
    return None


def load_accounts(site: SiteConfig) -> tuple[list[Account], str]:
    """按候选环境变量名依次查找，返回 (账号列表, 命中的变量名)"""
    raw_value = ""
    used_env = ""
    for env_name in site.env_names:
        value = (os.getenv(env_name) or "").strip()
        if value:
            raw_value = value
            used_env = env_name
            break

    if not raw_value:
        print(f"未获取到环境变量，请配置 {' 或 '.join(site.env_names)} 之一")
        return [], ""

    print(f"使用环境变量: {used_env}")

    try:
        data = json.loads(raw_value)
    except json.JSONDecodeError:
        print("环境变量不是合法 JSON，将按 cookie 文本解析")
        data = None

    if data is not None:
        items = data if isinstance(data, list) else [data]
    else:
        # && 分隔的多账号，每段优先按 JSON 解析，失败则当 cookie
        items = []
        for segment in re.split(r"\s*&&\s*", raw_value):
            segment = segment.strip()
            if not segment:
                continue
            try:
                items.append(json.loads(segment))
            except json.JSONDecodeError:
                items.append(segment)

    accounts: list[Account] = []
    for index, item in enumerate(items):
        account = parse_account(item, index, site)
        if account:
            accounts.append(account)
    return accounts, used_env


def build_headers(account: Account, site: SiteConfig) -> dict[str, str]:
    """合并默认头、站点头、账号头；cookie 单独拼接避免大小写重复"""
    merged = dict(DEFAULT_HEADERS)
    merged.update(site.default_headers)
    merged.update(account.headers)

    cookie = account.cookie.strip()
    if cookie:
        existing = ""
        for key in list(merged):
            if key.lower() == "cookie":
                existing = merged.pop(key)
                break
        merged["Cookie"] = f"{existing}; {cookie}" if existing else cookie
    return merged


def prepare_request(
    account: Account, site: SiteConfig
) -> tuple[str, str, dict[str, str], dict[str, Any]]:
    """构造 requests 的调用参数"""
    method = (account.method or site.default_method).upper()
    url = account.url or site.default_url
    headers = build_headers(account, site)
    kwargs: dict[str, Any] = {}

    body = account.body
    if method in ("GET", "HEAD"):
        if body:
            print("GET/HEAD 请求不支持 body，已忽略")
        return method, url, headers, kwargs

    if body not in ("", None):
        has_content_type = any(key.lower() == "content-type" for key in headers)
        if not has_content_type:
            stripped = str(body).strip()
            if stripped.startswith(("{", "[")):
                headers["Content-Type"] = "application/json;charset=UTF-8"
            else:
                headers["Content-Type"] = "application/x-www-form-urlencoded"
        kwargs["data"] = body

    return method, url, headers, kwargs


def find_field(payload: Any, keys: tuple[str, ...], depth: int = 0) -> Any:
    """在响应 JSON 里按常见字段名取值，最多下钻 3 层"""
    if depth > 3 or not isinstance(payload, (dict, list)):
        return None
    if isinstance(payload, list):
        for item in payload:
            found = find_field(item, keys, depth + 1)
            if found is not None:
                return found
        return None

    for key in keys:
        if key in payload:
            return payload[key]

    for value in payload.values():
        if isinstance(value, (dict, list)):
            found = find_field(value, keys, depth + 1)
            if found is not None:
                return found
    return None


def judge_result(status_code: int, payload: Any, text: str, site: SiteConfig) -> tuple[bool, str]:
    """判定签到是否成功，返回 (是否成功, 说明)"""
    message = shorten(find_field(payload, MESSAGE_KEYS) or "")

    if status_code >= 400:
        return False, f"HTTP {status_code} {message}".strip()

    haystack = f"{message} {text}"
    for keyword in site.fail_keywords:
        if keyword in haystack:
            return False, message or f"命中失败关键字: {keyword}"

    for keyword in site.success_keywords:
        if keyword in haystack:
            return True, message or f"命中成功关键字: {keyword}"

    code = find_field(payload, CODE_KEYS)
    if code is not None:
        allowed = site.success_codes if site.success_codes is not None else SUCCESS_CODES
        try:
            matched = code in allowed
        except TypeError:  # code 是 dict/list 时不可哈希
            matched = False
        return (True, message or f"返回码 {code}") if matched else (False, message or f"返回码 {code}")

    if 200 <= status_code < 400:
        return True, message or f"HTTP {status_code}（响应无可判定字段）"
    return False, message or f"HTTP {status_code}"


def replay(account: Account, site: SiteConfig) -> AccountResult:
    """执行一次重放"""
    if not (account.url or site.default_url):
        return AccountResult(False, "缺少签到地址")

    method, url, headers, kwargs = prepare_request(account, site)
    proxies = {"http": account.proxy, "https": account.proxy} if account.proxy else None

    print(f"请求: {method} {url}")
    if account.proxy:
        print(f"代理: {account.proxy}")

    try:
        response = requests.request(
            method,
            url,
            headers=headers,
            timeout=REQUEST_TIMEOUT,
            proxies=proxies,
            verify=False,
            **kwargs,
        )
    except requests.RequestException as exc:
        return AccountResult(False, f"请求失败: {shorten(exc)}")

    text = response.text or ""
    print(f"响应: HTTP {response.status_code} {shorten(text, 200)}")

    try:
        payload = response.json()
    except ValueError:
        payload = None

    success, message = judge_result(response.status_code, payload, text, site)
    return AccountResult(success, message, response.status_code)


def process_account(account: Account, site: SiteConfig, index: int) -> AccountResult:
    """处理单个账号，异常不外抛，避免影响其他账号"""
    label = account.account_name or f"账号{index + 1}"
    print("-" * 50)
    print(f"[{site.name}] {label}")

    try:
        result = replay(account, site)
    except Exception as exc:  # noqa: BLE001 - 单账号兜底
        result = AccountResult(False, f"执行异常: {shorten(exc)}")

    print(f"结果: {'成功' if result.success else '失败'} - {result.message}")
    return result


def build_notification(
    site: SiteConfig, results: list[AccountResult], duration: float
) -> tuple[str, str]:
    """汇总成通知标题与正文"""
    total = len(results)
    success = sum(1 for item in results if item.success)
    failed = total - success

    if total == 0:
        title = f"{site.name}未执行"
    elif failed == 0:
        title = f"{site.name}成功"
    elif success == 0:
        title = f"{site.name}失败"
    else:
        title = f"{site.name}部分成功"

    lines = [
        f"账号数: {total}",
        f"成功: {success}",
        f"失败: {failed}",
        f"耗时: {duration:.1f} 秒",
        "",
    ]
    for index, item in enumerate(results, start=1):
        flag = "成功" if item.success else "失败"
        lines.append(f"[{index}] {flag} - {item.message}")

    return title, "\n".join(lines)


def run_site(site: SiteConfig) -> int:
    """跑完一个站点，返回退出码：0 全部正常或无配置，1 存在失败"""
    print("=" * 50)
    print(f"{site.name} | 环境变量: {' / '.join(site.env_names)}")
    if site.note:
        print(f"备注: {site.note}")

    if not site.enabled:
        print("该站点当前停用，跳过")
        return 0

    start_time = time.time()
    accounts, _ = load_accounts(site)
    if not accounts:
        print("没有可用的账号配置，结束")
        return 0

    print(f"当前共 {len(accounts)} 个账号")
    results = [process_account(account, site, index) for index, account in enumerate(accounts)]
    duration = time.time() - start_time

    title, content = build_notification(site, results, duration)
    print("=" * 50)
    print(title)
    print(content)

    if _notify:
        try:
            _notify(title, content)
        except Exception as exc:  # noqa: BLE001 - 通知失败不影响结果
            print(f"通知发送失败: {shorten(exc)}")
    else:
        print(f"未加载 sendNotify.py（{_NOTIFY_ERROR}），跳过推送")

    return 0 if all(item.success for item in results) else 1
