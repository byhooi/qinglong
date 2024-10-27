#!/usr/bin/python3
# -- coding: utf-8 --
# -------------------------------
# @Author : github@wd210010 https://github.com/wd210010/only_for_happly
# @Time : 2024/05/321 9:23
# -------------------------------
"""
cron: "3 8 * * *"
new Env('999会员中心');
"""
import requests
import time
import json
import random
import os
from datetime import datetime

# 导入sendNotify函数
from sendNotify import send

#微信扫码 https://pic.imgdb.cn/item/664c0ef9d9c307b7e9fabfc4.png 这个图片(走下我邀请) 注册登录后抓mc.999.com.cn域名请求头里面的Authorization 变量名为jjjck 多号用#分割
#export jjjck='807b3cc1-3473-4baa-b038-********'

jjck = os.getenv("jjjck").split('#')

today = datetime.now().date().strftime('%Y-%m-%d')

for i in range(len(jjck)):
    Authorization = jjck[i]
    headers = {
        "Host": "mc.999.com.cn",
        "Connection": "keep-alive",
        "locale": "zh_CN",
        "Authorization": Authorization,
        "content-type": "application/json",
        "Accept-Encoding": "gzip,compress,br,deflate",
        "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 16_4_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148 MicroMessenger/8.0.48(0x18003030) NetType/WIFI Language/zh_CN"
    }

    try:
        resp_user = requests.get('https://mc.999.com.cn/zanmall_diy/ma/personal/user/info', headers=headers)
        phone = json.loads(resp_user.text)['data']['phone']
        print(f'开始账号: {phone} 打卡')
        
        # ... 其他任务代码 ...

        total_points = 0
        success_messages = []
        error_messages = []

        # 打卡任务
        for task in checkInCodeList:
            try:
                # ... 打卡任务的代码 ...
            except Exception as e:
                error_messages.append(f"打卡任务 {task['checkInMeaning']} 失败: {str(e)}")

        # 阅读文章任务
        for i in range(5):
            try:
                # ... 阅读文章任务的代码 ...
            except Exception as e:
                error_messages.append(f"第 {i+1} 次阅读文章失败: {str(e)}")

        # 体检任务
        for i in range(3):
            try:
                # ... 体检任务的代码 ...
            except Exception as e:
                error_messages.append(f"第 {i+1} 次体检任务失败: {str(e)}")

        # 获取总积分
        try:
            resp = requests.get('https://mc.999.com.cn/zanmall_diy/ma/personal/point/pointInfo', headers=headers)
            totalpoints = json.loads(resp.text)['data']
            print(f'当前拥有总积分:{totalpoints}')
            
            # 生成推送消息
            push_message = f"账号: {phone}\n今日获得总积分: {total_points}\n当前总积分: {totalpoints}\n\n成功信息:\n" + "\n".join(success_messages)
            if error_messages:
                push_message += f"\n\n失败信息:\n" + "\n".join(error_messages)
            
            # 使用sendNotify函数进行推送
            send("999会员中心签到结果", push_message)
        except Exception as e:
            print(f"获取总积分失败: {str(e)}")
            send("999会员中心", f"账号 {phone} 获取总积分失败，可能需要检查")

    except Exception as e:
        print(str(e))
        msg = f'账号 {phone} 可能失效！错误信息: {str(e)}'
        send("999会员中心", msg)

    print('*'*30)
