#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
cron: 15 7 * * *
new Env('央广网投票');
"""

import os
import sys
import json
import time
import base64
import requests
from datetime import datetime
try:
    from notify import send  # 青龙通知依赖
except:
    print("未安装通知依赖,可以使用 pip install qinglong-notify 安装")
    def send(*args):
        print("通知依赖未安装,将只打印不发送通知")
        print(args)

# 配置类
class Config:
    # 青龙面板拉取后会自动转换为环境变量
    temptokens = os.getenv("CNR_TEMPTOKENS", "").split("&") # 支持多账号,使用&分隔
    object_id = os.getenv("CNR_OBJECT_ID", "141197")  # 投票对象ID
    vote_count = int(os.getenv("CNR_VOTE_COUNT", "5"))  # 每次投票次数
    
    @classmethod
    def check(cls):
        if not cls.temptokens[0]:
            print("未配置 tempToken, 请查看配置说明")
            sys.exit(1)
        return True

class CNRVote:
    def __init__(self):
        self.session = requests.Session()
        self.base_url = "https://voteapi1.cnr.cn"
        self.success_count = 0
        self.fail_count = 0
        
    def vote(self, temptoken):
        """执行投票"""
        headers = {
            "Host": "voteapi1.cnr.cn",
            "appName": "ygw",
            "content-type": "application/json",
            "tempToken": temptoken,
            "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148 MicroMessenger/8.0.53(0x1800352b) NetType/WIFI Language/zh_CN",
            "Referer": "https://servicewechat.com/wx219ee13807f92193/66/page-frame.html"
        }
        
        data = {
            "id": 88,
            "objectId": Config.object_id,
            "t": str(int(time.time()))
        }
        
        try:
            response = self.session.post(
                f"{self.base_url}/sddh2/wechat/vote",
                headers=headers,
                json=data,
                timeout=10
            )
            result = response.json()
            
            if response.status_code == 200:
                if result.get("code") == 200:
                    self.success_count += 1
                    return True, f"投票成功: {result.get('message', 'OK')}"
                else:
                    self.fail_count += 1
                    return False, f"投票失败: {result.get('message', '未知错误')}"
            else:
                self.fail_count += 1
                return False, f"请求失败: HTTP {response.status_code}"
                
        except Exception as e:
            self.fail_count += 1
            return False, f"请求异常: {str(e)}"

    def run(self):
        """运行主函数"""
        msg_list = []
        msg_list.append(f"========= 央广网投票 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} =========")
        
        for index, token in enumerate(Config.temptokens):
            if not token:
                continue
                
            msg_list.append(f"\n开始执行第 {index + 1} 个账号:")
            for i in range(Config.vote_count):
                success, message = self.vote(token)
                msg_list.append(f"第 {i + 1} 次投票: {message}")
                if not success:
                    break
                time.sleep(3)  # 避免投票太快
                
        summary = f"\n执行完成! 成功: {self.success_count} 次, 失败: {self.fail_count} 次"
        msg_list.append(summary)
        
        # 发送通知
        send("央广网投票", "\n".join(msg_list))
        return "\n".join(msg_list)

def main():
    """主入口函数"""
    # 检查配置
    Config.check()
    
    # 执行任务
    voter = CNRVote()
    result = voter.run()
    print(result)
    
if __name__ == "__main__":
    main()