"""
华润通文体未来荟 API 接口
"""
import os
import ssl
import sys
import time

import requests
import urllib3
from requests.adapters import HTTPAdapter

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

# OpenSSL 3.x 默认拒绝服务器的旧版重协商 (UNSAFE_LEGACY_RENEGOTIATION_DISABLED)
# 该服务器偶发触发旧版重协商，需要显式放行。
# SSL_OP_LEGACY_SERVER_CONNECT 在 OpenSSL 1.1.1+ 中恒为 0x4，直接使用原始值，
# 避免依赖 ssl.OP_LEGACY_SERVER_CONNECT 常量（Python < 3.10 未暴露该常量）。
SSL_OP_LEGACY_SERVER_CONNECT = 0x4


class LegacyRenegotiationAdapter(HTTPAdapter):
    """允许服务端 legacy renegotiation 的 HTTP 适配器。

    该服务器（或其负载均衡）偶发触发旧版重协商，OpenSSL 3.x 默认拒绝。
    直连和代理两条连接路径都要使用带 SSL_OP_LEGACY_SERVER_CONNECT 的 context。
    """

    @staticmethod
    def _legacy_context():
        ctx = ssl.create_default_context()
        ctx.options |= SSL_OP_LEGACY_SERVER_CONNECT
        return ctx

    def init_poolmanager(self, *args, **kwargs):
        kwargs["ssl_context"] = self._legacy_context()
        return super().init_poolmanager(*args, **kwargs)

    def proxy_manager_for(self, proxy, **proxy_kwargs):
        proxy_kwargs.setdefault("ssl_context", self._legacy_context())
        return super().proxy_manager_for(proxy, **proxy_kwargs)


class WenTiWeiLaiHuiAPI:
    """文体未来荟API接口类"""

    def __init__(self, token, mobile=None, user_agent=None, project_uuid=None):
        """
        初始化API
        :param token: 认证token
        :param mobile: 手机号（用于显示，当前新签到接口不需要）
        :param user_agent: 用户代理字符串
        :param project_uuid: 项目 UUID
        """
        self.token = token
        self.mobile = mobile
        self.base_url = os.getenv("wentiweilaihui_base_url", "https://wlhmobile.crland.com.cn").rstrip("/")
        self.project_uuid = (
            project_uuid
            or os.getenv("wentiweilaihui_project_uuid")
            or "3a59e62a07f811f1bec0aeefcf2e061a"
        )
        self.user_agent = user_agent or 'Mozilla/5.0 (iPhone; CPU iPhone OS 26_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148 MicroMessenger/8.0.73(0x18004935) NetType/WIFI Language/zh_CN'
        self.headers = {
            'User-Agent': self.user_agent,
            'Content-Type': 'application/json',
            'Authorization': self.format_authorization(self.token),
            'Referer': 'https://servicewechat.com/wx020209beec4251e0/43/page-frame.html',
        }
        # 复用同一会话，并对该服务器放行旧版重协商
        self.session = requests.Session()
        self.session.mount("https://", LegacyRenegotiationAdapter())

    @staticmethod
    def format_authorization(token):
        """兼容只填 token 和填完整 Authorization 两种配置。"""
        token = (token or "").strip()
        if not token:
            return ""
        if token.lower().startswith(("wechat ", "bearer ")):
            return token
        return f"Wechat {token}"

    @staticmethod
    def normalize_response(data, default_success_msg="请求成功"):
        """统一新旧接口返回结构，方便 main.py 判断。"""
        if not isinstance(data, dict):
            return {"success": False, "msg": "接口响应不是 JSON", "raw": data}
        if data.get("success") is True:
            return data
        if str(data.get("code")) == "200":
            data["success"] = True
            result = data.get("result")
            data["msg"] = result if isinstance(result, str) else (data.get("text") or default_success_msg)
            return data
        data["success"] = False
        data["msg"] = data.get("msg") or data.get("message") or data.get("text") or "接口请求失败"
        return data

    def sign_in(self):
        """
        签到接口
        :return: 接口响应数据
        """
        url = f"{self.base_url}/marketing/client/task/daily/sign-in"
        data = {
            "custom": {
                "catch": True
            },
            "projectUuid": self.project_uuid
        }

        # 该服务器偶发 TLS 重协商失败，重试 3 次兜底
        last_error = None
        for attempt in range(1, 4):
            try:
                response = self.session.post(url, json=data, headers=self.headers, timeout=20)
                response.raise_for_status()
                return self.normalize_response(response.json(), "打卡成功")
            except Exception as e:
                last_error = e
                if attempt == 1:
                    # 输出环境诊断，便于排查 SSL 类故障
                    proxies = {k: v for k, v in os.environ.items() if k.lower().endswith("_proxy")}
                    print(f"ℹ️  诊断: Python {sys.version.split()[0]}, urllib3 {urllib3.__version__}, "
                          f"adapter={type(self.session.get_adapter('https://')).__name__}, "
                          f"env_proxy={proxies or '无'}")
                if attempt < 3:
                    print(f"⚠️  签到请求失败(第{attempt}次): {e}，稍后重试...")
                    time.sleep(2 * attempt)

        return {"success": False, "msg": f"请求失败: {last_error}"}
