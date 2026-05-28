"""
华润通文体未来荟 API 接口
"""
import os
import requests


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

        try:
            response = requests.post(url, json=data, headers=self.headers, timeout=20)
            response.raise_for_status()
            return self.normalize_response(response.json(), "打卡成功")
        except Exception as e:
            return {"success": False, "msg": f"请求失败: {str(e)}"}
