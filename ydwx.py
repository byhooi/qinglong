#!/usr/bin/python3
# -- coding: utf-8 -*-
# -------------------------------
# @Author : byhooi
# @Time : 2026/10/26
# 原脚本: github@wd210010 https://github.com/wd210010/just_for_happy
# 本版基于原脚本修改，适配 App 4.2.10 新协议
# -------------------------------
# cron: 2 8 * * *
# const $ = new Env('一点万象签到')
#
# App 4.2.10 协议(2026-10 重抓包适配):
# 网关 https://app.mixcapp.com/mixc/gateway 请求体不再有 sign/params,
# 改为 X-Mixc-Swimlane/t/date; 服务端前置阿里云 WAF, 需携带其下发的 cookie
# 否则会被拦截返回 405。
#
# 青龙环境变量(多账号用 & 分隔, 各变量账号顺序保持一致):
#   ydwx_deviceParams  请求体中的 deviceParams(直接复制抓包中 URL 编码后的值即可)
#   ydwx_token         同一请求体中的 token
#   ydwx_cookie        可选, 请求头中的 Cookie 整行(含 acw_tc 等 WAF cookie);
#                      仅在仍被 405 拦截时需要配置
import json
import os
import sys
import time
import uuid
from urllib.parse import unquote

import requests

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

try:
    from sendNotify import send
except Exception:
    def send(title, content):
        print(f"\n{title}\n{content}")

GATEWAY_URL = "https://app.mixcapp.com/mixc/gateway"
SIGN_PAGE_URL = "https://app.mixcapp.com/m/m-8602A101/signIn"
USER_AGENT = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 18_7 like Mac OS X) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) crland/4.4.0 grayscale/0 "
    "/MIXCAPP/4.2.10 AnalysysAgent/Hybrid"
)
APP_VERSION = "4.2.10"
MAX_RETRY = 3


def load_accounts():
    def split_env(name):
        return [item.strip() for item in os.getenv(name, "").split("&") if item.strip()]

    device_params = split_env("ydwx_deviceParams")
    tokens = split_env("ydwx_token")
    cookies = split_env("ydwx_cookie")

    accounts = []
    for index in range(max(len(device_params), len(tokens))):
        accounts.append({
            "account_name": f"帐号{index + 1}",
            "device_params": device_params[index] if index < len(device_params) else "",
            "token": tokens[index] if index < len(tokens) else "",
            "cookie": cookies[index] if index < len(cookies) else "",
        })
    return accounts


def build_form(account):
    now = str(int(time.time() * 1000))
    return {
        "mallNo": "8602A101",
        "appId": "68a91a5bac6a4f3e91bf4b42856785c6",
        "platform": "h5",
        "imei": str(uuid.uuid4()).upper(),
        "appVersion": APP_VERSION,
        "osVersion": "27.0.1",
        "action": "mixc.app.memberSign.sign",
        "apiVersion": "1.0",
        "timestamp": now,
        # 抓包复制的是 URL 编码值, 先解码, 由 requests 重新统一编码
        "deviceParams": unquote(account["device_params"]),
        "X-Mixc-Swimlane": "s1",
        "t": now,
        "date": time.strftime("%Y-%m-%d %H:%M:%S"),
        "token": account["token"],
    }


def build_success_message(response_data, message):
    data = response_data.get("data") or {}
    sign_map = data.get("signDataMap") or {}
    parts = [message]
    if sign_map.get("todayPoint") is not None:
        parts.append(f"今日+{sign_map['todayPoint']}分")
    if sign_map.get("continuousSign") is not None:
        parts.append(f"连签{sign_map['continuousSign']}天")
    if data.get("userPoints") is not None:
        parts.append(f"总积分{data['userPoints']}")
    return ", ".join(str(part) for part in parts)


def sign_in(account):
    result_info = {
        "account_name": account["account_name"],
        "success": False,
        "message": "",
        "error": "",
    }

    if not account["device_params"]:
        result_info["error"] = "deviceParams 为空"
        return result_info
    if not account["token"]:
        result_info["error"] = "token 为空"
        return result_info

    headers = {
        "Accept": "application/json, text/plain, */*",
        "Content-Type": "application/x-www-form-urlencoded",
        "Origin": "https://app.mixcapp.com",
        "User-Agent": USER_AGENT,
        "Referer": (
            f"https://app.mixcapp.com/m/m-8602A101/signIn"
            f"?appVersion={APP_VERSION}&mallNo=8602A101"
            f"&timestamp={int(time.time() * 1000)}"
            "&showWebNavigation=true&hideNativeNavigation=true"
        ),
        "Accept-Language": "zh-CN,zh-Hans;q=0.9",
        "Sec-Fetch-Site": "same-origin",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Dest": "empty",
        "X-Requested-With": "com.crland.mixc",
    }

    session = requests.Session()
    session.headers.update(headers)
    if account["cookie"]:
        session.headers["Cookie"] = account["cookie"]

    # 先访问签到页, 领取阿里云 WAF 下发的 acw_tc 等 cookie, 避免直接 POST 被 405 拦截
    try:
        session.get(SIGN_PAGE_URL, timeout=20)
    except requests.RequestException:
        pass

    response = None
    for _ in range(MAX_RETRY):
        try:
            response = session.post(GATEWAY_URL, data=build_form(account), timeout=20)
        except requests.RequestException as e:
            result_info["error"] = f"请求失败: {e}"
            return result_info

        if response.status_code != 405:
            break
        # 405 为 WAF 拦截, 响应可能已下发新 cookie, 稍等后带上重试
        time.sleep(1)

    if response is None or response.status_code != 200:
        status = response.status_code if response is not None else "无响应"
        result_info["error"] = f"HTTP {status}, 疑似被 WAF 拦截, 请配置 ydwx_cookie 后重试"
        return result_info

    try:
        response_data = response.json()
    except json.JSONDecodeError:
        result_info["error"] = "接口返回不是 JSON"
        return result_info

    message = response_data.get("message") or response_data.get("msg") or "未知返回"
    code = response_data.get("code")
    err_code = response_data.get("errCode")

    if (
        response_data.get("success") is True
        or code in (0, "0", "S0A00000")
        or err_code in (0, "0")
        or "已签到" in message
        or "成功" in message
    ):
        result_info["success"] = True
        result_info["message"] = build_success_message(response_data, message)
    else:
        result_info["error"] = message

    return result_info


def build_notification(results):
    total_count = len(results)
    success_count = sum(1 for item in results if item.get("success"))
    failed_count = total_count - success_count

    if total_count == 0:
        return "一点万象签到失败 ❌", "未获取到 ydwx_deviceParams 或 ydwx_token 环境变量"
    if failed_count == 0:
        title = "一点万象签到成功 ✅"
    elif success_count == 0:
        title = "一点万象签到失败 ❌"
    else:
        title = "一点万象签到部分成功 ⚠️"

    content_parts = []
    for result in results:
        account_name = result.get("account_name", "未知账号")
        if result.get("success"):
            message = result.get("message") or "签到成功"
            content_parts.append(f"✅ [{account_name}] {message}")
        else:
            error = result.get("error") or "未知错误"
            if len(error) > 50:
                error = error[:50] + "..."
            content_parts.append(f"❌ [{account_name}] {error}")

    return title, "\n".join(content_parts)


def main():
    accounts = load_accounts()
    print(f"共配置了{len(accounts)}个账号")

    results = []
    for index, account in enumerate(accounts):
        print(f"*****第{index + 1}个账号*****")
        result = sign_in(account)
        results.append(result)

        if result.get("success"):
            print(f"✅ {result['account_name']} {result.get('message')}")
        else:
            print(f"❌ {result['account_name']} {result.get('error')}")

    title, content = build_notification(results)
    send(title, content)


if __name__ == "__main__":
    main()
