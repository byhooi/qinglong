#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
H5登录抓包 ：https://cloud.huaruntong.cn/web/online/?mFrom=fastLogin#/signIn?utm_source=hrt&utm_medium=flzx&utm_content=qd0228&utm_campaign=qd0228&inviteCode=2d9e1a77d725404b864c7e79fdf7fc33
或者华润通APP 域名https://mid.huaruntong.cn/api/user/memberinfo/appBootstarp 返回文本里的token
以上都是抓token
变量
export hrthd='token'
多号@或换行隔开

配合之前的一点万象积分签到

依赖: requests, pycryptodome
"""

import os
import json
import time
import uuid
import hashlib
from Crypto.Cipher import AES
from Crypto.PublicKey import RSA
from Crypto.Cipher import PKCS1_OAEP
import base64
import requests
from datetime import datetime

# 全局变量
Notify = 1  # 0为关闭通知，1为打开通知,默认为1
debug = 0   # 0为关闭调试，1为打开调试,默认为0

class Huaruntong:
    def __init__(self):
        self.msg = ''
        self.hrthd = os.getenv('hrthd', '')
        self.hrthdArr = self.get_accounts()
        
    def get_accounts(self):
        if '@' in self.hrthd:
            return self.hrthd.split('@')
        elif '\n' in self.hrthd:
            return self.hrthd.strip().split('\n')
        elif self.hrthd:
            return [self.hrthd]
        else:
            print('⚠️ 未发现有效账号')
            return []

    def create_guid(self):
        return str(uuid.uuid4())

    def md5(self, text):
        return hashlib.md5(text.encode()).hexdigest()

    def get_auth_params(self):
        app_id = "API_AUTH_H5"
        timestamp = int(time.time() * 1000)
        nonce = self.create_guid()
        
        # 按字母顺序排序并拼接
        sign_str = ''.join(sorted([
            app_id,
            "1c6120fd-5ad3-4c2d-8cb7-b87a707f416d",
            str(timestamp),
            nonce
        ]))
        
        return {
            "appid": app_id,
            "nonce": nonce,
            "timestamp": timestamp,
            "signature": self.md5(sign_str)
        }

    def question_get(self):
        url = 'https://mid.huaruntong.cn/api/question/get'
        data = {
            "auth": self.get_auth_params(),
            "num": 1
        }
        
        headers = {
            'Content-Type': 'application/json;charset=UTF-8',
            'Host': 'mid.huaruntong.cn',
            'Origin': 'https://cloud.huaruntong.cn',
            'Referer': 'https://cloud.huaruntong.cn/',
            'User-Agent': 'Mozilla/5.0 (Linux; Android 10; PCAM00) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/77.0.3865.92 Mobile Safari/537.36 hrtbrowser/5.3.5',
            'x-Hrt-Mid-Appid': 'API_AUTH_WEB'
        }
        
        try:
            response = requests.post(url, json=data, headers=headers)
            result = response.json()
            
            if result['code'] == "S0A00000":
                print(result['msg'])
                question = result['data'][0]
                return question['id'], question['no'], question['keywords']
            else:
                print(result['msg'])
                return None, None, None
                
        except Exception as e:
            print(f"请求异常: {str(e)}")
            return None, None, None

    def question_count(self, question_id):
        url = 'https://mid.huaruntong.cn/api/question/count'
        data = {
            "auth": self.get_auth_params(),
            "id": question_id,
            "status": 1
        }
        
        headers = {
            'Content-Type': 'application/json;charset=UTF-8',
            'Host': 'mid.huaruntong.cn',
            'Origin': 'https://cloud.huaruntong.cn',
            'Referer': 'https://cloud.huaruntong.cn/',
            'User-Agent': 'Mozilla/5.0 (Linux; Android 10; PCAM00) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/77.0.3865.92 Mobile Safari/537.36 hrtbrowser/5.3.5',
            'x-Hrt-Mid-Appid': 'API_AUTH_WEB'
        }
        
        try:
            response = requests.post(url, json=data, headers=headers)
            result = response.json()
            print(result['msg'] if 'msg' in result else '请求失败')
            return result['code'] == "S0A00000"
        except Exception as e:
            print(f"请求异常: {str(e)}")
            return False

    def save_question_signin(self, question_no, token):
        url = 'https://mid.huaruntong.cn/api/points/saveQuestionSignin'
        transaction_uuid = self.create_guid()
        
        data = {
            "answerResult": 1,
            "questionId": question_no,
            "channelId": "APP",
            "merchantCode": "1641000001532",
            "storeCode": "qiandaosonjifen",
            "sysId": "T0000001",
            "transactionUuid": transaction_uuid,
            "inviteCode": "2d9e1a77d725404b864c7e79fdf7fc33",
            "token": token,
            "apiPath": "/api/points/saveQuestionSignin",
            "appId": "API_AUTH_WEB",
            "timestamp": int(time.time() * 1000)
        }
        
        headers = {
            'Content-Type': 'application/json;charset=UTF-8',
            'Host': 'mid.huaruntong.cn',
            'Origin': 'https://cloud.huaruntong.cn',
            'Referer': 'https://cloud.huaruntong.cn/',
            'User-Agent': 'Mozilla/5.0 (Linux; Android 10; PCAM00) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/77.0.3865.92 Mobile Safari/537.36 hrtbrowser/5.3.5',
            'x-Hrt-Mid-Appid': 'API_AUTH_WEB'
        }
        
        try:
            response = requests.post(url, json=self.sign_data(data), headers=headers)
            result = response.json()
            print(json.dumps(result, ensure_ascii=False))
            return result['code'] == "S0A00000"
        except Exception as e:
            print(f"请求异常: {str(e)}")
            return False

    def get_flop_reward(self, token):
        url = 'https://mid.huaruntong.cn/api/points/getFlopReward'
        transaction_uuid = self.create_guid()
        
        data = {
            "channelId": "APP",
            "merchantCode": "1641000001532",
            "storeCode": "qiandaosonjifen",
            "sysId": "T0000001",
            "sysCode": "T0000016",
            "transactionUuid": transaction_uuid,
            "num": 1,
            "token": token,
            "apiPath": "/api/points/getFlopReward",
            "appId": "API_AUTH_WEB",
            "timestamp": int(time.time() * 1000)
        }
        
        headers = {
            'Content-Type': 'application/json;charset=UTF-8',
            'Host': 'mid.huaruntong.cn',
            'Origin': 'https://cloud.huaruntong.cn',
            'Referer': 'https://cloud.huaruntong.cn/',
            'User-Agent': 'Mozilla/5.0 (Linux; Android 10; PCAM00) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/77.0.3865.92 Mobile Safari/537.36 hrtbrowser/5.3.5',
            'x-Hrt-Mid-Appid': 'API_AUTH_WEB'
        }
        
        try:
            response = requests.post(url, json=self.sign_data(data), headers=headers)
            result = response.json()
            print(json.dumps(result, ensure_ascii=False))
            return result['code'] == "S0A00000"
        except Exception as e:
            print(f"请求异常: {str(e)}")
            return False

    def sign_data(self, data):
        """签名加密数据"""
        secret = "c274fc67-19f9-47ba-bb84-585a2e3a1f6a"
        pub_key = """-----BEGIN PUBLIC KEY-----
MIGfMA0GCSqGSIb3DQEBAQUAA4GNADCBiQKBgQDuAiqDmvn9Rf15o21qkDxN0rUf
ZsX6rVBrtfgY6tamN2Yn+1D3eHZJuKNlucyqeBr6nmfN2srYAX+oyCXr5vWwFclj
PuWh8aSASqyk7MfbAv5Q4VqYS7lsYUQRdw4plZG0NASDeBvHWi3lsHjGfNb7iUvg
rk312EDfBHtRgDvB0QIDAQAB
-----END PUBLIC KEY-----"""

        # 生成签名
        sorted_items = sorted(data.items())
        sign_str = '&'.join(f"{k}={json.dumps(v) if isinstance(v, (dict, list)) else v}" for k, v in sorted_items)
        signature = hashlib.md5((sign_str).encode()).hexdigest()
        data['signature'] = signature

        # 生成16位随机密钥
        aes_key = ''.join(chr(ord('a') + i % 26) for i in range(16))
        
        # AES加密
        cipher = AES.new(aes_key.encode(), AES.MODE_CBC, b'\x00' * 16)
        raw = json.dumps(data).encode()
        # PKCS7 padding
        length = 16 - (len(raw) % 16)
        raw += bytes([length]) * length
        encrypted_data = base64.b64encode(cipher.encrypt(raw)).decode()

        # RSA加密AES密钥
        rsa_key = RSA.import_key(pub_key)
        cipher_rsa = PKCS1_OAEP.new(rsa_key)
        encrypted_key = base64.b64encode(cipher_rsa.encrypt(aes_key.encode())).decode()

        return {
            'key': encrypted_key,
            'data': encrypted_data
        }

    def run(self):
        print(f"\n=================== 共找到 {len(self.hrthdArr)} 个账号 ===================")
        
        for index, token in enumerate(self.hrthdArr, 1):
            print(f"\n==== 开始【第 {index} 个账号】====\n")
            
            # 获取问题
            qid, qno, keywords = self.question_get()
            if qid:
                # 提交问题计数
                self.question_count(qid)
                # 保存签到
                self.save_question_signin(qno, token)
                # 获取翻牌奖励
                self.get_flop_reward(token)

def main():
    hrt = Huaruntong()
    hrt.run()

if __name__ == "__main__":
    main()