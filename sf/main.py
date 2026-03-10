#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
new Env('顺丰快递积分任务');
cron: 25 8 * * *
"""

"""
顺丰快递积分任务自动化脚本
环境变量: sf_jifen (JSON格式)
格式示例: {"accounts":[{"account_name":"账号1","sign":"xxx","channel":"yyy","device_id":"zzz"},{"account_name":"账号2","sign":"xxx","channel":"yyy","device_id":"zzz"}]}
多账号在 accounts 数组中添加即可

依赖: pip install PyExecJS (需要 Node.js 运行时)
"""

import json
import logging
import os
import random
import re
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import parse_qs, unquote, urlparse

import requests
from requests.packages.urllib3.exceptions import InsecureRequestWarning
requests.packages.urllib3.disable_warnings(InsecureRequestWarning)

# 添加项目根目录到Python路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

try:
    from sendNotify import send
except:
    def send(title, content):
        print(f"\n{title}\n{content}")

# 导入API模块（当前目录）
from api import SFExpressAPI, ShareLoginInfo

# 延迟时间常量配置 (秒)
DELAY_BETWEEN_ACCOUNTS = (3, 8)      # 账号间切换延迟
DELAY_AFTER_SIGN = (2, 5)           # 签到后延迟
DELAY_BETWEEN_TASKS = (10, 15)      # 任务间延迟

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SFAccountConfig:
    """顺丰账号配置"""

    account_name: str
    sign: str
    user_agent: str
    channel: str
    device_id: str

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SFAccountConfig":
        """从配置字典构建账号配置"""
        account_name = data.get("account_name") or "未命名账号"
        sign = data.get("sign") or ""
        user_agent = data.get("user_agent") or ""
        channel = data.get("channel") or ""
        device_id = data.get("device_id") or ""

        missing_fields = []
        if not sign:
            missing_fields.append("sign")
        if not channel:
            missing_fields.append("channel")
        if not device_id:
            missing_fields.append("device_id")

        if missing_fields:
            missing_text = "、".join(missing_fields)
            raise ValueError(f"账号【{account_name}】缺少必填字段: {missing_text}")

        return cls(
            account_name=account_name,
            sign=sign,
            user_agent=user_agent,
            channel=channel,
            device_id=device_id
        )


def load_accounts():
    """
    从环境变量加载账号配置
    支持两种格式:
    1. 旧格式: 换行分隔的URL (兼容旧版 sfsyUrl)
    2. 新格式: JSON {"accounts":[...]}
    """
    env_value = os.getenv('sfsyUrl', '')
    if not env_value:
        return []

    env_value = env_value.strip()

    # 尝试JSON格式
    if env_value.startswith('{'):
        try:
            config = json.loads(env_value)
            raw_accounts = config.get('accounts', [])
            accounts = []
            for raw in raw_accounts:
                try:
                    accounts.append(SFAccountConfig.from_dict(raw))
                except ValueError as e:
                    logger.error(f"账号配置异常: {e}")
            return accounts
        except json.JSONDecodeError:
            print("❌ 环境变量 sfsyUrl JSON格式错误")
            return []

    # 旧格式: 换行分隔的URL，每行一个账号
    urls = [u.strip() for u in env_value.split('\n') if u.strip()]
    accounts = []
    for i, url in enumerate(urls):
        accounts.append(SFAccountConfig(
            account_name=f"账号{i + 1}",
            sign=url,
            user_agent="",
            channel="appqiandao",
            device_id=""
        ))
    logger.info(f"从旧格式 sfsyUrl 加载了 {len(accounts)} 个账号")
    return accounts


class SFTasksManager:
    """顺丰积分任务管理器"""

    def __init__(self):
        self.site_name = "顺丰速运"
        self.task_summary = []

    def get_task_list(self, sf_api: SFExpressAPI) -> List[Dict[str, Any]]:
        """获取顺丰积分任务列表"""
        try:
            result = sf_api.query_point_task_and_sign()
            task_list = result.get("obj", {}).get("taskTitleLevels", [])
            logger.info(f"获取到 {len(task_list)} 个任务")
            return task_list
        except Exception as e:
            logger.error(f"获取任务列表失败: {e}")
            return []

    @staticmethod
    def extract_task_code(task: Dict[str, Any]) -> str:
        """从任务信息中提取task_code"""
        task_code = task.get("taskCode")
        if task_code:
            return task_code

        button_redirect = task.get("buttonRedirect", "")
        if not button_redirect:
            return ""

        decoded_redirect = unquote(button_redirect)
        ug_param = ""

        if "_ug_view_param=" in decoded_redirect:
            ug_param = decoded_redirect.split("_ug_view_param=", 1)[1]
        else:
            for candidate in (button_redirect, decoded_redirect):
                try:
                    query = urlparse(candidate).query
                    if not query:
                        continue
                    params = parse_qs(query)
                    if params.get("_ug_view_param"):
                        ug_param = params["_ug_view_param"][0]
                        break
                except Exception:
                    continue

        if not ug_param:
            return ""

        ug_param = unquote(ug_param).strip()

        try:
            ug_data = json.loads(ug_param)
            if isinstance(ug_data, dict):
                return ug_data.get("taskId", "")
        except json.JSONDecodeError:
            match = re.search(r'"taskId"\s*:\s*"([^"]+)"', ug_param)
            if match:
                return match.group(1)

        return ""

    @staticmethod
    def _url_login(sign_url: str, user_agent: str = None) -> Optional[ShareLoginInfo]:
        """
        使用完整URL直接登录（兼容旧版 sfsyUrl 格式）
        直接访问URL获取cookies，和旧版 sfsy.py 的登录方式一致
        """
        from urllib.parse import unquote as url_unquote

        # URL解码处理
        if '//' not in sign_url:
            sign_url = url_unquote(sign_url)
            if '3A//' in sign_url:
                sign_url = url_unquote(sign_url)

        headers = {
            'Host': 'mcs-mimp-web.sf-express.com',
            'upgrade-insecure-requests': '1',
            'user-agent': user_agent or 'Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148 mediaCode=SFEXPRESSAPP-iOS-ML',
            'accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.9',
            'sec-fetch-site': 'none',
            'sec-fetch-mode': 'navigate',
            'sec-fetch-user': '?1',
            'sec-fetch-dest': 'document',
            'accept-language': 'zh-CN,zh',
            'platform': 'MINI_PROGRAM',
        }

        try:
            session = requests.Session()
            session.verify = False
            response = session.get(sign_url, headers=headers, timeout=30)
            cookies_dict = session.cookies.get_dict()

            user_id = cookies_dict.get('_login_user_id_', '')
            phone = cookies_dict.get('_login_mobile_', '')

            if not user_id:
                return None

            # 构建cookie字符串
            cookie_str = "; ".join([f"{k}={v}" for k, v in cookies_dict.items()])

            logger.info(f"URL登录成功，手机号: {phone[:3]}****{phone[7:]}" if phone else "URL登录成功")

            return ShareLoginInfo(
                success=True,
                user_id=user_id,
                token="",
                cookies=cookie_str,
                raw=cookies_dict,
                error=""
            )
        except Exception as e:
            logger.error(f"URL登录失败: {e}")
            return None

    def fetch_login_info(self, account: SFAccountConfig) -> Optional[ShareLoginInfo]:
        """获取账号登录信息（自动识别 URL 格式或 sign 格式）"""
        sign = account.sign

        # 如果是完整URL，使用URL直接登录（兼容旧版sfsyUrl）
        if '://' in sign or 'mcs-mimp' in sign:
            logger.info(f"[{account.account_name}] 检测到完整URL，使用URL直接登录")
            login_info = self._url_login(sign, account.user_agent or None)
        else:
            logger.info(f"[{account.account_name}] 使用sign参数登录")
            login_info = SFExpressAPI.share_login(
                sign=sign,
                user_agent=account.user_agent or None
            )

        if not login_info or not login_info.success:
            error_msg = login_info.error if login_info else "登录返回为空"
            logger.warning(f"[{account.account_name}] 登录失败: {error_msg}")
            return None

        if not login_info.user_id or not login_info.cookies:
            logger.warning(f"[{account.account_name}] 登录返回数据不完整")
            return None

        logger.info(f"[{account.account_name}] 登录成功")
        return login_info

    def auto_sign_and_fetch_package(self, sf_api: SFExpressAPI, account_name: str) -> Dict[str, Any]:
        """自动签到并获取礼包"""
        try:
            logger.info(f"[{account_name}] 开始执行自动签到...")
            result = sf_api.automatic_sign_fetch_package()

            if result.get("success"):
                obj = result.get("obj", {})
                has_finish_sign = obj.get("hasFinishSign", 0)
                count_day = obj.get("countDay", 0)
                package_list = obj.get("integralTaskSignPackageVOList", [])

                if has_finish_sign == 1:
                    logger.info(f"[{account_name}] 今日已完成签到，连续签到 {count_day} 天")
                else:
                    logger.info(f"[{account_name}] 签到成功！连续签到 {count_day} 天")

                if package_list:
                    for package in package_list:
                        package_name = package.get("commodityName", "未知礼包")
                        logger.info(f"[{account_name}] 获得: {package_name}")

                return {'success': True, 'days': count_day, 'already_signed': has_finish_sign == 1}
            else:
                error_msg = result.get("errorMessage", "未知错误")
                logger.warning(f"[{account_name}] 签到失败: {error_msg}")
                return {'success': False, 'days': 0, 'error': error_msg}

        except Exception as e:
            logger.error(f"[{account_name}] 自动签到时发生错误: {e}")
            return {'success': False, 'days': 0, 'error': str(e)}

    def process_single_task(self, task: Dict[str, Any], sf_api: SFExpressAPI, account_name: str) -> Dict[str, Any]:
        """处理单个任务"""
        task_title = task.get('title', '未知任务')
        task_code = self.extract_task_code(task)

        if not task_code:
            logger.warning(f"[{account_name}] 任务 {task_title} 缺少任务代码，跳过")
            return {'title': task_title, 'success': False, 'points': 0}

        try:
            finish_result = sf_api.finish_task(task_code)
            if finish_result and finish_result.get('success'):
                logger.info(f"[{account_name}] 任务 {task_title} 完成成功")

                reward_result = sf_api.fetch_tasks_reward()
                points = 0
                if reward_result and reward_result.get('success'):
                    obj_list = reward_result.get('obj', [])
                    if isinstance(obj_list, list):
                        for item in obj_list:
                            points += item.get('point', 0)

                return {'title': task_title, 'success': True, 'points': points}
            else:
                logger.warning(f"[{account_name}] 任务 {task_title} 完成失败")
                return {'title': task_title, 'success': False, 'points': 0}
        except Exception as e:
            logger.error(f"[{account_name}] 执行任务 {task_title} 时发生错误: {e}")
            return {'title': task_title, 'success': False, 'points': 0}

    def process_account_tasks(self, account: SFAccountConfig) -> Dict[str, Any]:
        """处理单个账号的所有任务"""
        account_name = account.account_name

        account_stat = {
            'account_name': account_name,
            'sign_success': False,
            'sign_days': 0,
            'total_tasks': 0,
            'completed_tasks': 0,
            'total_points': 0,
            'available_points': None,
            'tasks': []
        }

        if not account.sign:
            logger.error(f"账号 {account_name} 缺少sign，跳过")
            account_stat['error'] = '配置信息不完整'
            return account_stat

        logger.info(f"开始处理账号: {account_name}")

        try:
            login_info = self.fetch_login_info(account)
            if login_info is None:
                account_stat['error'] = '分享登录失败'
                return account_stat

            sf_api = SFExpressAPI(
                cookies=login_info.cookies,
                device_id=account.device_id,
                user_id=login_info.user_id,
                user_agent=account.user_agent,
                channel=account.channel
            )

            # 签到
            sign_result = self.auto_sign_and_fetch_package(sf_api, account_name)
            account_stat['sign_success'] = sign_result.get('success', False)
            account_stat['sign_days'] = sign_result.get('days', 0)

            sign_delay = random.uniform(*DELAY_AFTER_SIGN)
            time.sleep(sign_delay)

            # 获取任务列表
            task_list = self.get_task_list(sf_api)

            if task_list:
                for i, task in enumerate(task_list, 1):
                    if task.get("taskPeriod") != "D":
                        continue

                    account_stat['total_tasks'] += 1

                    if task.get("status") == 3:
                        continue

                    delay_time = random.uniform(*DELAY_BETWEEN_TASKS)
                    time.sleep(delay_time)

                    task_result = self.process_single_task(task, sf_api, account_name)
                    account_stat['tasks'].append(task_result)

                    if task_result.get('success'):
                        account_stat['completed_tasks'] += 1
                        account_stat['total_points'] += task_result.get('points', 0)

            # 查询积分
            user_info_result = sf_api.query_user_info()
            if user_info_result.get("success"):
                available_points = user_info_result.get("obj", {}).get("availablePoints")
                account_stat['available_points'] = available_points
                logger.info(f"[{account_name}] 当前积分: {available_points}")

        except Exception as e:
            logger.error(f"处理账号 {account_name} 时发生错误: {e}")
            account_stat['error'] = str(e)

        return account_stat

    def run_all_accounts(self, accounts: List[SFAccountConfig]) -> None:
        """执行所有账号的任务处理"""
        if not accounts:
            logger.warning("没有配置的账号，程序退出")
            return

        logger.info(f"开始执行任务，共 {len(accounts)} 个账号")

        for i, account in enumerate(accounts, 1):
            logger.info(f"\n{'='*60}")
            logger.info(f"处理第 {i}/{len(accounts)} 个账号")
            logger.info(f"{'='*60}")

            account_stat = self.process_account_tasks(account)
            self.task_summary.append(account_stat)

            if i < len(accounts):
                account_delay = random.uniform(*DELAY_BETWEEN_ACCOUNTS)
                time.sleep(account_delay)

        logger.info("所有账号任务处理完成")

    def build_notification(self, start_time: datetime, end_time: datetime):
        """构建推送通知内容"""
        duration = (end_time - start_time).total_seconds()

        total_accounts = len(self.task_summary)
        total_sign_success = sum(1 for stat in self.task_summary if stat.get('sign_success'))

        title = f"{self.site_name}积分任务完成 ✅"

        content_parts = []
        for stat in self.task_summary:
            account_name = stat.get('account_name', '未知')
            if stat.get('error'):
                content_parts.append(f"❌ [{account_name}] {stat['error']}")
            else:
                sign_status = "✅" if stat.get('sign_success') else "❌"
                sign_days = stat.get('sign_days', 0)
                completed = stat.get('completed_tasks', 0)
                available_points = stat.get('available_points')
                line = f"{sign_status} [{account_name}] 签到{sign_days}天 | 任务{completed}个"
                if available_points is not None:
                    line += f" | 积分{available_points}"
                content_parts.append(line)

        content_parts.append(f"\n⏱️ 耗时: {int(duration)}秒")
        return title, "\n".join(content_parts)


def main():
    """主函数"""
    start_time = datetime.now()
    logger.info("=" * 60)
    logger.info(f"顺丰快递积分任务开始 - {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info("=" * 60)

    accounts = load_accounts()

    if not accounts:
        print("❌ 未获取到 sf_jifen 环境变量或其中没有账号信息")
        return 1

    manager = SFTasksManager()

    try:
        manager.run_all_accounts(accounts)

        end_time = datetime.now()
        logger.info(f"顺丰快递积分任务完成 - 耗时 {int((end_time - start_time).total_seconds())} 秒")

        if manager.task_summary:
            try:
                title, content = manager.build_notification(start_time, end_time)
                send(title, content)
                logger.info("✅ 推送通知发送成功")
            except Exception as e:
                logger.error(f"❌ 推送通知失败: {str(e)}")

        return 0

    except Exception as e:
        end_time = datetime.now()
        logger.error(f"任务执行异常: {str(e)}", exc_info=True)

        try:
            send(
                f"顺丰快递积分任务异常 ❌",
                f"❌ 错误: {str(e)}\n⏱️ 耗时: {int((end_time - start_time).total_seconds())}秒"
            )
        except Exception:
            pass

        return 1


if __name__ == '__main__':
    exit_code = main()
    sys.exit(exit_code)
