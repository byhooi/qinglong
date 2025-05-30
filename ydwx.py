#!/usr/bin/python3
# -- coding: utf-8 -- 
# -------------------------------
# @Author : github@wd210010 https://github.com/wd210010/just_for_happy
# @Time : 2023/2/27 13:23
# -------------------------------
"""
cron: "2 8 * * *"
new Env('一点万象签到');
"""
import requests
import time
import hashlib
import json
import os
from sendNotify import send

# 登录后搜索 https://app.mixcapp.com/mixc/gateway 域名随意一个 请求体里面的deviceParams，token 多账号填多个单引号里面 用英文逗号隔开
# 青龙变量 ydwx_deviceParams ydwx_token
ydwx_deviceParams = os.getenv("ydwx_deviceParams").split('&')
ydwx_token = os.getenv("ydwx_token").split('&')

print(f'共配置了{len(ydwx_deviceParams)}个账号')
log = []
for i in range(len(ydwx_deviceParams)):
    print(f'*****第{str(i+1)}个账号*****')
    timestamp = str(int(round(time.time() * 1000)))
    md5 = hashlib.md5()
    sig = f'action=mixc.app.memberSign.sign&apiVersion=1.0&appId=68a91a5bac6a4f3e91bf4b42856785c6&appVersion=3.53.0&deviceParams={ydwx_deviceParams[i]}&imei=2333&mallNo=8602A101&osVersion=12.0.1&params=eyJtYWxsTm8iOiIyMDAxNCJ9&platform=h5&timestamp={timestamp}&token={ydwx_token[i]}&P@Gkbu0shTNHjhM!7F'
    md5.update(sig.encode('utf-8'))
    sign = md5.hexdigest()
    url = 'https://app.mixcapp.com/mixc/gateway'
    headers = {
        'Host': 'app.mixcapp.com',
        'Connection': 'keep-alive',
        'Content-Length': '564',
        'Accept': 'application/json, text/plain, */*',
        'Origin': 'https://app.mixcapp.com',
        'User-Agent': 'Mozilla/5.0 (Linux; Android 10; PCAM00 Build/QKQ1.190918.001; wv) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/77.0.3865.92 Mobile Safari/537.36/MIXCAPP/3.42.2/AnalysysAgent/Hybrid',
        'Sec-Fetch-Mode': 'cors',
        'Content-Type': 'application/x-www-form-urlencoded',
        'X-Requested-With': 'com.crland.mixc',
        'Sec-Fetch-Site': 'same-origin',
        'Referer': 'https://app.mixcapp.com/m/m-8602A101/signIn?showWebNavigation=true&timestamp=1676906528979&appVersion=3.53.0&mallNo=8602A101',
        'Accept-Encoding': 'gzip, deflate',
        'Accept-Language': 'zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7'
    }
    data = f'mallNo=8602A101&appId=68a91a5bac6a4f3e91bf4b42856785c6&platform=h5&imei=2333&appVersion=3.53.0&osVersion=12.0.1&action=mixc.app.memberSign.sign&apiVersion=1.0&timestamp={timestamp}&deviceParams={ydwx_deviceParams[i]}&token={ydwx_token[i]}&params=eyJtYWxsTm8iOiIyMDAxNCJ9&sign={sign}'
    html = requests.post(url=url, headers=headers, data=data)
    result = f'帐号{i+1}签到结果:' + json.loads(html.text)['message']
    print(result)
    log.append(result)

log2 = '\n'.join(log)
send('一点万象签到结果', log2)
