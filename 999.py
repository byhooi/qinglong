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

        #阅读文章
        try:
            print('开始阅读任务')
            for i in range(3):  # 每天只有3次阅读机会
                data_read = {"type":"explore_health_knowledge","params":{"articleCode":str(random.randint(1, 20))}}
                resp_read = requests.post('https://mc.999.com.cn/zanmall_diy/ma/client/pointTaskClient/finishTask',
                                                 headers=headers, json=data_read)
                resp_data = json.loads(resp_read.text)
                
                print(f'第{i+1}次阅读响应: {resp_data}')
                
                if 'data' in resp_data and resp_data['data'] and isinstance(resp_data['data'].get('point'), (int, str)):
                    point = int(resp_data['data']['point'])
                    message = f'第{i+1}次阅读成功！获得{point}积分'
                    print(message)
                    success_messages.append(message)
                    total_points += point
                    print(f'等待30秒后进行下一次阅读...')
                    time.sleep(30)  # 每次阅读都等待30秒
                else:
                    print('今日阅读任务已完成或达到上限')
                    break
        except Exception as e:
            print(f'阅读任务出错：{str(e)}')

        #体检
        try:
            print('开始体检任务')
            h_test = {"gender":"1","age":"17","height":"188","weight":"50","waist":"55","hip":"55",
                     # ... 体检数据保持不变 ...
                    }
            resp_htest = requests.post('https://mc.999.com.cn/zanmall_diy/ma/health/add',
                                      headers=headers, json=h_test)
            referNo = json.loads(resp_htest.text)['data']['referNo']
            print(f'体检编号: {referNo}')
            
            data_h_test = {"type":"complete_health_testing","params":{"testCode":referNo}}
            resp_h_test = requests.post('https://mc.999.com.cn/zanmall_diy/ma/client/pointTaskClient/finishTask',
                                      headers=headers, json=data_h_test)
            resp_data = json.loads(resp_h_test.text)
            
            # 打印响应内容以便调试
            print(f'体检任务响应: {resp_data}')
            
            if 'data' in resp_data and resp_data['data'] and isinstance(resp_data['data'].get('point'), (int, str)):
                point = int(resp_data['data']['point'])
                message = f'体检成功！获得{point}积分'
                print(message)
                success_messages.append(message)
                total_points += point
            else:
                print('今日体检任务已完成或达到上限')
        except Exception as e:
            print(f'体检任务出错：{str(e)}')

        # 获取总积分并推送消息
        try:
            resp = requests.get('https://mc.999.com.cn/zanmall_diy/ma/personal/point/pointInfo', headers=headers)
            totalpoints = json.loads(resp.text)['data']
            print(f'当前拥有总积分:{totalpoints}')
            
            if not success_messages:
                push_message = f"账号: {phone}\n今日所有任务已完成\n当前总积分: {totalpoints}"
            else:
                push_message = (f"账号: {phone}\n"
                              f"今日获得总积分: {total_points}\n"
                              f"当前总积分: {totalpoints}\n"
            
            send("999会员中心签到结果", push_message)
        except Exception as e:
            print(f'获取总积分失败：{str(e)}')
            if not success_messages:
                push_message = f"账号: {phone}\n今日所有任务已完成"
            else:
                push_message = (f"账号: {phone}\n"
                              f"今日获得总积分: {total_points}\n"
            send("999会员中心签到结果", push_message)


    except Exception as e:
        error_msg = f'账号 {phone if "phone" in locals() else "未知"} 运行出错：{str(e)}'
        print(error_msg)
        if 'success_messages' in locals() and success_messages:
            error_msg += f"\n\n已完成的任务:\n" + "\n".join(success_messages)
        send("999会员中心运行异常", error_msg)
        continue

    print('*'*30)
