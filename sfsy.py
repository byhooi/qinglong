#!/usr/bin/python3
# -*- coding: utf-8 -*-

"""
new Env('顺丰速运签到');
Cron:"12 */6 * * *";
"""

# 打开小程序或APP-我的-积分, 捉以下几种url之一,把整个url放到变量 sfsyUrl 里,多账号换行分割
# https://mcs-mimp-web.sf-express.com/mcs-mimp/share/weChat/shareGiftReceiveRedirect
# https://mcs-mimp-web.sf-express.com/mcs-mimp/share/app/shareRedirect
# https://mcs-mimp-web.sf-express.com/mcs-mimp/share/weChat/activityRedirect

import hashlib
import json
import os
import random
import time
from datetime import datetime
import requests
from requests.packages.urllib3.exceptions import InsecureRequestWarning
try:
    from notify import send
except:
    # notify.py 不存在时的替代函数
    def send(title, content):
        print(f"\n{title}\n{content}")

# 禁用安全请求警告
requests.packages.urllib3.disable_warnings(InsecureRequestWarning)

# 全局日志变量
send_msg = ''
one_msg = ''

def Log(cont=''):
    """记录日志"""
    global send_msg, one_msg
    print(cont)  # 控制台始终打印所有日志
    
    # 定义需要推送的关键信息
    push_keywords = [
        '账号', '登陆成功',
        '开始执行签到', '今日已签到',
        '当前积分',
        '会员日'
    ]
    
    # 只有包含关键词的信息才记录到推送消息中
    if cont and any(keyword in cont for keyword in push_keywords):
        one_msg += f'{cont}\n'
        send_msg += f'{cont}\n'

inviteId = ['']

class RUN:
    def __init__(self, info, index):
        """初始化账号信息"""
        global one_msg
        one_msg = ''
        split_info = info.split('@')
        url = split_info[0]
        self.send_UID = split_info[-1] if len(split_info) > 1 and "UID_" in split_info[-1] else None
        self.index = index + 1

        self.s = requests.session()
        self.s.verify = False

        self.headers = {
            'Host': 'mcs-mimp-web.sf-express.com',
            'upgrade-insecure-requests': '1',
            'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/98.0.4758.102 Safari/537.36 NetType/WIFI MicroMessenger/7.0.20.1781(0x6700143B) WindowsWechat(0x63090551) XWEB/6945 Flue',
            'accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.9',
            'sec-fetch-site': 'none',
            'sec-fetch-mode': 'navigate',
            'sec-fetch-user': '?1',
            'sec-fetch-dest': 'document',
            'accept-language': 'zh-CN,zh',
            'platform': 'MINI_PROGRAM',
        }

        # 会员日相关属性
        self.member_day_black = False
        self.member_day_red_packet_map = {}
        self.max_level = 8
        self.packet_threshold = 1 << (self.max_level - 1)

        self.login_res = self.login(url)

    def get_deviceId(self, characters='abcdef0123456789'):
        """生成随机设备ID"""
        result = ''
        for char in 'xxxxxxxx-xxxx-xxxx':
            if char == 'x':
                result += random.choice(characters)
            else:
                result += char
        return result

    def login(self, sfurl):
        """登录顺丰账号"""
        try:
            ress = self.s.get(sfurl, headers=self.headers)
            self.user_id = self.s.cookies.get_dict().get('_login_user_id_', '')
            self.phone = self.s.cookies.get_dict().get('_login_mobile_', '')
            self.mobile = self.phone[:3] + "*" * 4 + self.phone[7:] if self.phone else ''
            if self.phone:
                Log(f'👤 账号{self.index}:【{self.mobile}】登陆成功')
                return True
            else:
                Log(f'❌ 账号{self.index}获取用户信息失败')
                return False
        except Exception as e:
            Log(f'❌ 登录异常: {str(e)}')
            return False

    def getSign(self):
        """生成请求签名"""
        timestamp = str(int(time.time() * 1000))
        token = 'wwesldfs29aniversaryvdld29'
        sysCode = 'MCS-MIMP-CORE'
        data = f'token={token}×tamp={timestamp}&sysCode={sysCode}'
        signature = hashlib.md5(data.encode()).hexdigest()
        data = {
            'sysCode': sysCode,
            'timestamp': timestamp,
            'signature': signature
        }
        self.headers.update(data)
        return data

    def do_request(self, url, data=None, req_type='post', max_retries=3):
        """发送HTTP请求"""
        self.getSign()
        for retry_count in range(max_retries):
            try:
                if req_type.lower() == 'get':
                    enkelt = self.s.get(url, headers=self.headers, timeout=30)
                elif req_type.lower() == 'post':
                    response = self.s.post(url, headers=self.headers, json=data or {}, timeout=30)
                else:
                    raise ValueError(f'Invalid req_type: {req_type}')

                response.raise_for_status()
                return response.json()

            except (requests.exceptions.RequestException, json.JSONDecodeError) as e:
                Log(f'❌ 请求失败 ({retry_count + 1}/{max_retries}): {str(e)}')
                if retry_count < max_retries - 1:
                    time.sleep(2)
                    continue
                return {'success': False, 'errorMessage': str(e)}
        return {'success': False, 'errorMessage': 'All retries failed'}

    def sign(self):
        """执行签到任务"""
        Log('🎯 开始执行签到')
        json_data = {"comeFrom": "vioin", "channelFrom": "WEIXIN"}
        url = 'https://mcs-mimp-web.sf-express.com/mcs-mimp/commonPost/~memberNonactivity~integralTaskSignPlusService~automaticSignFetchPackage'
        response = self.do_request(url, data=json_data)
        if response.get('success'):
            count_day = response.get('obj', {}).get('countDay', 0)
            if response.get('obj', {}).get('integralTaskSignPackageVOList'):
                packet_name = response["obj"]["integralTaskSignPackageVOList"][0]["packetName"]
                Log(f'✨ 签到成功，获得【{packet_name}】，本周累计签到【{count_day + 1}】天')
            else:
                Log(f'📝 今日已签到，本周累计签到【{count_day + 1}】天')
        else:
            Log(f'❌ 签到失败！原因：{response.get("errorMessage", "未知错误")}')

    
    def get_SignTaskList(self, end=False):
        """获取签到任务列表"""
        Log('🎯 开始获取签到任务列表' if not end else '💰 查询最终积分')
        json_data = {"channelType": "1", "deviceId": self.get_deviceId()}
        url = 'https://mcs-mimp-web.sf-express.com/mcs-mimp/commonPost/~memberNonactivity~integralTaskStrategyService~queryPointTaskAndSignFromES'
        response = self.do_request(url, data=json_data)
        if response.get('success') and response.get('obj'):
            totalPoint = response["obj"]["totalPoint"]
            Log(f'💰 {"执行前" if not end else "当前"}积分：【{totalPoint}】')
            if not end:
                for task in response["obj"]["taskTitleLevels"]:
                    self.taskId = task["taskId"]
                    self.taskCode = task["taskCode"]
                    self.strategyId = task["strategyId"]
                    self.title = task["title"]
                    status = task["status"]
                    skip_title = ['用行业模板寄件下单', '去新增一个收件偏好', '参与积分活动']
                    if status == 3:
                        Log(f'✨ {self.title}-已完成')
                        continue
                    if self.title in skip_title:
                        Log(f'⏭️ {self.title}-跳过')
                        continue
                    self.doTask()
                    time.sleep(2)
                    self.receiveTask()

    def doTask(self):
        """完成签到任务"""
        Log(f'🎯 开始去完成【{self.title}】任务')
        json_data = {"taskCode": self.taskCode}
        url = 'https://mcs-mimp-web.sf-express.com/mcs-mimp/commonRoutePost/memberEs/taskRecord/finishTask'
        response = self.do_request(url, data=json_data)
        Log(f'✨ 【{self.title}】任务-{"已完成" if response.get("success") else response.get("errorMessage", "失败")}')

    def receiveTask(self):
        """领取签到任务奖励"""
        Log(f'🎁 开始领取【{self.title}】任务奖励')
        json_data = {
            "strategyId": self.strategyId,
            "taskId": self.taskId,
            "taskCode": self.taskCode,
            "deviceId": self.get_deviceId()
        }
        url = 'https://mcs-mimp-web.sf-express.com/mcs-mimp/commonPost/~memberNonactivity~integralTaskStrategyService~fetchIntegral'
        response = self.do_request(url, data=json_data)
        Log(f'✨ 【{self.title}】任务奖励-{"领取成功" if response.get("success") else response.get("errorMessage", "失败")}')













    def member_day_index(self):
        """执行会员日活动"""
        Log('🎭 会员日活动')
        invite_user_id = random.choice([invite for invite in inviteId if invite != self.user_id])
        payload = {'inviteUserId': invite_user_id}
        url = 'https://mcs-mimp-web.sf-express.com/mcs-mimp/commonPost/~memberNonactivity~memberDayIndexService~index'
        response = self.do_request(url, data=payload)
        if response.get('success'):
            lottery_num = response.get('obj', {}).get('lotteryNum', 0)
            can_receive_invite_award = response.get('obj', {}).get('canReceiveInviteAward', False)
            if can_receive_invite_award:
                self.member_day_receive_invite_award(invite_user_id)
            self.member_day_red_packet_status()
            Log(f'🎁 会员日可以抽奖{lottery_num}次')
            for _ in range(lottery_num):
                self.member_day_lottery()
            if self.member_day_black:
                return
            self.member_day_task_list()
            if self.member_day_black:
                return
            self.member_day_red_packet_status()
        else:
            error_message = response.get('errorMessage', '无返回')
            Log(f'📝 查询会员日失败: {error_message}')
            if '没有资格参与活动' in error_message:
                self.member_day_black = True
                Log('📝 会员日任务风控')

    def member_day_receive_invite_award(self, invite_user_id):
        """领取会员日邀请奖励"""
        payload = {'inviteUserId': invite_user_id}
        url = 'https://mcs-mimp-web.sf-express.com/mcs-mimp/commonPost/~memberNonactivity~memberDayIndexService~receiveInviteAward'
        response = self.do_request(url, data=payload)
        if response.get('success'):
            product_name = response.get('obj', {}).get('productName', '空气')
            Log(f'🎁 会员日奖励: {product_name}')
        else:
            error_message = response.get('errorMessage', '无返回')
            Log(f'📝 领取会员日奖励失败: {error_message}')
            if '没有资格参与活动' in error_message:
                self.member_day_black = True
                Log('📝 会员日任务风控')

    def member_day_lottery(self):
        """会员日抽奖"""
        url = 'https://mcs-mimp-web.sf-express.com/mcs-mimp/commonPost/~memberNonactivity~memberDayLotteryService~lottery'
        response = self.do_request(url, data={})
        if response.get('success'):
            product_name = response.get('obj', {}).get('productName', '空气')
            Log(f'🎁 会员日抽奖: {product_name}')
        else:
            error_message = response.get('errorMessage', '无返回')
            Log(f'📝 会员日抽奖失败: {error_message}')
            if '没有资格参与活动' in error_message:
                self.member_day_black = True
                Log('📝 会员日任务风控')

    def member_day_task_list(self):
        """获取会员日任务列表"""
        payload = {'activityCode': 'MEMBER_DAY', 'channelType': 'MINI_PROGRAM'}
        url = 'https://mcs-mimp-web.sf-express.com/mcs-mimp/commonPost/~memberNonactivity~activityTaskService~taskList'
        response = self.do_request(url, data=payload)
        if response.get('success'):
            task_list = response.get('obj', [])
            for task in task_list:
                if not isinstance(task, dict):
                    continue
                status = task.get('status')
                task_type = task.get('taskType')
                task_code = task.get('taskCode')
                
                if not all([status, task_type, task_code]):
                    continue
                    
                if status == 1:
                    if self.member_day_black:
                        return
                    self.member_day_fetch_mix_task_reward(task)
                elif status == 2 and task_type not in [
                    'SEND_SUCCESS', 'INVITEFRIENDS_PARTAKE_ACTIVITY', 'OPEN_SVIP',
                    'OPEN_NEW_EXPRESS_CARD', 'OPEN_FAMILY_CARD', 'CHARGE_NEW_EXPRESS_CARD', 'INTEGRAL_EXCHANGE'
                ]:
                    rest_finish_time = task.get('restFinishTime', 1)
                    for _ in range(rest_finish_time):
                        if self.member_day_black:
                            return
                        self.member_day_finish_task(task)
        else:
            error_message = response.get('errorMessage', '无返回')
            Log(f'📝 查询会员日任务失败: {error_message}')
            if '没有资格参与活动' in error_message:
                self.member_day_black = True
                Log('📝 会员日任务风控')

    def member_day_finish_task(self, task):
        """完成会员日任务"""
        if not isinstance(task, dict):
            return
            
        task_code = task.get('taskCode')
        task_name = task.get('taskName', '未知任务')
        
        if not task_code:
            Log(f'📝 任务[{task_name}]缺少taskCode，跳过')
            return
            
        payload = {'taskCode': task_code}
        url = 'https://mcs-mimp-web.sf-express.com/mcs-mimp/commonPost/~memberEs~taskRecord~finishTask'
        response = self.do_request(url, data=payload)
        if response.get('success'):
            Log(f'📝 完成会员日任务[{task_name}]: 成功')
            self.member_day_fetch_mix_task_reward(task)
        else:
            error_message = response.get('errorMessage', '无返回')
            Log(f'📝 完成会员日任务[{task_name}]: {error_message}')
            if '没有资格参与活动' in error_message:
                self.member_day_black = True
                Log('📝 会员日任务风控')

    def member_day_fetch_mix_task_reward(self, task):
        """领取会员日任务奖励"""
        payload = {'taskType': task['taskType'], 'activityCode': 'MEMBER_DAY', 'channelType': 'MINI_PROGRAM'}
        url = 'https://mcs-mimp-web.sf-express.com/mcs-mimp/commonPost/~memberNonactivity~activityTaskService~fetchMixTaskReward'
        response = self.do_request(url, data=payload)
        Log(f'🎁 领取会员日任务[{task["taskName"]}]: {"成功" if response.get("success") else response.get("errorMessage", "失败")}')

    def member_day_receive_red_packet(self, hour):
        """领取会员日红包"""
        payload = {'receiveHour': hour}
        url = 'https://mcs-mimp-web.sf-express.com/mcs-mimp/commonPost/~memberNonactivity~memberDayTaskService~receiveRedPacket'
        response = self.do_request(url, data=payload)
        Log(f'🎁 会员日领取{hour}点红包-{"成功" if response.get("success") else response.get("errorMessage", "失败")}')

    def member_day_red_packet_status(self):
        """查询会员日红包状态"""
        url = 'https://mcs-mimp-web.sf-express.com/mcs-mimp/commonPost/~memberNonactivity~memberDayPacketService~redPacketStatus'
        response = self.do_request(url, data={})
        if response.get('success'):
            packet_list = response.get('obj', {}).get('packetList', [])
            self.member_day_red_packet_map = {packet['level']: packet['count'] for packet in packet_list}
            for level in range(1, self.max_level):
                count = self.member_day_red_packet_map.get(level, 0)
                while count >= 2:
                    self.member_day_red_packet_merge(level)
                    count -= 2
            packet_summary = [f"[{level}]X{count}" for level, count in self.member_day_red_packet_map.items() if count > 0]
            Log(f"📝 会员日合成列表: {', '.join(packet_summary) or '无红包'}")
            if self.member_day_red_packet_map.get(self.max_level):
                Log(f"🎁 会员日已拥有[{self.max_level}级]红包X{self.member_day_red_packet_map[self.max_level]}")
                self.member_day_red_packet_draw(self.max_level)
            else:
                remaining_needed = sum(1 << (int(level) - 1) for level, count in self.member_day_red_packet_map.items() if count > 0)
                remaining = self.packet_threshold - remaining_needed
                Log(f"📝 会员日距离[{self.max_level}级]红包还差: [1级]红包X{remaining}")
        else:
            error_message = response.get('errorMessage', '无返回')
            Log(f'📝 查询会员日合成失败: {error_message}')
            if '没有资格参与活动' in error_message:
                self.member_day_black = True
                Log('📝 会员日任务风控')

    def member_day_red_packet_merge(self, level):
        """合成会员日红包"""
        payload = {'level': level, 'num': 2}
        url = 'https://mcs-mimp-web.sf-express.com/mcs-mimp/commonPost/~memberNonactivity~memberDayPacketService~redPacketMerge'
        response = self.do_request(url, data=payload)
        if response.get('success'):
            Log(f'🎁 会员日合成: [{level}级]红包X2 -> [{level + 1}级]红包')
            self.member_day_red_packet_map[level] = self.member_day_red_packet_map.get(level, 0) - 2
            self.member_day_red_packet_map[level + 1] = self.member_day_red_packet_map.get(level + 1, 0) + 1
        else:
            Log(f'📝 会员日合成[{level}级]红包失败: {response.get("errorMessage", "无返回")}')

    def member_day_red_packet_draw(self, level):
        """提取会员日红包"""
        payload = {'level': str(level)}
        url = 'https://mcs-mimp-web.sf-express.com/mcs-mimp/commonPost/~memberNonactivity~memberDayPacketService~redPacketDraw'
        response = self.do_request(url, data=payload)
        if response.get('success'):
            coupon_names = [item['couponName'] for item in response.get('obj', [])] or ['空气']
            Log(f"🎁 会员日提取[{level}级]红包: {', '.join(coupon_names)}")
        else:
            Log(f"📝 会员日提取[{level}级]红包失败: {response.get('errorMessage', '无返回')}")

    def main(self):
        """主执行逻辑"""
        if not self.login_res:
            return False
        time.sleep(random.uniform(1, 3))

        # 执行签到任务
        self.sign()
        self.get_SignTaskList()
        self.get_SignTaskList(True)

        # 会员日任务
        if 26 <= datetime.now().day <= 28:
            self.member_day_index()
        else:
            Log('📝 未到指定时间不执行会员日任务')

        self.sendMsg()
        return True

    def sendMsg(self, help=False):
        """收集消息,不单独推送"""
        pass  # 改为空方法,只收集消息,不推送



if __name__ == '__main__':
    """主程序入口"""
    APP_NAME = '顺丰速运'
    ENV_NAME = 'sfsyUrl'
    token = os.getenv(ENV_NAME)
    tokens = token.split('\n') if token else []
    if tokens:
        Log(f"🚚 共获取到{len(tokens)}个账号")
        for index, infos in enumerate(tokens):
            Log(f"==================================\n🚚 处理账号{index + 1}")
            RUN(infos, index).main()
            
        # 所有账号处理完成后统一推送
        try:
            title = "🚚 顺丰速运"
            send(title, send_msg)
            Log("✅ 推送成功")
        except Exception as e:
            Log(f"❌ 推送失败: {str(e)}")
    else:
        Log("❌ 未获取到sfsyUrl环境变量")