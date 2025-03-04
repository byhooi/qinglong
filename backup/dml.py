'''
达美乐,开一把游戏抓取openid的值。
一定要在我的奖品那绑定好手机号！
变量名1：dmlck，多账号用@隔开。备注信息用#隔开 如openid的值#大帅比
变量名2：pzid 填活动id这次是volcano

'''
"""
cron: "30 10 * * *"
new Env('达美乐披萨');
"""
import os
import time
import requests
import json
import notify
message = ''
# from dotenv import load_dotenv
# load_dotenv()
accounts = os.getenv('dmlck')
pzid = os.getenv('pzid')
if accounts is None:
    print('你没有填入ck，咋运行？')
else:
    accounts_list = os.environ.get('dmlck').split('@')

    num_of_accounts = len(accounts_list)

    print(f"获取到 {num_of_accounts} 个账号")

    for i, account in enumerate(accounts_list, start=1):

        values = account.split('#')
        Cookie = values[0]
        account_no = values[1] if len(values) > 1 else ""
        print(f"\n=======开始执行账号{i} {account_no}=======")
        url = f"https://game.dominos.com.cn/spring/v2/game/gameDone"
        payload = f"openid={Cookie}&score=t5%2Bhzvt2h6jpwH7D%2BJkNWvT%2Fb6J2mWDStIgcC4ZSrhkqPEqXtcDrCC9LVFvQLRtGkeVQ7z0W6RYqcXxmeXi9596r4HZ1Pt0E5PpRLYWZZL%2BXQXEpyc0WX8c4ewMqQymjBgGMcSRFp3aaLTDNaRLvLcnnh2t5PpL70pW%2B7LcM8tnhtP1J2rLaTe0Dno7%2B9Qf32LuHUS%2BUXCgQ6YbCJwj%2BWrmhP1zbFvGthkH6HB9lkI9mS%2F%2BY9582WQeFREMF9OflJpRVjgPd1%2FPWFRWKWrl%2F7VGztrHpQLZvLQ9HRINK99cN4FBBvPVkkHxyACadINkuFwxgC9ODPYInHXXpn5iElg%3D%3D&tempId=null"
        headers = {
            'User-Agent': "Mozilla/5.0 (iPhone; CPU iPhone OS 18_3_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148 MicroMessenger/8.0.56(0x18003835) NetType/WIFI Language/zh_CN",
            'Accept-Encoding': "gzip,compress,br,deflate",
            'Content-Type': "application/x-www-form-urlencoded",
            'Authorization': "Bearer eyJhbGciOiJIUzUxMiIsInR5cCI6IkpXVCJ9.eyJ1aWQiOiI5MjI2MTI1MDMwNDExMzgwOTQ3IiwiZXhwIjoxNzQxMTQ3MDY5fQ.0eHxowo4d8DRBlvL05hUCrT-7fofkF365UW2ZBErbXhPg5qJ0dkOVc2epI2idwXF1v_io7XlNmsAebP_Hn3fRA",
            'Referer': "https://servicewechat.com/wx887bf6ad752ca2f3/72/page-frame.html"
        }

        while True:
            shrurl = f"https://game.dominos.com.cn/spring/v2/game/getGameSharing"
            params = {'openid': Cookie}
            res = requests.get(shrurl, params=params, headers=headers).json()
            if res['content']['sharingNum'] >= 3:
                print(f'账号{i}分享已达上限，开始抽奖')
                break
            time.sleep(1)  # 添加延迟避免请求过快
        
        # 计算抽奖次数：初始3次 + (分享次数 * 2)
        draw_times = 3 + (res['content']['sharingNum'] * 2)
        print(f'账号{i}可抽奖{draw_times}次')
        
        for a in range(draw_times):
            response = requests.post(url, data=payload, headers=headers)
            response = response.json()
            if response["statusCode"] == 0:
                prize = response['content']['name']
                print(f"\n账号{i}\n{prize}")
                if '一等奖' in prize:
                    message += f"\n账号{i}中得：{prize}"
                    try:
                        notify.send('达美乐一等奖通知', f"恭喜账号{i}中得：{prize}")
                    except Exception as e:
                        print(f'推送失败：{e}')
            if response["statusCode"] != 0:
                print(response)
                err = response['errorMessage']
                print(f'\n账号{i}\n {err}')
                message += f"\n账号{i}出错：{err}"
                break