# -*- coding: utf-8 -*-
'''
new Env('wskey转换');
Cron:"58 21,9 * * *";

京东 wskey 本地转换: 读取青龙环境变量 JD_WSCK, 转换为 JD_COOKIE 并写回青龙面板 (仅能在青龙容器内运行)
环境变量:
  JD_WSCK             必填, 多账号用 & 或换行分隔, 单个格式 pin=xxx;wskey=xxx;
  QL_PORT             青龙端口, 默认 5700
  WSKEY_SLEEP         每个账号之间的间隔秒数, 默认 10
  WSKEY_TRY_COUNT     转换失败重试次数, 默认 1
  WSKEY_UPDATE_HOUR   设置后改为按小时定期刷新 (不再请求京东接口检查有效性), 非数字时按 23 小时
  WSKEY_DISCHECK      设置后不检查现有 JD_COOKIE 有效性, 每次都重新转换
  WSKEY_AUTO_DISABLE  设置后 wskey 失效时只推送提醒, 不禁用对应的 JD_COOKIE
  WSKEY_SEND=disable  关闭推送
  WSKEY_DEBUG         输出调试日志
'''
import base64
import hashlib
import hmac
import json
import logging
import os
import random
import re
import socket
import struct
import sys
import time
import uuid

WSKEY_MODE = 0
# 0 = Default / 1 = Debug!

DEBUG_MODE = "WSKEY_DEBUG" in os.environ or bool(WSKEY_MODE)  # 判断调试模式变量
logging.basicConfig(level=logging.DEBUG if DEBUG_MODE else logging.INFO, format='%(message)s')
logger = logging.getLogger(__name__)  # 主模块
if DEBUG_MODE:
    logger.debug("\nDEBUG模式开启!\n")  # 消息输出

try:
    import requests  # 导入HTTP模块
except Exception as e:
    logger.info(str(e) + "\n缺少requests模块, 请执行命令：pip3 install requests\n")  # 日志输出
    sys.exit(1)  # 退出脚本
os.environ['no_proxy'] = '*'  # 禁用代理
requests.packages.urllib3.disable_warnings()  # 抑制错误

# 脚本位于 jd/ 子目录, 推送模块 sendNotify.py 在仓库根目录, 需要把根目录加入模块搜索路径
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)
try:
    from sendNotify import send  # 导入项目根目录的 sendNotify 推送模块
except Exception as err:
    logger.debug(str(err))  # 调试日志输出
    logger.info("未找到 sendNotify.py, 通知仅输出到日志")  # 标准日志输出

    def send(title, content):  # 降级处理: 无推送模块时仅打印, 避免 ql_send 报 NameError
        print(f"\n{title}\n{content}")


def env_int(name, default, minimum=0):
    """读取整数型环境变量, 非数字或小于下限时返回默认值"""
    value = os.environ.get(name, "")
    if value.isdigit() and int(value) >= minimum:
        return int(value)
    return default


WSKEY_UPDATE_BOOL = bool(os.environ.get("WSKEY_UPDATE_HOUR"))  # 设置后按小时定期刷新, 转换结果附带 __time 时间戳
WSKEY_AUTO_DISABLE = bool(os.environ.get("WSKEY_AUTO_DISABLE"))  # 设置后失效账号只推送提醒, 不禁用 JD_COOKIE
push_msgs = []  # 统一推送: 收集所有账号的重要信息, 结束时一次性推送


def ttotp(key):
    key = base64.b32decode(key.upper() + '=' * ((8 - len(key)) % 8))
    counter = struct.pack('>Q', int(time.time() / 30))
    mac = hmac.new(key, counter, 'sha1').digest()
    offset = mac[-1] & 0x0f
    binary = struct.unpack('>L', mac[offset:offset + 4])[0] & 0x7fffffff
    return str(binary)[-6:].zfill(6)


def sign_core(par):
    arr = [0x37, 0x92, 0x44, 0x68, 0xA5, 0x3D, 0xCC, 0x7F, 0xBB, 0xF, 0xD9, 0x88, 0xEE, 0x9A, 0xE9, 0x5A]
    key2 = b"80306f4370b39fd5630ad0529f77adb6"
    arr1 = [0 for _ in range(len(par))]
    for i in range(len(par)):
        r0 = int(par[i])
        r2 = arr[i & 0xf]
        r4 = int(key2[i & 7])
        r0 = r2 ^ r0
        r0 = r0 ^ r4
        r0 = r0 + r2
        r2 = r2 ^ r0
        r1 = int(key2[i & 7])
        r2 = r2 ^ r1
        arr1[i] = r2 & 0xff
    return bytes(arr1)

def get_sign(functionId, body, uuid, client, clientVersion, st, sv):
    all_arg = "functionId=%s&body=%s&uuid=%s&client=%s&clientVersion=%s&st=%s&sv=%s" % (
        functionId, body, uuid, client, clientVersion, st, sv)
    ret_bytes = sign_core(str.encode(all_arg))
    info = hashlib.md5(base64.b64encode(ret_bytes)).hexdigest()
    return info

def base64Encode(string):
    string1 = "KLMNOPQRSTABCDEFGHIJUVWXYZabcdopqrstuvwxefghijklmnyz0123456789+/"
    string2 = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/"
    return base64.b64encode(string.encode("utf-8")).decode('utf-8').translate(str.maketrans(string1, string2))

def base64Decode(string):
    string1 = "KLMNOPQRSTABCDEFGHIJUVWXYZabcdopqrstuvwxefghijklmnyz0123456789+/"
    string2 = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/"
    stringbase = base64.b64decode(string.translate(str.maketrans(string1, string2))).decode('utf-8')
    return stringbase

def genJDUA():
    st = round(time.time() * 1000)
    aid = base64Encode(''.join(str(uuid.uuid4()).split('-'))[16:])
    oaid = base64Encode(''.join(str(uuid.uuid4()).split('-'))[16:])
    ua = 'jdapp;android;11.1.4;;;appBuild/98176;ef/1;ep/{"hdid":"JM9F1ywUPwflvMIpYPok0tt5k9kW4ArJEU3lfLhxBqw=","ts":%s,"ridx":-1,"cipher":{"sv":"CJS=","ad":"%s","od":"%s","ov":"CzO=","ud":"%s"},"ciphertype":5,"version":"1.2.0","appname":"com.jingdong.app.mall"};Mozilla/5.0 (Linux; Android 12; M2102K1C Build/SKQ1.220303.001; wv) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/97.0.4692.98 Mobile Safari/537.36' % (st, aid, oaid, aid)
    return ua

def genParams():
    suid = ''.join(str(uuid.uuid4()).split('-'))[16:]
    buid = base64Encode(suid)
    st = round(time.time() * 1000)
    sv = random.choice(["102", "111", "120"])
    ep = json.dumps({
        "hdid": "JM9F1ywUPwflvMIpYPok0tt5k9kW4ArJEU3lfLhxBqw=",
        "ts": st,
        "ridx": -1,
        "cipher": {
            "area": "CV8yEJUzXzU0CNG0XzK=",
            "d_model": "JWunCVVidRTr",
            "wifiBssid": "dW5hbw93bq==",
            "osVersion": "CJS=",
            "d_brand": "WQvrb21f",
            "screen": "CJuyCMenCNq=",
            "uuid": buid,
            "aid": buid,
            "openudid": buid
        },
        "ciphertype": 5,
        "version": "1.2.0",
        "appname": "com.jingdong.app.mall"
    }).replace(" ", "")
    body = '{"to":"https%3a%2f%2fplogin.m.jd.com%2fjd-mlogin%2fstatic%2fhtml%2fappjmp_blank.html"}'
    sign = get_sign("genToken", body, suid, "android", "11.1.4", st, sv)
    params = {
        'functionId': 'genToken',
        'clientVersion': '11.1.4',
        'build': '98176',
        'client': 'android',
        'partner': 'google',
        'oaid': suid,
        'sdkVersion': '31',
        'lang': 'zh_CN',
        'harmonyOs': '0',
        'networkType': 'UNKNOWN',
        'uemps': '0-2',
        'ext': '{"prstate": "0", "pvcStu": "1"}',
        'eid': 'eidAcef08121fds9MoeSDdMRQ1aUTyb1TyPr2zKHk5Asiauw+K/WvS1Ben1cH6N0UnBd7lNM50XEa2kfCcA2wwThkxZc1MuCNtfU/oAMGBqadgres4BU',
        'ef': '1',
        'ep': ep,
        'st': st,
        'sign': sign,
        'sv': sv
    }
    return params


def ql_send(text):
    """立即推送一条消息 (WSKEY_SEND=disable 时跳过)"""
    if os.environ.get("WSKEY_SEND") == 'disable':
        return
    try:
        send('WSKEY转换', text)  # 消息发送
    except Exception as err:
        logger.debug(str(err))  # Debug日志输出
        logger.info("通知发送失败")  # 标准日志输出


def push_collect(text):
    """收集账号级消息, 脚本结束后由 push_flush 统一推送一次"""
    push_msgs.append(text)


def push_flush():
    if push_msgs:
        ql_send("\n".join(push_msgs))


# 登录青龙 返回值 token
def get_qltoken(username, password, twoFactorSecret):  # 方法 用于获取青龙 Token
    logger.info("Token失效, 新登陆\n")  # 日志输出
    if not username or not password:
        logger.info("auth 文件中没有用户名密码, 无法自动登录, 请在青龙面板重新登录以刷新 token")
        ql_send('青龙 token 失效且无法自动登录, 请检查面板状态.')
        sys.exit(1)
    body = {
        'username': username,
        'password': password
    }  # HTTP请求载荷
    headers = {
        'Accept': 'application/json',
        'Content-Type': 'application/json'
    }  # HTTP请求头 设置为 Json格式
    try:
        res = requests.post(url=ql_url + 'api/user/login', headers=headers, json=body, timeout=10)  # 新版登录接口
        res_json = res.json()
    except Exception as err:
        logger.debug(str(err))  # Debug日志输出
        logger.info("使用旧版青龙登录接口")
        try:
            res = requests.post(url=ql_url + 'api/login', headers=headers, json=body, timeout=10)
            return res.json()["data"]['token']  # 从返回值中 取出 Token值
        except Exception as err2:
            logger.debug(str(err2))  # Debug日志输出
            logger.info("青龙登录失败, 请检查面板状态!")  # 标准日志输出
            ql_send('青龙登录失败, 请检查面板状态.')
            sys.exit(1)  # 脚本退出
    code = res_json.get("code") if res.status_code == 200 and isinstance(res_json, dict) else None
    if code == 200:
        return res_json["data"]['token']  # 从返回值中 取出 Token值
    if code == 420:  # 青龙开启了两步验证
        if not twoFactorSecret:
            logger.info("青龙开启了两步验证但 auth 文件中没有 twoFactorSecret, 无法自动登录\n")
            sys.exit(1)
        try:
            body['code'] = ttotp(twoFactorSecret)
            res = requests.put(url=ql_url + 'api/user/two-factor/login', headers=headers, json=body, timeout=10)
            res_json = res.json()
        except Exception as err:
            logger.debug(str(err))  # Debug日志输出
            logger.info("两步校验请求异常\n")
            sys.exit(1)
        if res.status_code == 200 and isinstance(res_json, dict) and res_json.get("code") == 200:
            return res_json["data"]['token']
        logger.info("两步校验失败\n")  # 日志输出
        sys.exit(1)
    logger.info(f"青龙登录失败: HTTP {res.status_code} {res.text[:200]}")
    ql_send("青龙登录失败!")
    sys.exit(1)  # 脚本退出


def get_latest_file(files):
    latest_file = None
    latest_mtime = 0
    for file in files:
        try:
            stats = os.stat(file)
            mtime = stats.st_mtime
            if mtime > latest_mtime:
                latest_mtime = mtime
                latest_file = file
        except FileNotFoundError:
            continue
    return latest_file


def read_auth_json(paths):
    """读取 auth.json, 提供用户名/密码/两步验证密钥, 供 token 失效时重新登录"""
    for path in paths:
        try:
            with open(path, "r", encoding="utf-8") as file:
                return json.load(file)
        except (OSError, ValueError) as err:
            logger.debug(str(err))
    return {}


# 返回值 Token
def ql_login() -> str:  # 方法 青龙登录(获取Token 功能同上)
    keyv_file = '/ql/data/db/keyv.sqlite'
    auth_files = ['/ql/data/config/auth.json', '/ql/config/auth.json']
    path = get_latest_file([keyv_file] + auth_files)
    if not path:
        logger.info("没有发现auth文件, 你这是青龙吗???")  # 输出标准日志
        sys.exit(0)  # 脚本退出
    # 新版青龙的 token 保存在 keyv 文件中, 用户名密码仍在 auth.json 里; 两者都读, 候选 token 逐个验证
    auth = read_auth_json(auth_files if path == keyv_file else [path])
    candidates = []
    if path == keyv_file:
        with open(path, "r", encoding="latin1") as file:
            tokens = re.findall(r'"token":"([^"]*)"', file.read())
        if tokens:
            candidates.append(tokens[-1])  # 取最后一个 (最新) token
    if auth.get("token"):
        candidates.append(auth["token"])
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/94.0.4606.71 Safari/537.36 Edg/94.0.992.38'
    }  # 设置用于 HTTP头
    for token in dict.fromkeys(candidates):  # 去重并保持顺序
        headers['Authorization'] = 'Bearer {0}'.format(token)
        try:
            res = requests.get(url=ql_url + 'api/user', headers=headers, timeout=10)  # 验证 token 是否有效
        except Exception as err:
            logger.debug(str(err))
            continue
        if res.status_code == 200:  # 判断 HTTP返回状态码
            return token  # 有效 返回 token
    return get_qltoken(auth.get("username", ""), auth.get("password", ""), auth.get("twoFactorSecret", ""))  # token 为空或失效, 重新登录


# 返回值 list[wskey]
def get_wskey() -> list:  # 方法 获取 wskey值 [系统变量传递]
    if "JD_WSCK" in os.environ:  # 判断 JD_WSCK是否存在于环境变量
        wskey_list = [w.strip() for w in re.split(r'[&\n]', os.environ['JD_WSCK']) if w.strip()]  # 以 & 或换行分割, 忽略空项
        if len(wskey_list) > 0:  # 判断 WSKEY 数量 大于 0 个
            return wskey_list  # 返回 WSKEY [LIST]
        else:
            logger.info("JD_WSCK变量未启用")  # 标准日志输出
            sys.exit(1)  # 脚本退出
    else:
        logger.info("未添加JD_WSCK变量")  # 标准日志输出
        sys.exit(0)  # 脚本退出


# 返回值 bool
def check_ck(ck) -> bool:  # 方法 检查 Cookie有效性 使用变量传递 单次调用
    searchObj = re.search(r'pt_pin=([^;\s]+)', ck, re.M | re.I)  # 正则检索 pt_pin
    if searchObj:  # 真值判断
        pin = searchObj.group(1)  # 取值
    else:
        parts = ck.split(";")
        pin = parts[1] if len(parts) > 1 else ck  # 取值 使用 ; 分割
    if "WSKEY_UPDATE_HOUR" in os.environ:  # 判断 WSKEY_UPDATE_HOUR是否存在于环境变量
        updateHour = env_int("WSKEY_UPDATE_HOUR", 23, minimum=1)  # 更新间隔, 非数字时按 23 小时
        nowTime = time.time()  # 获取时间戳 赋值
        updatedAt = 0.0  # 赋值
        searchObj = re.search(r'__time=([^;\s]+)', ck, re.M | re.I)  # 正则检索 [__time=]
        if searchObj:  # 真值判断
            updatedAt = float(searchObj.group(1))  # 取值 [float]类型
        if nowTime - updatedAt >= (updateHour * 60 * 60) - (10 * 60):  # 判断时间操作
            logger.info(str(pin) + ";即将到期或已过期\n")  # 标准日志输出
            return False  # 返回 Bool类型 False
        else:
            remainingTime = (updateHour * 60 * 60) - (nowTime - updatedAt)  # 时间运算操作
            hour = int(remainingTime / 60 / 60)  # 时间运算操作 [int]
            minute = int((remainingTime % 3600) / 60)  # 时间运算操作 [int]
            logger.info(str(pin) + ";未到期，{0}时{1}分后更新\n".format(hour, minute))  # 标准日志输出
            return True  # 返回 Bool类型 True
    elif "WSKEY_DISCHECK" in os.environ:
        logger.info("不检查账号有效性\n--------------------\n")  # 标准日志输出
        return False  # 返回 Bool类型 False
    else:
        url = 'https://me-api.jd.com/user_new/info/GetJDUserInfoUnion'  # 设置JD_API接口地址
        headers = {
            'Cookie': ck,
            'Referer': 'https://home.m.jd.com/myJd/home.action',
            'user-agent': genJDUA()
        }  # 设置 HTTP头
        try:
            res = requests.get(url=url, headers=headers, verify=False, timeout=10,
                               allow_redirects=False)  # 进行 HTTP请求[GET] 超时 10秒
        except Exception as err:
            logger.debug(str(err))  # 调试日志输出
            logger.info("JD接口错误 请重试或者更换IP")  # 标准日志输出
            return False  # 返回 Bool类型 False
        else:
            if res.status_code == 200:  # 判断 JD_API 接口是否为 200 [HTTP_OK]
                try:
                    code = int(json.loads(res.text)['retcode'])  # 使用 Json模块对返回数据取值 int([retcode])
                except Exception as err:
                    logger.debug(str(err))
                    logger.info("JD接口风控, 建议更换IP或增加间隔时间")
                    return False
                if code == 0:  # 判断 code值
                    logger.info(str(pin) + ";状态正常\n")  # 标准日志输出
                    return True  # 返回 Bool类型 True
                else:
                    logger.info(str(pin) + ";状态失效\n")
                    return False  # 返回 Bool类型 False
            else:
                logger.info("JD接口错误码: " + str(res.status_code))  # 标注日志输出
                return False  # 返回 Bool类型 False


# 返回值 bool jd_ck
def getToken(wskey):  # 方法 获取 Wskey转换使用的 Token 由 JD_API 返回 这里传递 wskey
    params = genParams()
    headers = {
        'cookie': wskey,
        'content-type': 'application/x-www-form-urlencoded; charset=UTF-8',
        'charset': 'UTF-8',
        'accept-encoding': 'br,gzip,deflate',
        'user-agent': genJDUA()
    }  # 设置 HTTP头
    url = 'http://api.m.jd.com/client.action'  # 设置 URL地址
    data = 'body=%7B%22to%22%3A%22https%253a%252f%252fplogin.m.jd.com%252fjd-mlogin%252fstatic%252fhtml%252fappjmp_blank.html%22%7D&'  # 设置 POST 载荷
    try:
        res = requests.post(url=url, params=params, headers=headers, data=data, verify=False,
                            timeout=10)  # HTTP请求 [POST] 超时 10秒
        res_json = json.loads(res.text)  # Json模块 取值
        tokenKey = res_json['tokenKey']  # 取出TokenKey
    except Exception as err:
        logger.info("JD_WSKEY接口抛出错误 尝试重试 更换IP")  # 标准日志输出
        logger.info(str(err))  # 标注日志输出
        # return False, wskey  # 返回 -> False[Bool], Wskey
        return False  # 返回 -> False[Bool], Wskey
    else:
        return appjmp(wskey, tokenKey)  # 传递 wskey, Tokenkey 执行方法 [appjmp]


# 返回值 bool jd_ck
def appjmp(wskey, tokenKey):  # 方法 传递 wskey & tokenKey
    wskey = "pt_" + str(wskey.split(";")[0])  # 变量组合 使用 ; 分割变量 拼接 pt_
    if tokenKey == 'xxx':  # 判断 tokenKey返回值
        logger.info(str(wskey) + ";疑似IP风控等问题 默认为失效\n--------------------\n")  # 标准日志输出
        # return False, wskey  # 返回 -> False[Bool], Wskey
        return False  # 返回 -> False[Bool], Wskey
    headers = {
        'User-Agent': genJDUA(),
        'accept': 'accept:text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.9',
        'x-requested-with': 'com.jingdong.app.mall'
    }  # 设置 HTTP头
    params = {
        'tokenKey': tokenKey,
        'to': 'https://plogin.m.jd.com/jd-mlogin/static/html/appjmp_blank.html'
    }  # 设置 HTTP_URL 参数
    url = 'https://un.m.jd.com/cgi-bin/app/appjmp'  # 设置 URL地址
    try:
        res = requests.get(url=url, headers=headers, params=params, verify=False, allow_redirects=False,
                           timeout=20)  # HTTP请求 [GET] 阻止跳转 超时 20秒
    except Exception as err:
        logger.info("JD_appjmp 接口错误 请重试或者更换IP\n")  # 标准日志输出
        logger.info(str(err))  # 标准日志输出
        # return False, wskey  # 返回 -> False[Bool], Wskey
        return False  # 返回 -> False[Bool], Wskey
    else:
        try:
            res_set = res.cookies.get_dict()  # 从res cookie取出
            pt_key = 'pt_key=' + res_set['pt_key']  # 取值 [pt_key]
            pt_pin = 'pt_pin=' + res_set['pt_pin']  # 取值 [pt_pin]
            # if "WSKEY_UPDATE_HOUR" in os.environ:  # 判断是否在系统变量中启用 WSKEY_UPDATE_HOUR
            if WSKEY_UPDATE_BOOL:
                jd_ck = str(pt_key) + ';' + str(pt_pin) + ';__time=' + str(time.time()) + ';'  # 拼接变量
            else:
                jd_ck = str(pt_key) + ';' + str(pt_pin) + ';'  # 拼接变量
        except Exception as err:
            logger.info("JD_appjmp提取Cookie错误 请重试或者更换IP\n")  # 标准日志输出
            logger.info(str(err))  # 标准日志输出
            # return False, wskey  # 返回 -> False[Bool], Wskey
            return False  # 返回 -> False[Bool], Wskey
        else:
            if 'fake' in pt_key:  # 判断 pt_key中 是否存在fake
                logger.info(str(wskey) + ";WsKey状态失效\n")  # 标准日志输出
                # return False, wskey  # 返回 -> False[Bool], Wskey
                return False  # 返回 -> False[Bool], Wskey
            else:
                logger.info(str(wskey) + ";WsKey状态正常\n")  # 标准日志输出
                # return True, jd_ck  # 返回 -> True[Bool], jd_ck
                return jd_ck


def ql_api(method, api, body=None) -> dict:
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {token}"
    }
    url = ql_url + api
    for retry_count in range(3):
        try:
            if isinstance(body, dict):
                res = ql_session.request(method, url=url, headers=headers, json=body, timeout=10).json()
            else:
                res = ql_session.request(method, url=url, headers=headers, data=body, timeout=10).json()
        except Exception as err:
            logger.debug(str(err))
            logger.info(f"\n青龙{api}接口错误，重试次数：{retry_count + 1}")
            continue
        else:
            return res
    logger.info(f"\n青龙{api}接口多次重试仍然失败")
    sys.exit(1)


def ql_check(port) -> bool:  # 方法 检查青龙端口
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)  # Socket模块初始化
    sock.settimeout(2)  # 设置端口超时
    try:
        sock.connect(('127.0.0.1', port))  # 请求端口
    except Exception as err:  # 捕捉异常
        logger.debug(str(err))  # 调试日志输出
        sock.close()  # 端口关闭
        return False  # 返回 -> False[Bool]
    else:  # 分支判断
        sock.close()  # 关闭端口
        return True  # 返回 -> True[Bool]


def serch_ck(pin):  # 方法 搜索 Pin
    for i in range(len(envlist)):  # For循环 变量[envlist]的数量
        if "name" not in envlist[i] or envlist[i]["name"] != "JD_COOKIE":  # 判断 envlist内容
            continue  # 继续循环
        if pin in envlist[i]['value']:  # 判断envlist取值['value']
            value = envlist[i]['value']  # 取值['value']
            id = envlist[i][ql_id]  # 取值 [ql_id](变量)
            logger.info(str(pin) + "检索成功\n")  # 标准日志输出
            # return True, value, id  # 返回 -> True[Bool], value, id
            return value, id  # 返回 -> value, id
        else:
            continue  # 继续循环
    logger.info(str(pin) + "检索失败\n")  # 标准日志输出
    return False  # 返回 -> False[Bool], 1


def get_env():  # 方法 读取变量
    api = 'api/envs'
    res = ql_api("GET", api)
    if res.get('code') != 200 or not isinstance(res.get('data'), list):
        logger.info(f"青龙{api}接口返回异常: {str(res)[:200]}")
        sys.exit(1)
    return res['data']


def check_id(envs) -> str:  # 方法 兼容青龙老版本与新版本 id & _id的问题
    if envs and '_id' in envs[0]:  # 判断 [_id]
        logger.info("使用 _id 键值")  # 标准日志输出
        return '_id'  # 返回 -> '_id'
    else:
        logger.info("使用 id 键值")  # 标准日志输出
        return 'id'  # 返回 -> 'id'


def ql_update(eid, newck):  # 方法 青龙更新变量 传递 id cookie
    api = 'api/envs'
    body = {
        'name': 'JD_COOKIE',
        'value': newck,
        ql_id: eid
    }
    res = ql_api("PUT", api, body)
    if res.get('code') != 200:  # 更新失败时记录并推送, 避免静默失败
        logger.info(f"\n账号更新失败: {str(res)[:200]}\n")
        pin = re.search(r'pt_pin=[^;]+', newck)
        push_collect(f"账号: {pin.group(0) if pin else '?'}; JD_COOKIE 更新失败, 请查看日志")
    ql_enable(eid)


def ql_enable(eid):  # 方法 青龙变量启用 传递值 eid
    api = 'api/envs/enable'
    res = ql_api("PUT", api, json.dumps([eid]))  # json.dumps 兼容旧版字符串型 _id
    if res.get('code') == 200:  # 判断返回值为 200
        logger.info("\n账号启用\n--------------------\n")  # 标准日志输出
        return True
    else:
        logger.info("\n账号启用失败\n--------------------\n")  # 标准日志输出
        return False


def ql_disable(eid):  # 方法 青龙变量禁用 传递 eid
    api = 'api/envs/disable'
    res = ql_api("PUT", api, json.dumps([eid]))
    if res.get('code') == 200:  # 判断返回值为 200
        logger.info("\n账号禁用成功\n--------------------\n")  # 标准日志输出
    else:
        logger.info("\n账号禁用失败\n--------------------\n")  # 标准日志输出


def ql_insert(i_ck):  # 方法 插入新变量
    api = 'api/envs'
    body = json.dumps([{"value": i_ck, "name": "JD_COOKIE"}])
    res = ql_api("POST", api, body)
    if res.get('code') == 200:  # 判断返回值为 200
        logger.info("\n账号添加完成\n--------------------\n")  # 标准日志输出
    else:
        logger.info("\n账号添加失败\n--------------------\n")  # 标准日志输出
        push_collect("新账号添加到青龙失败, 请查看日志")


def check_port():  # 方法 检查变量传递端口
    logger.info("\n--------------------\n")  # 标准日志输出
    port = env_int("QL_PORT", 5700, minimum=1)
    if ql_check(port):  # 调用方法 [ql_check] 传递 [port]
        logger.info(str(port) + "端口检查通过")  # 标准日志输出
        return port  # 返回->port
    else:
        logger.info(
            str(port) + "端口检查失败, 如果改过端口, 请在变量中声明端口 \n在config.sh中加入 export QL_PORT=\"端口号\"")  # 标准日志输出
        logger.info("\n如果你很确定端口没错, 还是无法执行, 在GitHub给我发issus\n--------------------\n")  # 标准日志输出
        sys.exit(1)  # 脚本退出


if __name__ == '__main__':  # Python主函数执行入口
    port = check_port()  # 调用方法 [check_port]  并赋值 [port]
    ql_url = f'http://127.0.0.1:{port}/'
    ql_session = requests.session()
    token = ql_login()  # 调用方法 [ql_login]  并赋值 [token]
    wslist = get_wskey()
    envlist = get_env()  # 只请求一次 api/envs, 同时用于判断 id 键名和检索账号
    ql_id = check_id(envlist)
    sleepTime = env_int("WSKEY_SLEEP", 10)
    tryCount = env_int("WSKEY_TRY_COUNT", 1, minimum=1)
    for index, ws in enumerate(wslist):  # wslist变量 for循环  [wslist -> ws]
        wspin = ws.split(";")[0]  # 变量分割 ;
        if "pin" not in wspin:  # 判断 pin 是否存在于 [wspin]
            logger.info("WSKEY格式错误\n--------------------\n")  # 标准日志输出
            continue
        wspin = "pt_" + wspin + ";"  # 封闭变量
        return_serch = serch_ck(wspin)  # 变量 pt_pin 搜索获取 key eid
        if return_serch:  # bool: True 搜索到账号
            jck, eid = return_serch  # 拿到 JD_COOKIE
            if check_ck(jck):  # bool: True 现有 JD_COOKIE 仍然有效, 无需转换
                logger.info(str(wspin) + "账号有效")  # 标准日志输出
                ql_enable(eid)  # 执行方法[ql_enable] 传递 eid
                logger.info("--------------------\n")  # 标准日志输出
            else:
                return_ws = False
                for count in range(1, tryCount + 1):  # for循环 [tryCount]
                    return_ws = getToken(ws)  # 使用 WSKEY 请求获取 JD_COOKIE bool jd_ck
                    if return_ws:
                        break  # 中断循环
                    if count < tryCount:  # 判断循环次
                        logger.info("{0} 秒后重试，剩余次数：{1}\n".format(sleepTime, tryCount - count))  # 标准日志输出
                        time.sleep(sleepTime)  # 脚本休眠 使用变量 [sleepTime]
                if return_ws:  # 判断 [return_ws]返回值 Bool类型
                    logger.info("wskey转换成功")  # 标准日志输出
                    ql_update(eid, return_ws)  # 函数 ql_update 参数 eid JD_COOKIE
                elif WSKEY_AUTO_DISABLE:
                    logger.info(str(wspin) + "账号失效")  # 标准日志输出
                    push_collect(f"账号: {wspin} WsKey疑似失效")  # 设置推送内容
                else:
                    logger.info(str(wspin) + "账号禁用")  # 标准日志输出
                    ql_disable(eid)  # 执行方法[ql_disable] 传递 eid
                    push_collect(f"账号: {wspin} WsKey疑似失效, 已禁用Cookie")
        else:
            logger.info("\n新wskey\n")  # 标准日志分支
            return_ws = getToken(ws)  # 使用 WSKEY 请求获取 JD_COOKIE bool jd_ck
            if return_ws:  # 判断 (return_ws[0]) 类型: [Bool]
                logger.info("wskey转换成功\n")  # 标准日志输出
                ql_insert(return_ws)  # 调用方法 [ql_insert]
            else:
                push_collect(f"账号: {wspin} 新wskey转换失败, 请查看日志")
        if index < len(wslist) - 1:  # 最后一个账号处理完后无需再等待
            logger.info(f"暂停{sleepTime}秒\n")  # 标准日志输出
            time.sleep(sleepTime)  # 脚本休眠
    push_flush()  # 所有账号处理完成后统一推送一次
    logger.info("执行完成\n--------------------")  # 标准日志输出
    sys.exit(0)  # 脚本退出
    # Enjoy
