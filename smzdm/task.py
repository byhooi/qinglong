"""
new Env('什么值得买每日任务');
cron: 20 14 * * *
"""

"""
什么值得买每日任务脚本

环境变量:
1. 推荐: smzdm (JSON)
   {"accounts":[{"account_name":"账号1","cookie":"..."}]}
2. 兼容: SMZDM_COOKIE，多账号用 & 或换行分隔。

可选开关:
- SMZDM_COMMENT: 设置后才执行评论任务，评论后会尝试删除。
- SMZDM_CROWD_SILVER_5=yes: 免费抽奖不可用时，允许 5 碎银抽奖。
- SMZDM_CROWD_KEYWORD: 5 碎银抽奖奖品关键词。
"""

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


APP_VERSION = "10.4.26"
APP_VERSION_REV = "866"
SIGN_KEY = "apr1$AwP!wRRT$gJ/q.X24poeBInlUJC"
TIMEOUT = 15
RETRIES = 2
PUSH_KEYWORDS = ("成功", "失败", "奖励", "领取", "异常", "完成", "跳过")
USER_AGENT_APP = (
    f"smzdm_android_V{APP_VERSION} rv:{APP_VERSION_REV} "
    "(Redmi Note 3;Android10.0;zh)smzdmapp"
)
USER_AGENT_WEB = (
    "Mozilla/5.0 (Linux; Android 10.0; Redmi Build/Redmi Note 3; wv) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/95.0.4638.74 "
    f"Mobile Safari/537.36 smzdm_android_V{APP_VERSION} rv:{APP_VERSION_REV} "
    "(Redmi;Android10.0;zh) jsbv_1.0.0 webv_2.0 smzdmapp"
)


@dataclass
class Account:
    account_name: str
    cookie: str


def random_string(length: int = 18, chars: str = string.digits) -> str:
    return "".join(random.choice(chars) for _ in range(length))


def remove_tags(html: str) -> str:
    return re.sub(r"<[^>]+>", "", str(html or "")).strip()


def parse_json(text: str) -> dict:
    try:
        return json.loads(text)
    except (TypeError, ValueError):
        return {}


def parse_cookie_field(cookie: str, name: str) -> str:
    match = re.search(rf"{name}=([^;]*)", cookie or "")
    return match.group(1) if match else ""


def update_cookie(cookie: str, name: str, value: str) -> str:
    pattern = re.compile(rf"(^|;\s*){re.escape(name)}=[^;]*", re.I)
    if pattern.search(cookie):
        return pattern.sub(rf"\1{name}={value}", cookie)
    return f"{cookie.rstrip(';')}; {name}={value}"


def sleep_random(min_sec: float = 1, max_sec: float = 5) -> None:
    delay = random.uniform(min_sec, max_sec)
    print(f"等待 {delay:.1f} 秒")
    time.sleep(delay)


def load_accounts() -> list[Account]:
    raw = os.getenv("smzdm", "").strip()
    if raw:
        try:
            config = json.loads(raw)
            items = config.get("accounts", []) if isinstance(config, dict) else []
            accounts = []
            for index, item in enumerate(items, start=1):
                if not isinstance(item, dict):
                    continue
                cookie = str(item.get("cookie", "")).strip()
                if cookie:
                    accounts.append(Account(str(item.get("account_name") or f"账号{index}"), cookie))
            if accounts:
                return accounts
        except json.JSONDecodeError as exc:
            print(f"smzdm 环境变量 JSON 解析失败: {exc}")

    cookie_env = os.getenv("SMZDM_COOKIE", "").strip()
    if not cookie_env:
        return []
    cookies = cookie_env.split("\n") if "\n" in cookie_env else cookie_env.split("&")
    return [Account(f"账号{i + 1}", cookie.strip()) for i, cookie in enumerate(cookies) if cookie.strip()]


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


def request_api(
    session: requests.Session,
    url: str,
    *,
    method: str = "get",
    headers: dict | None = None,
    data: dict | None = None,
    sign: bool = True,
    parse_response_json: bool = True,
) -> dict:
    payload = sign_form_data(data) if sign else (data or {})
    last_error: Any = ""
    for attempt in range(RETRIES):
        try:
            if method.lower() == "post":
                response = session.post(url, headers=headers, data=payload, timeout=TIMEOUT, verify=False)
            else:
                response = session.get(url, headers=headers, params=payload, timeout=TIMEOUT, verify=False)

            if not parse_response_json:
                return {"success": True, "data": response.text, "response": response.text}

            body = parse_json(response.text)
            return {
                "success": str(body.get("error_code", "")) == "0",
                "data": body,
                "response": response.text,
            }
        except requests.RequestException as exc:
            last_error = exc
            if attempt < RETRIES - 1:
                sleep_random(1, 3)
    return {"success": False, "data": {}, "response": str(last_error)}


class SmzdmTask:
    def __init__(self, cookie: str) -> None:
        self.cookie = cookie.strip()
        self.token = parse_cookie_field(self.cookie, "sess")
        self.android_cookie = self.normalize_cookie(self.cookie)
        self.session = requests.Session()

    def normalize_cookie(self, cookie: str) -> str:
        result = cookie.replace("iphone", "android").replace("iPhone", "Android")
        updates = {
            "smzdm_version": APP_VERSION,
            "device_smzdm_version": APP_VERSION,
            "v": APP_VERSION,
            "device_smzdm_version_code": APP_VERSION_REV,
            "device_system_version": "10.0",
            "apk_partner_name": "smzdm_download",
            "partner_name": "smzdm_download",
            "device_type": "Android",
            "device_smzdm": "android",
            "device_name": "Android",
        }
        for key, value in updates.items():
            result = update_cookie(result, key, value)
        return result

    def headers(self) -> dict:
        return {
            "Accept": "*/*",
            "Accept-Language": "zh-Hans-CN;q=1",
            "Accept-Encoding": "gzip",
            "request_key": random_string(18),
            "User-Agent": os.getenv("SMZDM_USER_AGENT_APP", USER_AGENT_APP),
            "Cookie": self.android_cookie,
        }

    def web_headers(self) -> dict:
        return {
            "Accept": "*/*",
            "Accept-Language": "zh-CN,zh-Hans;q=0.9",
            "Accept-Encoding": "gzip",
            "User-Agent": os.getenv("SMZDM_USER_AGENT_WEB", USER_AGENT_WEB),
            "Cookie": self.android_cookie,
        }

    def run(self) -> str:
        print("获取任务列表")
        tasks, _ = self.get_task_list()
        sleep_random(5, 10)

        notify_msg = self.do_tasks(tasks) if tasks else "无可执行任务\n"

        print("查询限时累计活动阶段奖励")
        sleep_random(5, 10)
        _, detail = self.get_task_list()
        cell = detail.get("cell_data", {}) or {}
        if str(cell.get("activity_reward_status", "")) == "1":
            print("有奖励，领取奖励")
            sleep_random(5, 10)
            ok = self.receive_activity(cell)
            notify_msg += ("🟢" if ok else "❌") + f"限时累计活动阶段奖励领取{'成功' if ok else '失败'}\n"
        else:
            print("无活动奖励")

        return notify_msg or "无可执行任务\n"

    def do_tasks(self, tasks: list[dict]) -> str:
        notify_msg = ""
        for task in tasks:
            task_id = task.get("task_id")
            name = task.get("task_name", "未知任务")
            status = str(task.get("task_status", ""))
            event_type = task.get("task_event_type", "")

            if not task_id:
                continue
            if status == "3":
                print(f"领取[{name}]奖励")
                ok, _ = self.receive_reward(task_id)
                notify_msg += self.task_notify(ok, name, "领取")
                sleep_random(5, 15)
            elif status == "2":
                ok = self.dispatch_task(task, event_type)
                if ok is not None:
                    notify_msg += self.task_notify(ok, name, "完成")
                sleep_random(5, 15)
            else:
                notify_msg += f"⏭️{name}: 跳过，状态 {status}\n"
        return notify_msg

    def dispatch_task(self, task: dict, event_type: str) -> bool | None:
        if event_type == "interactive.view.article":
            return self.do_view_task(task)
        if event_type == "interactive.share":
            return self.do_share_task(task)
        if event_type == "guide.crowd":
            return self.do_crowd_task(task)
        if event_type == "interactive.follow.user":
            return self.do_follow_user_task(task)
        if event_type == "interactive.follow.tag":
            return self.do_follow_tag_task(task)
        if event_type == "interactive.follow.brand":
            return self.do_follow_brand_task(task)
        if event_type == "interactive.favorite":
            return self.do_favorite_task(task)
        if event_type == "interactive.rating":
            return self.do_rating_task(task)
        if event_type == "interactive.comment":
            if os.getenv("SMZDM_COMMENT", "").strip():
                return self.do_comment_task(task)
            print("请设置 SMZDM_COMMENT 环境变量后再执行评论任务")
            return None
        print(f"暂不支持任务类型: {event_type}")
        return False

    def task_notify(self, success: bool, task_name: str, action: str) -> str:
        return f"{'🟢' if success else '❌'}{action}[{task_name}]任务{'成功' if success else '失败，请查看日志'}\n"

    def get_task_list(self) -> tuple[list[dict], dict]:
        result = request_api(
            self.session,
            "https://user-api.smzdm.com/task/list_v2",
            method="post",
            headers=self.headers(),
        )
        if not result["success"]:
            print(f"任务列表获取失败: {result['response'][:300]}")
            return [], {}

        rows = result["data"].get("data", {}).get("rows", []) or []
        if not rows:
            return [], {}
        first = rows[0] or {}
        default_list = ((first.get("cell_data") or {}).get("activity_task") or {}).get("default_list_v2", []) or []
        tasks: list[dict] = []
        for group in default_list:
            tasks.extend(group.get("task_list", []) or [])
        return tasks, first

    def receive_activity(self, activity: dict) -> bool:
        print(f"领取奖励: {activity.get('activity_name', '活动')}")
        result = request_api(
            self.session,
            "https://user-api.smzdm.com/task/activity_receive",
            method="post",
            headers=self.headers(),
            data={"activity_id": activity.get("activity_id", "")},
        )
        if result["success"]:
            print(remove_tags(result["data"].get("data", {}).get("reward_msg", "")))
            return True
        print(f"领取活动奖励失败: {result['response'][:300]}")
        return False

    def receive_reward(self, task_id: str) -> tuple[bool, str]:
        robot_token = self.get_robot_token()
        if not robot_token:
            return False, "获取 robot_token 失败"
        result = request_api(
            self.session,
            "https://user-api.smzdm.com/task/activity_task_receive",
            method="post",
            headers=self.headers(),
            data={
                "robot_token": robot_token,
                "geetest_seccode": "",
                "geetest_validate": "",
                "geetest_challenge": "",
                "captcha": "",
                "task_id": task_id,
            },
        )
        if result["success"]:
            msg = remove_tags(result["data"].get("data", {}).get("reward_msg", "完成"))
            print(msg)
            return True, msg
        print(f"领取任务奖励失败: {result['response'][:300]}")
        return False, "领取任务奖励失败"

    def get_robot_token(self) -> str:
        result = request_api(
            self.session,
            "https://user-api.smzdm.com/robot/token",
            method="post",
            headers=self.headers(),
        )
        if result["success"]:
            return (result["data"].get("data") or {}).get("token", "")
        print(f"Robot Token 获取失败: {result['response'][:300]}")
        return ""

    def do_view_task(self, task: dict) -> bool:
        print(f"开始任务: {task.get('task_name')}")
        articles = self.get_task_articles(task)
        if not articles:
            return False

        is_read = bool((task.get("task_redirect_url") or {}).get("link_val", "")) or str(task.get("article_id")) == "0"
        for index, article in enumerate(articles, start=1):
            print(f"开始阅读第 {index} 篇文章")
            if is_read:
                self.open_article(task, article)
            sleep_random(20, 50)
            result = request_api(
                self.session,
                "https://user-api.smzdm.com/task/event_view_article_sync",
                method="post",
                headers=self.headers(),
                data={
                    "article_id": article.get("article_id"),
                    "channel_id": article.get("article_channel_id"),
                    "task_id": task.get("task_id"),
                },
            )
            print("完成阅读成功" if result["success"] else f"完成阅读失败: {result['response'][:200]}")
            sleep_random(5, 15)

        print("领取奖励")
        sleep_random(3, 10)
        ok, _ = self.receive_reward(task.get("task_id", ""))
        return ok

    def do_share_task(self, task: dict) -> bool:
        print(f"开始任务: {task.get('task_name')}")
        articles = self.get_task_articles(task)
        if not articles:
            return False

        for index, article in enumerate(articles, start=1):
            print(f"开始分享第 {index} 篇文章")
            if (task.get("task_redirect_url") or {}).get("link_type") != "other":
                self.open_article(task, article)
                sleep_random(8, 20)
            self.share_article_done(article.get("article_id"), article.get("article_channel_id"))
            self.share_daily_reward(article.get("article_channel_id"))
            self.share_callback(article.get("article_id"), article.get("article_channel_id"))
            sleep_random(5, 15)

        print("领取奖励")
        sleep_random(3, 10)
        ok, _ = self.receive_reward(task.get("task_id", ""))
        return ok

    def do_favorite_task(self, task: dict) -> bool:
        print(f"开始任务: {task.get('task_name')}")
        article = self.resolve_article_from_task(task)
        if not article:
            return False
        article_id = article.get("article_id")
        channel_id = article.get("article_channel_id")
        self.favorite("destroy", article_id, channel_id)
        sleep_random(3, 10)
        self.favorite("create", article_id, channel_id)
        sleep_random(3, 10)
        self.favorite("destroy", article_id, channel_id)
        sleep_random(5, 15)
        ok, _ = self.receive_reward(task.get("task_id", ""))
        return ok

    def do_rating_task(self, task: dict) -> bool:
        print(f"开始任务: {task.get('task_name')}")
        article = self.resolve_article_from_task(task)
        if not article:
            return False
        article_id = article.get("article_id")
        channel_id = article.get("article_channel_id")
        if article.get("article_price"):
            self.rating("worth_cancel", article_id, channel_id, 3)
            sleep_random(3, 10)
            self.rating("worth_create", article_id, channel_id, 1)
            sleep_random(3, 10)
            self.rating("worth_cancel", article_id, channel_id, 3)
        else:
            self.rating("like_cancel", article_id, channel_id)
            sleep_random(3, 10)
            self.rating("like_create", article_id, channel_id)
            sleep_random(3, 10)
            self.rating("like_cancel", article_id, channel_id)
            sleep_random(3, 10)
            self.rating("like_create", article_id, channel_id)
            sleep_random(3, 10)
            self.rating("like_cancel", article_id, channel_id)
        sleep_random(5, 15)
        ok, _ = self.receive_reward(task.get("task_id", ""))
        return ok

    def do_follow_user_task(self, task: dict) -> bool:
        print(f"开始任务: {task.get('task_name')}")
        user = self.get_user_by_random()
        if not user:
            return False
        for _ in range(max(1, int(task.get("task_even_num", 1)) - int(task.get("task_finished_num", 0)))):
            if str(user.get("is_follow")) == "1":
                self.follow("destroy", "user", user.get("keyword", ""))
                sleep_random(3, 10)
            self.follow("create", "user", user.get("keyword", ""))
            sleep_random(3, 10)
            if str(user.get("is_follow")) == "0":
                self.follow("destroy", "user", user.get("keyword", ""))
            sleep_random(3, 10)
        sleep_random(5, 15)
        ok, _ = self.receive_reward(task.get("task_id", ""))
        return ok

    def do_follow_tag_task(self, task: dict) -> bool:
        print(f"开始任务: {task.get('task_name')}")
        redirect = task.get("task_redirect_url") or {}
        tag_id = redirect.get("link_val")
        if str(tag_id) == "0" or not tag_id:
            tag = self.get_tag_by_random()
            if not tag:
                return False
            tag_id = tag.get("lanmu_id")
        detail = self.get_tag_detail(tag_id)
        if not detail.get("lanmu_id"):
            return False
        name = (detail.get("lanmu_info") or {}).get("lanmu_name", "")
        self.follow("destroy", "tag", name, detail.get("lanmu_id"))
        sleep_random(3, 10)
        self.follow("create", "tag", name, detail.get("lanmu_id"))
        sleep_random(3, 10)
        self.follow("destroy", "tag", name, detail.get("lanmu_id"))
        sleep_random(5, 15)
        ok, _ = self.receive_reward(task.get("task_id", ""))
        return ok

    def do_follow_brand_task(self, task: dict) -> bool:
        print(f"开始任务: {task.get('task_name')}")
        brand_id = (task.get("task_redirect_url") or {}).get("link_val")
        brand = self.get_brand_detail(brand_id)
        if not brand.get("id"):
            return False
        self.follow_brand("dingyue_lanmu_del", brand.get("id"), brand.get("title", ""))
        sleep_random(3, 10)
        self.follow_brand("dingyue_lanmu_add", brand.get("id"), brand.get("title", ""))
        sleep_random(3, 10)
        self.follow_brand("dingyue_lanmu_del", brand.get("id"), brand.get("title", ""))
        sleep_random(5, 15)
        ok, _ = self.receive_reward(task.get("task_id", ""))
        return ok

    def do_comment_task(self, task: dict) -> bool:
        print(f"开始任务: {task.get('task_name')}")
        article = self.get_one_by_random(self.get_article_list(20))
        if not article:
            return False
        result = self.submit_comment(article.get("article_id"), article.get("article_channel_id"), os.getenv("SMZDM_COMMENT", ""))
        if not result["success"]:
            return False
        comment_id = ((result.get("data") or {}).get("data") or {}).get("comment_ID")
        if comment_id:
            print("删除评论")
            sleep_random(20, 30)
            if not self.remove_comment(comment_id):
                sleep_random(10, 20)
                self.remove_comment(comment_id)
        sleep_random(5, 15)
        ok, _ = self.receive_reward(task.get("task_id", ""))
        return ok

    def do_crowd_task(self, task: dict) -> bool:
        print(f"开始任务: {task.get('task_name')}")
        crowd_id = self.get_crowd("免费", 0)
        if not crowd_id:
            if os.getenv("SMZDM_CROWD_SILVER_5") == "yes":
                crowd_id = self.get_crowd("5碎银子", 5)
            else:
                print("请设置 SMZDM_CROWD_SILVER_5=yes 后再进行 5 碎银抽奖")
                return False
        if not crowd_id:
            return False
        sleep_random(5, 15)
        if not self.join_crowd(crowd_id):
            return False
        sleep_random(5, 15)
        ok, _ = self.receive_reward(task.get("task_id", ""))
        return ok

    def get_task_articles(self, task: dict) -> list[dict]:
        if str(task.get("article_id", "0")) == "0":
            count = max(1, int(task.get("task_even_num", 1)) - int(task.get("task_finished_num", 0)))
            return self.get_article_list(count)
        return [{"article_id": task.get("article_id"), "article_channel_id": task.get("channel_id")}]

    def resolve_article_from_task(self, task: dict) -> dict:
        redirect = task.get("task_redirect_url") or {}
        link_type = redirect.get("link_type")
        link_val = redirect.get("link_val")
        if link_type == "lanmu":
            return self.get_one_by_random(self.get_article_list_from_lanmu(link_val, 20)) or {}
        if link_type == "tag":
            return self.get_one_by_random(self.get_article_list_from_tag(link_val, redirect.get("link_title", ""), 20)) or {}
        if str(link_val) == "0" or not link_val:
            return self.get_one_by_random(self.get_article_list(20)) or {}
        detail = self.get_article_detail(link_val)
        if detail:
            return {"article_id": link_val, "article_channel_id": detail.get("channel_id")}
        return {}

    def open_article(self, task: dict, article: dict) -> None:
        scheme = ((task.get("task_redirect_url") or {}).get("scheme_url") or "")
        if re.search(r"detail_haojia", scheme, re.I):
            self.get_haojia_detail(article.get("article_id"))
        else:
            self.get_article_detail(article.get("article_id"))

    def get_article_list(self, num: int = 1) -> list[dict]:
        result = request_api(
            self.session,
            "https://article-api.smzdm.com/ranking_list/articles",
            headers=self.headers(),
            data={
                "offset": 0,
                "channel_id": 76,
                "tab": 2,
                "order": 0,
                "limit": 20,
                "exclude_article_ids": "",
                "stream": "a",
                "ab_code": "b",
            },
        )
        if result["success"]:
            return (result["data"].get("data", {}).get("rows") or [])[:num]
        print(f"获取文章列表失败: {result['response'][:200]}")
        return []

    def get_article_detail(self, article_id: Any) -> dict:
        result = request_api(
            self.session,
            f"https://article-api.smzdm.com/article_detail/{article_id}",
            headers=self.headers(),
            data={
                "comment_flow": "",
                "hashcode": "",
                "lastest_update_time": "",
                "uhome": 0,
                "imgmode": 0,
                "article_channel_id": 0,
                "h5hash": "",
            },
        )
        if result["success"]:
            return result["data"].get("data", {}) or {}
        print(f"获取文章详情失败: {result['response'][:200]}")
        return {}

    def get_haojia_detail(self, article_id: Any) -> dict:
        result = request_api(
            self.session,
            f"https://haojia-api.smzdm.com/detail/{article_id}",
            headers=self.headers(),
            data={"imgmode": 0, "hashcode": "", "h5hash": ""},
        )
        if result["success"]:
            return result["data"].get("data", {}) or {}
        print(f"获取好价详情失败: {result['response'][:200]}")
        return {}

    def share_article_done(self, article_id: Any, channel_id: Any) -> bool:
        result = request_api(
            self.session,
            "https://user-api.smzdm.com/share/complete_share_rule",
            method="post",
            headers=self.headers(),
            data={
                "token": self.token,
                "article_id": article_id,
                "channel_id": channel_id,
                "tag_name": "gerenzhongxin",
            },
        )
        print("完成分享成功" if result["success"] else f"完成分享失败: {result['response'][:200]}")
        return result["success"]

    def share_daily_reward(self, channel_id: Any) -> bool:
        result = request_api(
            self.session,
            "https://user-api.smzdm.com/share/daily_reward",
            method="post",
            headers=self.headers(),
            data={"token": self.token, "channel_id": channel_id},
        )
        if result["success"]:
            print(result["data"].get("data", {}).get("reward_desc", ""))
        return result["success"]

    def share_callback(self, article_id: Any, channel_id: Any) -> bool:
        result = request_api(
            self.session,
            "https://user-api.smzdm.com/share/callback",
            method="post",
            headers=self.headers(),
            data={
                "token": self.token,
                "article_id": article_id,
                "channel_id": channel_id,
                "touchstone_event": self.touchstone({
                    "event_value": {"aid": article_id, "cid": channel_id, "is_detail": True, "pid": "无"},
                    "sourceMode": "排行榜_社区_好文精选",
                    "sourcePage": f"Android/长图文/P/{article_id}/",
                    "upperLevel_url": "排行榜/社区/好文精选/文章_24H/",
                }),
            },
        )
        print("分享回调完成" if result["success"] else f"分享回调失败: {result['response'][:200]}")
        return result["success"]

    def favorite(self, method: str, article_id: Any, channel_id: Any) -> bool:
        result = request_api(
            self.session,
            f"https://user-api.smzdm.com/favorites/{method}",
            method="post",
            headers=self.headers(),
            data={
                "touchstone_event": self.touchstone({
                    "event_value": {"aid": article_id, "cid": channel_id, "is_detail": True},
                    "sourceMode": "我的_我的任务页",
                    "sourcePage": f"Android/长图文/P/{article_id}/",
                    "upperLevel_url": "个人中心/赚奖励/",
                }),
                "token": self.token,
                "id": article_id,
                "channel_id": channel_id,
            },
        )
        print(f"{method} 收藏{'成功' if result['success'] else '失败'}: {article_id}")
        return result["success"]

    def rating(self, method: str, article_id: Any, channel_id: Any, rating_type: int | None = None) -> bool:
        result = request_api(
            self.session,
            f"https://user-api.smzdm.com/rating/{method}",
            method="post",
            headers=self.headers(),
            data={
                "touchstone_event": self.touchstone({
                    "event_value": {"aid": article_id, "cid": channel_id, "is_detail": True},
                    "sourceMode": "栏目页",
                    "sourcePage": f"Android//P/{article_id}/",
                    "upperLevel_url": "栏目页///",
                }),
                "token": self.token,
                "id": article_id,
                "channel_id": channel_id,
                "wtype": rating_type,
            },
        )
        print(f"{method} 点赞{'成功' if result['success'] else '失败'}: {article_id}")
        return result["success"]

    def follow(self, method: str, follow_type: str, keyword: str, keyword_id: Any = "") -> bool:
        if follow_type == "user":
            touchstone = self.touchstone({
                "event_value": {"cid": "null", "is_detail": False, "p": "1"},
                "sourceMode": "我的_我的任务页",
                "sourcePage": "Android/关注/达人/爆料榜",
                "upperLevel_url": "关注/达人/推荐/",
            })
        else:
            touchstone = self.touchstone({
                "event_value": {"cid": "null", "is_detail": False},
                "sourceMode": "栏目页",
                "sourcePage": f"Android/栏目页/{keyword}/{keyword_id}/",
                "source_page_type_id": str(keyword_id),
                "upperLevel_url": "个人中心/赚奖励/",
                "source_area": {"lanmu_id": str(keyword_id), "prev_source_scence": "我的_我的任务页"},
            })
        result = request_api(
            self.session,
            f"https://dingyue-api.smzdm.com/dingyue/{method}",
            method="post",
            headers=self.headers(),
            data={
                "touchstone_event": touchstone,
                "refer": "",
                "keyword_id": keyword_id,
                "keyword": keyword,
                "type": follow_type,
            },
        )
        print(f"{method} 关注{'成功' if result['success'] else '失败'}: {keyword}")
        return result["success"]

    def follow_brand(self, method: str, keyword_id: Any, keyword: str) -> bool:
        result = request_api(
            self.session,
            "https://dingyue-api.smzdm.com/dy/util/api/user_action",
            method="post",
            headers=self.headers(),
            data={
                "action": method,
                "params": json.dumps({"keyword": keyword_id, "keyword_id": keyword_id, "type": "brand"}, ensure_ascii=False),
                "refer": f"Android/其他/品牌详情页/{keyword}/{keyword_id}/",
                "touchstone_event": self.touchstone({
                    "event_value": {"cid": "44", "is_detail": True, "aid": str(keyword_id)},
                    "sourceMode": "百科_品牌详情页",
                    "sourcePage": f"Android/其他/品牌详情页/{keyword}/{keyword_id}/",
                    "upperLevel_url": "个人中心/赚奖励/",
                }),
            },
        )
        print(f"{method} 关注品牌{'成功' if result['success'] else '失败'}: {keyword}")
        return result["success"]

    def get_user_by_random(self) -> dict:
        result = request_api(
            self.session,
            "https://dingyue-api.smzdm.com/tuijian/search_result",
            method="post",
            headers=self.headers(),
            data={"nav_id": 0, "page": 1, "type": "user", "time_code": ""},
        )
        if result["success"]:
            return self.get_one_by_random(result["data"].get("data", {}).get("rows") or []) or {}
        print(f"获取用户列表失败: {result['response'][:200]}")
        return {}

    def get_tag_by_random(self) -> dict:
        result = request_api(
            self.session,
            "https://dingyue-api.smzdm.com/tuijian/search_result",
            headers=self.headers(),
            data={"time_code": "", "nav_id": "", "type": "tag", "limit": 20},
        )
        if result["success"]:
            return self.get_one_by_random(result["data"].get("data", {}).get("rows") or []) or {}
        print(f"获取栏目列表失败: {result['response'][:200]}")
        return {}

    def get_tag_detail(self, tag_id: Any) -> dict:
        result = request_api(
            self.session,
            "https://common-api.smzdm.com/lanmu/config_data",
            headers=self.headers(),
            data={"middle_page": "", "tab_selects": "", "redirect_params": tag_id},
        )
        if result["success"]:
            return result["data"].get("data", {}) or {}
        print(f"获取栏目信息失败: {result['response'][:200]}")
        return {}

    def get_brand_detail(self, brand_id: Any) -> dict:
        result = request_api(
            self.session,
            "https://brand-api.smzdm.com/brand/brand_basic",
            headers=self.headers(),
            data={"brand_id": brand_id},
        )
        if result["success"]:
            return result["data"].get("data", {}) or {}
        print(f"获取品牌信息失败: {result['response'][:200]}")
        return {}

    def get_article_list_from_lanmu(self, tag_id: Any, num: int = 1) -> list[dict]:
        detail = self.get_tag_detail(tag_id)
        tabs = detail.get("tab") or []
        if not detail.get("lanmu_id") or not tabs:
            return []
        result = request_api(
            self.session,
            "https://common-api.smzdm.com/lanmu/list_data",
            headers=self.headers(),
            data={
                "price_lt": "",
                "order": "",
                "category_ids": "",
                "price_gt": "",
                "referer_article": "",
                "tag_params": "",
                "mall_ids": "",
                "time_sort": "",
                "page": 1,
                "params": tag_id,
                "limit": 20,
                "tab_params": tabs[0].get("params", ""),
            },
        )
        if result["success"]:
            return (result["data"].get("data", {}).get("rows") or [])[:num]
        print(f"获取栏目文章失败: {result['response'][:200]}")
        return []

    def get_article_list_from_tag(self, tag_id: Any, name: str, num: int = 1) -> list[dict]:
        status = self.get_dingyue_status(name)
        result = request_api(
            self.session,
            "https://tag-api.smzdm.com/theme/detail_feed",
            headers=self.headers(),
            data={
                "article_source": 1,
                "past_num": 0,
                "feed_sort": 2,
                "smzdm_id": status.get("smzdm_id", ""),
                "tag_id": tag_id,
                "name": name,
                "time_sort": 0,
                "page": 1,
                "article_tab": 0,
                "limit": 20,
            },
        )
        if result["success"]:
            return (result["data"].get("data", {}).get("rows") or [])[:num]
        print(f"获取 Tag 文章失败: {result['response'][:200]}")
        return []

    def get_dingyue_status(self, name: str) -> dict:
        result = request_api(
            self.session,
            "https://dingyue-api.smzdm.com/dingyue/follow_status",
            method="post",
            headers=self.headers(),
            data={"rules": json.dumps([{"type": "tag", "keyword": name}], ensure_ascii=False)},
        )
        if result["success"]:
            return result["data"]
        print(f"获取订阅状态失败: {result['response'][:200]}")
        return {}

    def submit_comment(self, article_id: Any, channel_id: Any, content: str) -> dict:
        result = request_api(
            self.session,
            "https://comment-api.smzdm.com/comments/submit",
            method="post",
            headers=self.headers(),
            data={
                "touchstone_event": self.touchstone({
                    "event_value": {"aid": article_id, "cid": channel_id, "is_detail": True},
                    "sourceMode": "好物社区_全部",
                    "sourcePage": f"Android/长图文/{article_id}/评论页/",
                    "upperLevel_url": "好物社区/首页/全部/",
                    "sourceRoot": "社区",
                }),
                "is_like": 3,
                "reply_from": 3,
                "smiles": 0,
                "atta": 0,
                "parentid": 0,
                "token": self.token,
                "article_id": article_id,
                "channel_id": channel_id,
                "content": content,
            },
        )
        print("评论发表成功" if result["success"] else f"评论发表失败: {result['response'][:200]}")
        return result

    def remove_comment(self, comment_id: Any) -> bool:
        result = request_api(
            self.session,
            "https://comment-api.smzdm.com/comments/delete_comment",
            method="post",
            headers=self.headers(),
            data={"comment_id": comment_id},
        )
        print(f"评论删除{'成功' if result['success'] else '失败'}: {comment_id}")
        return result["success"]

    def get_crowd(self, name: str, price: int) -> str:
        result = request_api(
            self.session,
            "https://zhiyou.smzdm.com/user/crowd/",
            headers=self.web_headers(),
            sign=False,
            parse_response_json=False,
        )
        if not result["success"]:
            print(f"获取{name}抽奖失败: {result['response'][:200]}")
            return ""

        pattern = re.compile(
            rf'<button\s+([^>]+?)>\s*<div\s+[^>]+?>\s*{re.escape(name)}(?:抽奖)?\s*</div>\s*'
            rf'<span\s+class="reduceNumber">-{price}</span>[\s\S]+?</button>',
            re.I,
        )
        crowds = pattern.findall(result["data"])
        if not crowds:
            print(f"未找到{name}抽奖")
            return ""
        keyword = os.getenv("SMZDM_CROWD_KEYWORD", "").strip()
        selected = ""
        if price > 0 and keyword:
            selected = next((item for item in crowds if keyword in item), "")
        selected = selected or self.get_one_by_random(crowds) or ""
        match = re.search(r'data-crowd_id="(\d+)"', selected, re.I)
        if match:
            print(f"{name}抽奖ID: {match.group(1)}")
            return match.group(1)
        print(f"未找到{name}抽奖ID")
        return ""

    def join_crowd(self, crowd_id: str) -> bool:
        result = request_api(
            self.session,
            "https://zhiyou.m.smzdm.com/user/crowd/ajax_participate",
            method="post",
            headers={**self.web_headers(), "Origin": "https://zhiyou.m.smzdm.com", "Referer": f"https://zhiyou.m.smzdm.com/user/crowd/p/{crowd_id}/"},
            sign=False,
            data={
                "crowd_id": crowd_id,
                "sourcePage": f"https://zhiyou.m.smzdm.com/user/crowd/p/{crowd_id}/",
                "client_type": "android",
                "sourceRoot": "个人中心",
                "sourceMode": "幸运屋抽奖",
                "price_id": 1,
            },
        )
        if result["success"]:
            print(remove_tags(result["data"].get("data", {}).get("msg", "")))
            return True
        print(f"参加抽奖失败: {result['response'][:200]}")
        return False

    def touchstone(self, extra: dict) -> str:
        base = {
            "search_tv": "f",
            "sourceRoot": "个人中心",
            "trafic_version": "113_a,115_b,116_e,118_b,131_b,132_b,134_b,136_b,139_a",
            "tv": "z1",
        }
        base.update(extra)
        return json.dumps(base, ensure_ascii=False, separators=(",", ":"))

    def get_one_by_random(self, listing: list) -> Any:
        if not listing:
            return None
        return random.choice(listing)


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
            full_log.append(header + "\n" + SmzdmTask(account.cookie).run())
        except Exception as exc:
            err = f"❌ {account.account_name} 异常: {exc}"
            print(err)
            full_log.append(err)

    push = "\n".join(full_log)
    filtered = "\n".join(line for line in push.splitlines() if any(keyword in line for keyword in PUSH_KEYWORDS))
    send("什么值得买每日任务", filtered or push)


if __name__ == "__main__":
    main()
