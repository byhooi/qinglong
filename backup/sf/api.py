#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
顺丰快递API模块

提供顺丰快递积分任务相关的API接口
"""

import hashlib
import logging
import os
import time
from dataclasses import dataclass
from http.cookies import SimpleCookie
from typing import Any, Dict, List, Optional
from urllib.parse import unquote

import execjs
import requests

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ShareLoginInfo:
    """分享登录接口返回信息"""

    success: bool
    user_id: str
    token: str
    cookies: str
    raw: Dict[str, Any]
    error: str = ""


class SFExpressAPI:
    """顺丰速运API接口类"""

    BASE_URL = "https://mcs-mimp-web.sf-express.com"
    SYS_CODE = "MCS-MIMP-CORE"
    SHARE_LOGIN_PATH = "/mcs-mimp/share/app/shareLogin"
    SHARE_LOGIN_PARAMS = {"bizCode": "622", "source": "SFAPP"}
    DEFAULT_WEB_USER_AGENT = (
        "Mozilla/5.0 (iPod; U; CPU iPhone OS 3_1 like Mac OS X; sq-AL) AppleWebKit/533.18.3 (KHTML, like Gecko) Version/4.0.5 Mobile/8B119 Safari/6533.18.3"
    )
    DEFAULT_SHARE_LOGIN_USER_AGENT = (
        "SFMainland_Store_Pro/9.86.0.5 CFNetwork/3860.200.71 Darwin/25.1.0"
    )

    def __init__(self, cookies: str = None, user_id: str = None, user_agent: str = None, channel: str = None, device_id: str = None):
        """
        初始化SF Express API

        Args:
            cookies: Cookie字符串
            user_id: 用户ID
            user_agent: 用户代理
            channel: 渠道
            device_id: 设备ID
        """
        self.js_file_path = os.path.join(os.path.dirname(__file__), 'code.js')
        self.base_url = self.BASE_URL
        self.session = requests.Session()
        self.cookies = cookies
        self.user_id = user_id
        self.user_agent = user_agent or self.DEFAULT_WEB_USER_AGENT
        self.channel = channel
        self.device_id = device_id
        self._init_js()

        self.default_headers = {
            "User-Agent": self.user_agent,
            "pragma": "no-cache",
            "cache-control": "no-cache",
            "timestamp": "",
            "signature": "",
            "channel": self.channel or "",
            "syscode": self.SYS_CODE,
            "sw8": "",
            "platform": "SFAPP",
            "sec-gpc": "1",
            "accept-language": "zh-CN,zh;q=0.9",
            "origin": "https://mcs-mimp-web.sf-express.com",
            "sec-fetch-site": "same-origin",
            "sec-fetch-mode": "cors",
            "sec-fetch-dest": "empty",
            "referer": "https://mcs-mimp-web.sf-express.com/superWelfare?citycode=&cityname=&tab=0",
            "cookie": self.cookies,
            "priority": "u=1, i"
        }

    def _init_js(self) -> None:
        """初始化JavaScript环境"""
        try:
            with open(self.js_file_path, 'r', encoding='utf-8') as f:
                js_code = f.read()
            self.js_context = execjs.compile(js_code)
        except Exception as e:
            logger.error(f"初始化JavaScript环境失败: {e}")
            self.js_context = None

    def get_sw8(self, url_path: str) -> Optional[Dict[str, Any]]:
        """调用JavaScript中的get_sw8函数"""
        if self.js_context is None:
            raise RuntimeError("JavaScript context not initialized")

        try:
            result = self.js_context.call('get_sw8', url_path)
            return result
        except Exception as e:
            logger.error(f"调用get_sw8函数时出错: {e}")
            return None

    def generate_signature(self, timestamp: str, sys_code: str = None) -> str:
        """生成签名"""
        sign_str = f"wwesldfs29aniversaryvdld29&timestamp={timestamp}&sysCode={sys_code}"
        return hashlib.md5(sign_str.encode()).hexdigest()

    @classmethod
    def share_login(cls, sign: str, user_agent: Optional[str] = None) -> ShareLoginInfo:
        """
        分享登录接口，获取用户ID与Cookie

        Args:
            sign: 分享登录sign值
            user_agent: 请求User-Agent

        Returns:
            ShareLoginInfo: 登录信息
        """
        if not sign:
            return ShareLoginInfo(
                success=False,
                user_id="",
                token="",
                cookies="",
                raw={},
                error="sign为空，无法请求分享登录接口"
            )

        url = f"{cls.BASE_URL}{cls.SHARE_LOGIN_PATH}"
        decoded_sign = unquote(sign.strip())
        params = {**cls.SHARE_LOGIN_PARAMS, "sign": decoded_sign}
        headers = {
            "User-Agent": user_agent or cls.DEFAULT_SHARE_LOGIN_USER_AGENT,
            "content-type": "application/json",
            "priority": "u=3, i",
            "accept-language": "zh-CN,zh-Hans;q=0.9",
        }

        session = requests.Session()
        response = None
        try:
            response = session.get(url, headers=headers, params=params, timeout=30)
            response.raise_for_status()
            data = response.json()
        except requests.exceptions.RequestException as e:
            return ShareLoginInfo(
                success=False,
                user_id="",
                token="",
                cookies="",
                raw={},
                error=f"请求分享登录接口失败: {e}"
            )
        except ValueError as e:
            return ShareLoginInfo(
                success=False,
                user_id="",
                token="",
                cookies="",
                raw={},
                error=f"分享登录响应解析失败: {e}"
            )

        cookies = cls._build_cookie_from_response(response)
        obj = data.get("obj", {}) if isinstance(data, dict) else {}
        success = bool(data.get("success")) if isinstance(data, dict) else False
        error_message = data.get("errorMessage", "") if isinstance(data, dict) else "分享登录返回异常"

        return ShareLoginInfo(
            success=success,
            user_id=obj.get("userId", "") if isinstance(obj, dict) else "",
            token=obj.get("token", "") if isinstance(obj, dict) else "",
            cookies=cookies,
            raw=data,
            error=error_message
        )

    @staticmethod
    def _get_set_cookie_headers(response: requests.Response) -> List[str]:
        """获取所有Set-Cookie头"""
        if hasattr(response.raw, "headers"):
            raw_headers = response.raw.headers
            if hasattr(raw_headers, "getlist"):
                return raw_headers.getlist("Set-Cookie")
            if hasattr(raw_headers, "get_all"):
                return raw_headers.get_all("Set-Cookie")

        header = response.headers.get("Set-Cookie")
        return [header] if header else []

    @classmethod
    def _build_cookie_from_response(cls, response: requests.Response) -> str:
        """从响应中构建Cookie字符串"""
        cookie_jar = SimpleCookie()
        for header in cls._get_set_cookie_headers(response):
            if header:
                cookie_jar.load(header)

        if cookie_jar:
            return "; ".join([f"{item.key}={item.value}" for item in cookie_jar.values()])

        if response.cookies:
            return "; ".join([f"{key}={value}" for key, value in response.cookies.items()])

        return ""

    def _build_headers(self, url_path: str, referer: str, extra_headers: Optional[Dict[str, str]] = None) -> Dict[str, str]:
        """构建通用请求头"""
        timestamp = str(int(time.time() * 1000))
        sw8_data = self.get_sw8(url_path)
        sw8_code = sw8_data.get("code") if isinstance(sw8_data, dict) else ""

        headers = self.default_headers.copy()
        headers.update({
            "timestamp": timestamp,
            "signature": self.generate_signature(timestamp, self.SYS_CODE),
            "sw8": sw8_code,
            "referer": referer,
        })

        if extra_headers:
            headers.update(extra_headers)

        return headers

    def _post_json(self, url_path: str, data: Dict[str, Any], referer: str, error_message: str, extra_headers: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
        """发送POST请求并返回JSON结果"""
        url = f"{self.base_url}{url_path}"
        headers = self._build_headers(url_path, referer, extra_headers)
        try:
            response = self.session.post(url, headers=headers, json=data, timeout=30)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            return {
                "success": False,
                "error": str(e),
                "message": error_message
            }

    def query_point_task_and_sign(self, channel_type: str = "1", device_id: str = None) -> Dict[str, Any]:
        """
        查询积分任务和签到信息

        Args:
            channel_type: 渠道类型，默认为"1"
            device_id: 设备ID，如果不提供则使用初始化时的device_id

        Returns:
            Dict: API响应结果
        """
        url_path = "/mcs-mimp/commonPost/~memberNonactivity~integralTaskStrategyService~queryPointTaskAndSignFromES"
        data = {
            "channelType": channel_type,
            "deviceId": device_id or self.device_id
        }
        referer = "https://mcs-mimp-web.sf-express.com/superWelfare?citycode=&cityname=&tab=0"
        return self._post_json(url_path, data, referer, "请求失败")

    def finish_task(self, task_code: str) -> Dict[str, Any]:
        """
        完成任务接口

        Args:
            task_code: 任务代码

        Returns:
            Dict: API响应结果
        """
        url_path = "/mcs-mimp/commonPost/~memberEs~taskRecord~finishTask"
        data = {
            "taskCode": task_code
        }
        extra_headers = {
            "Accept-Encoding": "gzip, deflate, br, zstd",
            "Content-Type": "application/json",
        }
        referer = "https://mcs-mimp-web.sf-express.com/home?from=qqjrwzx515&WC_AC_ID=111&WC_REPORT=111"
        return self._post_json(url_path, data, referer, "完成任务请求失败", extra_headers)

    def fetch_tasks_reward(self, channel_type: str = "1", device_id: str = None) -> Dict[str, Any]:
        """
        获取任务奖励接口

        Args:
            channel_type: 渠道类型，默认为"1"
            device_id: 设备ID，如果不提供则使用初始化时的device_id

        Returns:
            Dict: API响应结果
        """
        url_path = "/mcs-mimp/commonNoLoginPost/~memberNonactivity~integralTaskStrategyService~fetchTasksReward"
        data = {
            "channelType": channel_type,
            "deviceId": device_id or self.device_id
        }
        extra_headers = {
            "Accept-Encoding": "gzip, deflate, br, zstd",
            "Content-Type": "application/json",
        }
        referer = "https://mcs-mimp-web.sf-express.com/superWelfare?citycode=&cityname=&tab=0"
        return self._post_json(url_path, data, referer, "获取任务奖励请求失败", extra_headers)

    def automatic_sign_fetch_package(self, come_from: str = "vioin", channel_from: str = "SFAPP") -> Dict[str, Any]:
        """
        自动签到获取礼包接口

        Args:
            come_from: 来源，默认为"vioin"
            channel_from: 渠道来源，默认为"SFAPP"

        Returns:
            Dict: API响应结果
        """
        url_path = "/mcs-mimp/commonPost/~memberNonactivity~integralTaskSignPlusService~automaticSignFetchPackage"
        data = {
            "comeFrom": come_from,
            "channelFrom": channel_from
        }
        extra_headers = {
            "Accept": "application/json, text/plain, */*",
            "Accept-Encoding": "gzip, deflate, br, zstd",
            "Content-Type": "application/json",
            "deviceid": self.device_id or "",
            "accept-language": "zh-CN,zh-Hans;q=0.9",
            "priority": "u=3, i",
        }
        referer = (
            "https://mcs-mimp-web.sf-express.com/superWelfare"
            f"?mobile=176****2621&userId={self.user_id}&path=/superWelfare&supportShare=YES&from=appIndex&tab=1"
        )
        return self._post_json(url_path, data, referer, "自动签到获取礼包请求失败", extra_headers)

    def query_user_info(self) -> Dict[str, Any]:
        """
        查询会员积分信息

        Returns:
            Dict: API响应结果
        """
        url_path = "/mcs-mimp/commonPost/~memberIntegral~userInfoService~personalInfoNew"
        data = {}
        extra_headers = {
            "Accept": "application/json, text/plain, */*",
            "Content-Type": "application/json",
            "deviceid": self.device_id or "",
            "priority": "u=3, i",
            "accept-language": "zh-CN,zh-Hans;q=0.9",
            "channel": "appqiandao",
        }
        referer = (
            "https://mcs-mimp-web.sf-express.com/home"
            f"?redirectUri=/myPoints&userId={self.user_id or ''}&from=appqiandao"
        )
        return self._post_json(url_path, data, referer, "查询会员积分信息请求失败", extra_headers)
