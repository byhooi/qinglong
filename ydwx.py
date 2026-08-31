#!/usr/bin/python3
# -- coding: utf-8 --
# -------------------------------
# @Author : github@wd210010 https://github.com/wd210010/just_for_happy
# @Time : 2023/2/27 13:23
# -------------------------------
# cron: 2 8 * * *
# const $ = new Env('一点万象签到')
import hashlib
import json
import os
import sys
import time

import requests

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

try:
    from sendNotify import send
except Exception:
    def send(title, content):
        print(f"\n{title}\n{content}")


# 登录后搜索 https://app.mixcapp.com/mixc/gateway 域名随意一个请求体里面的 deviceParams、token
# 青龙变量: ydwx_deviceParams ydwx_token
# 多账号用 & 分隔，两个变量的账号顺序需保持一致
def load_accounts():
    device_params = [item.strip() for item in os.getenv("ydwx_deviceParams", "").split("&") if item.strip()]
    tokens = [item.strip() for item in os.getenv("ydwx_token", "").split("&") if item.strip()]

    total = max(len(device_params), len(tokens))
    accounts = []
    for index in range(total):
        accounts.append({
            "account_name": f"帐号{index + 1}",
            "device_params": device_params[index] if index < len(device_params) else "",
            "token": tokens[index] if index < len(tokens) else "",
        })
    return accounts


def sign_in(account):
    account_name = account["account_name"]
    result_info = {
        "account_name": account_name,
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

    timestamp = str(int(round(time.time() * 1000)))
    md5 = hashlib.md5()
    sig = (
        "action=mixc.app.memberSign.sign&apiVersion=1.0"
        "&appId=68a91a5bac6a4f3e91bf4b42856785c6"
        "&appVersion=3.53.0"
        f"&deviceParams={account['device_params']}"
        "&imei=2333&mallNo=8602A101&osVersion=12.0.1"
        "&params=eyJtYWxsTm8iOiIyMDAxNCJ9&platform=h5"
        f"&timestamp={timestamp}"
        f"&token={account['token']}"
        "&P@Gkbu0shTNHjhM!7F"
    )
    md5.update(sig.encode("utf-8"))
    sign = md5.hexdigest()

    url = "https://app.mixcapp.com/mixc/gateway"
    headers = {
        "Host": "app.mixcapp.com",
        "Connection": "keep-alive",
        "Content-Length": "564",
        "Accept": "application/json, text/plain, */*",
        "Origin": "https://app.mixcapp.com",
        "User-Agent": "Mozilla/5.0 (Linux; Android 10; PCAM00 Build/QKQ1.190918.001; wv) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/77.0.3865.92 Mobile Safari/537.36/MIXCAPP/3.42.2/AnalysysAgent/Hybrid",
        "Sec-Fetch-Mode": "cors",
        "Content-Type": "application/x-www-form-urlencoded",
        "X-Requested-With": "com.crland.mixc",
        "Sec-Fetch-Site": "same-origin",
        "Referer": "https://app.mixcapp.com/m/m-8602A101/signIn?showWebNavigation=true&timestamp=1676906528979&appVersion=3.53.0&mallNo=8602A101",
        "Accept-Encoding": "gzip, deflate",
        "Accept-Language": "zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7",
    }
    data = (
        "mallNo=8602A101&appId=68a91a5bac6a4f3e91bf4b42856785c6"
        "&platform=h5&imei=2333&appVersion=3.53.0&osVersion=12.0.1"
        "&action=mixc.app.memberSign.sign&apiVersion=1.0"
        f"&timestamp={timestamp}"
        f"&deviceParams={account['device_params']}"
        f"&token={account['token']}"
        f"&params=eyJtYWxsTm8iOiIyMDAxNCJ9&sign={sign}"
    )

    try:
        response = requests.post(url=url, headers=headers, data=data, timeout=20)
        response.raise_for_status()
        response_data = response.json()
    except requests.RequestException as e:
        result_info["error"] = f"请求失败: {e}"
        return result_info
    except json.JSONDecodeError:
        result_info["error"] = "接口返回不是 JSON"
        return result_info

    message = response_data.get("message") or response_data.get("msg") or "未知返回"
    code = response_data.get("code")
    success = response_data.get("success")
    err_code = response_data.get("errCode")

    if success is True or code in (0, "0", "S0A00000") or err_code in (0, "0"):
        result_info["success"] = True
        result_info["message"] = message
    elif "已签到" in message or "签到成功" in message or "成功" in message:
        result_info["success"] = True
        result_info["message"] = message
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
