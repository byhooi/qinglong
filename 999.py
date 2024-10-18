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
        checkInCodeList = [
            {
                "checkInCode": "mtbbs",
                "checkInMeaning": "每天八杯水"
            },
            {
                "checkInCode": "zs",
                "checkInMeaning": "早睡"
            },
            {
                "checkInCode": "ydswfz",
                "checkInMeaning": "运动15分钟"
            },
            {
                "checkInCode": "zq",
                "checkInMeaning": "早起"
            }
        ]

        total_points = 0
        success_messages = []

        # # 请求体（JSON）
        for i in range(len(checkInCodeList)):
            data = {
                "type": "daily_health_check_in",
                "params": {
                    "checkInCode": f"{checkInCodeList[i]['checkInCode']}",
                    "checkInTime": today
                }
            }
            Meaning = checkInCodeList[i]['checkInMeaning']
            # 发送POST请求
            try:
                response = requests.post('https://mc.999.com.cn/zanmall_diy/ma/client/pointTaskClient/finishTask',
                                         headers=headers, json=data)
                result = json.loads(response.text)['data']
                point = result['point']
                if result['success'] == True:
                    message = f'打卡内容{Meaning}---打卡完成 获得积分{point}'
                    print(message)
                    success_messages.append(message)
                    total_points += point
                else:
                    print(f'打卡内容{Meaning}---请勿重复打卡')
            except:
                print('请检查抓包是否准确 个别青龙版本运行不了')
                continue

        try:
            resp = requests.get('https://mc.999.com.cn/zanmall_diy/ma/personal/point/pointInfo', headers=headers)
            totalpoints = json.loads(resp.text)['data']
            print(f'当前拥有总积分:{totalpoints}')
            
            # 生成推送消息
            push_message = f"账号: {phone}\n今日获得总积分: {total_points}\n当前总积分: {totalpoints}\n\n详细信息:\n" + "\n".join(success_messages)
            
            # 使用sendNotify函数进行推送
            send("999会员中心签到成功", push_message)
        except:
            continue
    except Exception as e:
        print(str(e))
        msg =f'账号可能失效！'
        # 使用sendNotify函数进行推送
        send("999会员中心", msg)
        continue
    print('*'*30)
