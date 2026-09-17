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
  WSKEY_UPDATE_HOUR   设置后改为按小时定期刷新 (只比较 Cookie 里的 __time, 不再请求京东接口), 非数字时按 23 小时
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
from urllib.parse import unquote

WSKEY_MODE = 0  # 0 = 正常运行 / 1 = 调试模式

DEBUG_MODE = bool(WSKEY_MODE) or "WSKEY_DEBUG" in os.environ  # 判断调试模式变量
logging.basicConfig(level=logging.DEBUG if DEBUG_MODE else logging.INFO, format='%(message)s')
logger = logging.getLogger(__name__)  # 主模块
if DEBUG_MODE:
    logger.debug("\nDEBUG模式开启!\n")  # 消息输出

try:
    import requests  # 导入HTTP模块
except Exception as e:
    logger.info(str(e) + "\n缺少requests模块, 请执行命令：pip3 install requests\n")  # 日志输出
    sys.exit(1)  # 退出脚本
os.environ['no_proxy'] = '*'  # 走直连, 避免容器内的代理设置干扰京东接口
requests.packages.urllib3.disable_warnings()  # 抑制证书告警

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


# 京东自定义的 base64 字符表, 与标准表逐位对应; 该映射自逆, 编码与解码共用同一张表
B64_TABLE = str.maketrans(
    "KLMNOPQRSTABCDEFGHIJUVWXYZabcdopqrstuvwxefghijklmnyz0123456789+/",
    "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/",
)

# 运行期状态: 由 main() 统一初始化, 供各青龙接口函数共享
ql_url = ''        # 青龙面板地址
ql_session = None  # 复用连接的会话对象
token = ''         # 青龙登录凭证
envlist = []       # 环境变量列表缓存, 只请求一次 api/envs
ql_id = 'id'       # 变量主键名, 新旧版本青龙分别为 _id / id

WSKEY_UPDATE_BOOL = bool(os.environ.get("WSKEY_UPDATE_HOUR"))  # 设置后按小时定期刷新, 转换结果附带 __time 时间戳
WSKEY_DISCHECK_BOOL = bool(os.environ.get("WSKEY_DISCHECK"))  # 设置后不检查现有 JD_COOKIE 有效性
WSKEY_AUTO_DISABLE = bool(os.environ.get("WSKEY_AUTO_DISABLE"))  # 设置后失效账号只推送提醒, 不禁用 JD_COOKIE
push_msgs = []  # 统一推送: 收集所有账号的重要信息, 结束时一次性推送


def env_int(name, default, minimum=0):
    """读取整数型环境变量, 非数字或小于下限时返回默认值"""
    value = os.environ.get(name, "").strip()
    if value.isdigit() and int(value) >= minimum:
        return int(value)
    return default


def totp(secret):
    """按密钥生成两步验证的 6 位动态口令"""
    key = base64.b32decode(secret.upper() + '=' * ((8 - len(secret)) % 8))
    counter = struct.pack('>Q', int(time.time() / 30))
    mac = hmac.new(key, counter, 'sha1').digest()
    offset = mac[-1] & 0x0f
    binary = struct.unpack('>L', mac[offset:offset + 4])[0] & 0x7fffffff
    return str(binary)[-6:].zfill(6)


def sign_core(par):
    """京东接口签名所使用的字节变换"""
    arr = [0x37, 0x92, 0x44, 0x68, 0xA5, 0x3D, 0xCC, 0x7F, 0xBB, 0xF, 0xD9, 0x88, 0xEE, 0x9A, 0xE9, 0x5A]
    key2 = b"80306f4370b39fd5630ad0529f77adb6"
    arr1 = [0 for _ in range(len(par))]
    for i in range(len(par)):
        r0 = int(par[i])
        r2 = arr[i & 0xf]
        r4 = key2[i & 7]
        r0 = r0 ^ r2 ^ r4
        r0 = r0 + r2
        r2 = r2 ^ r0
        r2 = r2 ^ r4
        arr1[i] = r2 & 0xff
    return bytes(arr1)


def get_sign(function_id, body, suid, client, client_version, st, sv):
    """拼接请求参数并生成 sign"""
    all_arg = "functionId=%s&body=%s&uuid=%s&client=%s&clientVersion=%s&st=%s&sv=%s" % (
        function_id, body, suid, client, client_version, st, sv)
    ret_bytes = sign_core(str.encode(all_arg))
    return hashlib.md5(base64.b64encode(ret_bytes)).hexdigest()


def b64_encode(string):
    """使用京东自定义字符表的 base64 编码"""
    return base64.b64encode(string.encode("utf-8")).decode('utf-8').translate(B64_TABLE)


def gen_suid():
    """生成 16 位随机串, 用作请求中的 uuid / openudid / aid"""
    return ''.join(str(uuid.uuid4()).split('-'))[16:]


def gen_jd_ua():
    """生成京东 App 的 User-Agent"""
    st = round(time.time() * 1000)
    aid = b64_encode(gen_suid())
    oaid = b64_encode(gen_suid())
    return 'jdapp;android;11.1.4;;;appBuild/98176;ef/1;ep/{"hdid":"JM9F1ywUPwflvMIpYPok0tt5k9kW4ArJEU3lfLhxBqw=","ts":%s,"ridx":-1,"cipher":{"sv":"CJS=","ad":"%s","od":"%s","ov":"CzO=","ud":"%s"},"ciphertype":5,"version":"1.2.0","appname":"com.jingdong.app.mall"};Mozilla/5.0 (Linux; Android 12; M2102K1C Build/SKQ1.220303.001; wv) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/97.0.4692.98 Mobile Safari/537.36' % (st, aid, oaid, aid)


def gen_params():
    """生成 genToken 接口所需的公共参数"""
    suid = gen_suid()
    buid = b64_encode(suid)
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
    return {
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


def pin_name(text):
    """提取账号名用于日志与推送

    支持 pt_pin=xxx; 与 pin=xxx;wskey=xxx; 两种形式, URL 编码的中文账号名一并解码;
    提取不到时返回占位符, 避免把 Cookie 原文(含 pt_key)带进日志或推送
    """
    matched = re.search(r'pin=([^;\s]+)', text, re.I)
    return unquote(matched.group(1)) if matched else "未知账号"


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
    """统一推送已收集的消息, 无消息时不打扰"""
    if push_msgs:
        ql_send("\n".join(push_msgs))


def get_latest_file(files):
    """返回修改时间最新的那个文件"""
    latest_file = None
    latest_mtime = 0
    for file in files:
        try:
            stats = os.stat(file)
        except FileNotFoundError:
            continue
        if stats.st_mtime > latest_mtime:
            latest_mtime = stats.st_mtime
            latest_file = file
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


def ql_login_by_password(username, password, two_factor_secret):
    """使用 auth.json 中的账号密码登录青龙, 返回 token"""
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
        if not two_factor_secret:
            logger.info("青龙开启了两步验证但 auth 文件中没有 twoFactorSecret, 无法自动登录\n")
            sys.exit(1)
        try:
            body['code'] = totp(two_factor_secret)
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


def ql_login():
    """获取青龙 Token, 优先复用已保存的, 失效则用账号密码重新登录"""
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
    for token_candidate in dict.fromkeys(candidates):  # 去重并保持顺序
        headers['Authorization'] = 'Bearer {0}'.format(token_candidate)
        try:
            res = requests.get(url=ql_url + 'api/user', headers=headers, timeout=10)  # 验证 token 是否有效
        except Exception as err:
            logger.debug(str(err))
            continue
        if res.status_code == 200:  # 判断 HTTP返回状态码
            return token_candidate  # 有效 返回 token
    return ql_login_by_password(auth.get("username", ""), auth.get("password", ""), auth.get("twoFactorSecret", ""))


def get_wskey():
    """从环境变量 JD_WSCK 读取 wskey 列表"""
    if "JD_WSCK" not in os.environ:  # 判断 JD_WSCK是否存在于环境变量
        logger.info("未添加JD_WSCK变量")  # 标准日志输出
        sys.exit(0)  # 脚本退出
    wskey_list = [w.strip() for w in re.split(r'[&\n]', os.environ['JD_WSCK']) if w.strip()]  # 以 & 或换行分割, 忽略空项
    if not wskey_list:
        logger.info("JD_WSCK变量未启用")  # 标准日志输出
        sys.exit(1)  # 脚本退出
    return wskey_list  # 返回 WSKEY [LIST]


def check_cookie(ck):
    """检查现有 JD_COOKIE 是否仍然可用, True 表示无需转换"""
    pin = pin_name(ck)
    if WSKEY_UPDATE_BOOL:
        # 定期刷新模式: 只比较 Cookie 内的 __time, 不请求京东接口
        update_hour = env_int("WSKEY_UPDATE_HOUR", 23, minimum=1)  # 更新间隔, 非数字时按 23 小时
        matched = re.search(r'__time=([^;\s]+)', ck, re.M | re.I)  # 正则检索 [__time=]
        try:
            updated_at = float(matched.group(1)) if matched else 0.0  # 没有时间戳时视为已过期
        except ValueError:
            updated_at = 0.0
        remaining = update_hour * 60 * 60 - (time.time() - updated_at)  # 距离下次更新还剩多少秒
        if remaining <= 10 * 60:  # 提前 10 分钟视为到期
            logger.info(str(pin) + ";即将到期或已过期\n")  # 标准日志输出
            return False
        logger.info(str(pin) + ";未到期，{0}时{1}分后更新\n".format(int(remaining // 3600), int(remaining % 3600 // 60)))
        return True
    if WSKEY_DISCHECK_BOOL:
        logger.info("不检查账号有效性\n--------------------\n")  # 标准日志输出
        return False
    url = 'https://me-api.jd.com/user_new/info/GetJDUserInfoUnion'  # 设置JD_API接口地址
    headers = {
        'Cookie': ck,
        'Referer': 'https://home.m.jd.com/myJd/home.action',
        'user-agent': gen_jd_ua()
    }  # 设置 HTTP头
    try:
        res = requests.get(url=url, headers=headers, verify=False, timeout=10, allow_redirects=False)  # HTTP请求[GET]
    except Exception as err:
        logger.debug(str(err))  # 调试日志输出
        logger.info("JD接口错误 请重试或者更换IP")  # 标准日志输出
        return False
    if res.status_code != 200:
        logger.info("JD接口错误码: " + str(res.status_code))  # 标注日志输出
        return False
    try:
        code = int(json.loads(res.text)['retcode'])  # 使用 Json模块对返回数据取值 int([retcode])
    except Exception as err:
        logger.debug(str(err))
        logger.info("JD接口风控, 建议更换IP或增加间隔时间")
        return False
    if code == 0:
        logger.info(str(pin) + ";状态正常\n")  # 标准日志输出
        return True
    logger.info(str(pin) + ";状态失效\n")
    return False


def appjmp(wskey, token_key):
    """带 tokenKey 跳转, 从响应 Cookie 中取出 JD_COOKIE, 失败返回 False"""
    pin = "pt_" + str(wskey.split(";")[0])  # 仅用于日志展示: pt_pin=xxx
    if token_key == 'xxx':  # 判断 tokenKey返回值
        logger.info(str(pin) + ";疑似IP风控等问题 默认为失效\n--------------------\n")  # 标准日志输出
        return False
    headers = {
        'User-Agent': gen_jd_ua(),
        'accept': 'accept:text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.9',
        'x-requested-with': 'com.jingdong.app.mall'
    }  # 设置 HTTP头
    params = {
        'tokenKey': token_key,
        'to': 'https://plogin.m.jd.com/jd-mlogin/static/html/appjmp_blank.html'
    }  # 设置 HTTP_URL 参数
    url = 'https://un.m.jd.com/cgi-bin/app/appjmp'  # 设置 URL地址
    try:
        res = requests.get(url=url, headers=headers, params=params, verify=False, allow_redirects=False,
                           timeout=20)  # HTTP请求 [GET] 阻止跳转 超时 20秒
    except Exception as err:
        logger.info("JD_appjmp 接口错误 请重试或者更换IP\n")  # 标准日志输出
        logger.info(str(err))
        return False
    try:
        res_set = res.cookies.get_dict()  # 从res cookie取出
        pt_key = 'pt_key=' + res_set['pt_key']
        pt_pin = 'pt_pin=' + res_set['pt_pin']
    except Exception as err:
        logger.info("JD_appjmp提取Cookie错误 请重试或者更换IP\n")  # 标准日志输出
        logger.info(str(err))
        return False
    if 'fake' in pt_key:  # 判断 pt_key中 是否存在fake
        logger.info(str(pin) + ";WsKey状态失效\n")  # 标准日志输出
        return False
    logger.info(str(pin) + ";WsKey状态正常\n")  # 标准日志输出
    if WSKEY_UPDATE_BOOL:  # 定期刷新模式需要记录转换时间, 供 check_cookie 判断是否到期
        return str(pt_key) + ';' + str(pt_pin) + ';__time=' + str(time.time()) + ';'
    return str(pt_key) + ';' + str(pt_pin) + ';'


def wskey_to_cookie(wskey):
    """用 wskey 换取 JD_COOKIE, 失败返回 False"""
    params = gen_params()
    headers = {
        'cookie': wskey,
        'content-type': 'application/x-www-form-urlencoded; charset=UTF-8',
        'charset': 'UTF-8',
        'accept-encoding': 'br,gzip,deflate',
        'user-agent': gen_jd_ua()
    }  # 设置 HTTP头
    url = 'http://api.m.jd.com/client.action'  # 设置 URL地址
    data = 'body=%7B%22to%22%3A%22https%253a%252f%252fplogin.m.jd.com%252fjd-mlogin%252fstatic%252fhtml%252fappjmp_blank.html%22%7D&'  # 设置 POST 载荷
    try:
        res = requests.post(url=url, params=params, headers=headers, data=data, verify=False,
                            timeout=10)  # HTTP请求 [POST] 超时 10秒
        token_key = json.loads(res.text)['tokenKey']  # 取出TokenKey
    except Exception as err:
        logger.info("JD_WSKEY接口抛出错误 尝试重试 更换IP")  # 标准日志输出
        logger.info(str(err))  # 标注日志输出
        return False
    return appjmp(wskey, token_key)


def ql_request(method, api, body=None):
    """调用青龙接口, 失败自动重试 3 次"""
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {token}"
    }
    url = ql_url + api
    for retry_count in range(3):
        try:
            if isinstance(body, (dict, list)):  # 结构化数据交给 requests 序列化
                res = ql_session.request(method, url=url, headers=headers, json=body, timeout=10).json()
            else:
                res = ql_session.request(method, url=url, headers=headers, data=body, timeout=10).json()
        except Exception as err:
            logger.debug(str(err))
            logger.info(f"\n青龙{api}接口错误，重试次数：{retry_count + 1}")
            continue
        return res
    logger.info(f"\n青龙{api}接口多次重试仍然失败")
    sys.exit(1)


def port_open(port):
    """检查本地端口是否可连接"""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)  # Socket模块初始化
    sock.settimeout(2)  # 设置端口超时
    try:
        sock.connect(('127.0.0.1', port))  # 请求端口
    except Exception as err:  # 捕捉异常
        logger.debug(str(err))  # 调试日志输出
        sock.close()  # 端口关闭
        return False
    sock.close()  # 关闭端口
    return True


def find_cookie(pin):
    """在已加载的环境变量中查找包含指定 pt_pin 的 JD_COOKIE, 返回 (值, 变量id) 或 False"""
    for env in envlist:
        if env.get("name") != "JD_COOKIE" or 'value' not in env:  # 只关心 JD_COOKIE
            continue
        if pin in env['value']:
            logger.info(str(pin) + "检索成功\n")  # 标准日志输出
            return env['value'], env[ql_id]
    logger.info(str(pin) + "检索失败\n")  # 标准日志输出
    return False


def get_envs():
    """读取青龙全部环境变量"""
    api = 'api/envs'
    res = ql_request("GET", api)
    if res.get('code') != 200 or not isinstance(res.get('data'), list):
        logger.info(f"青龙{api}接口返回异常: {str(res)[:200]}")
        sys.exit(1)
    return res['data']


def detect_id_key(envs):
    """兼容青龙新旧版本 id / _id 的差异"""
    if envs and '_id' in envs[0]:
        logger.info("使用 _id 键值")  # 标准日志输出
        return '_id'
    logger.info("使用 id 键值")  # 标准日志输出
    return 'id'


def update_cookie(eid, new_ck):
    """更新已有账号的 JD_COOKIE, 成功后顺带启用该变量"""
    res = ql_request("PUT", 'api/envs', {'name': 'JD_COOKIE', 'value': new_ck, ql_id: eid})
    if res.get('code') != 200:  # 更新失败时记录并推送, 避免静默失败
        logger.info(f"\n账号更新失败: {str(res)[:200]}\n")
        push_collect(f"{pin_name(new_ck)}；JD_COOKIE更新失败，请查看日志")
        return  # 值没写进去, 不启用旧的失效 Cookie
    enable_env(eid)


def enable_env(eid):
    """启用青龙变量"""
    res = ql_request("PUT", 'api/envs/enable', [eid])
    if res.get('code') == 200:
        logger.info("\n账号启用\n--------------------\n")  # 标准日志输出
        return True
    logger.info("\n账号启用失败\n--------------------\n")  # 标准日志输出
    return False


def disable_env(eid):
    """禁用青龙变量"""
    res = ql_request("PUT", 'api/envs/disable', [eid])
    if res.get('code') == 200:
        logger.info("\n账号禁用成功\n--------------------\n")  # 标准日志输出
    else:
        logger.info("\n账号禁用失败\n--------------------\n")  # 标准日志输出


def insert_cookie(ck):
    """把新账号写入青龙环境变量"""
    res = ql_request("POST", 'api/envs', [{"value": ck, "name": "JD_COOKIE"}])
    if res.get('code') == 200:
        logger.info("\n账号添加完成\n--------------------\n")  # 标准日志输出
    else:
        logger.info("\n账号添加失败\n--------------------\n")  # 标准日志输出
        push_collect(f"{pin_name(ck)}；新账号添加到青龙失败，请查看日志")


def check_port():
    """检查青龙端口, 返回可用端口"""
    logger.info("\n--------------------\n")  # 标准日志输出
    port = env_int("QL_PORT", 5700, minimum=1)
    if port_open(port):
        logger.info(str(port) + "端口检查通过")  # 标准日志输出
        return port
    logger.info(str(port) + "端口检查失败, 如果改过端口, 请在变量中声明端口 \n在config.sh中加入 export QL_PORT=\"端口号\"")
    logger.info("\n如果你很确定端口没错, 还是无法执行, 在GitHub给我发issus\n--------------------\n")  # 标准日志输出
    sys.exit(1)  # 脚本退出


def convert(wskey, sleep_time, try_count):
    """调用京东接口把 wskey 换成 JD_COOKIE, 失败按 WSKEY_TRY_COUNT 重试"""
    for count in range(1, try_count + 1):
        jd_ck = wskey_to_cookie(wskey)
        if jd_ck:
            return jd_ck
        if count < try_count:  # 判断循环次
            logger.info("{0} 秒后重试，剩余次数：{1}\n".format(sleep_time, try_count - count))  # 标准日志输出
            time.sleep(sleep_time)
    return False


def handle_wskey(ws, sleep_time, try_count):
    """处理单个 wskey: 已有同账号 Cookie 且有效则跳过, 否则转换后更新或新增"""
    pin_part = ws.split(";")[0]  # 形如 pin=xxx
    if "pin" not in pin_part:  # 判断 pin 是否存在于 [pin_part]
        logger.info("WSKEY格式错误\n--------------------\n")  # 标准日志输出
        return
    search_key = "pt_" + pin_part + ";"  # 形如 pt_pin=xxx;, 用于在已有 JD_COOKIE 中检索
    name = pin_name(search_key)
    found = find_cookie(search_key)
    if not found:  # 青龙里还没有这个账号
        logger.info("\n新wskey\n")  # 标准日志分支
        new_ck = convert(ws, sleep_time, try_count)
        if new_ck:
            logger.info("wskey转换成功\n")  # 标准日志输出
            insert_cookie(new_ck)
        else:
            push_collect(f"{name}；新wskey转换失败，请查看日志")
        return
    jck, eid = found  # 已有账号的 Cookie 与变量 id
    if check_cookie(jck):  # 现有 JD_COOKIE 仍然有效, 无需转换
        logger.info(str(name) + "账号有效")  # 标准日志输出
        enable_env(eid)  # 有效账号顺带确保处于启用状态
        logger.info("--------------------\n")  # 标准日志输出
        return
    new_ck = convert(ws, sleep_time, try_count)
    if new_ck:
        logger.info("wskey转换成功")  # 标准日志输出
        update_cookie(eid, new_ck)
    elif WSKEY_AUTO_DISABLE:
        logger.info(str(name) + "账号失效")  # 标准日志输出
        push_collect(f"{name}；Wskey疑似失效")  # 设置推送内容
    else:
        logger.info(str(name) + "账号禁用")  # 标准日志输出
        disable_env(eid)
        push_collect(f"{name}；Wskey疑似失效，已禁用Cookie")


def main():
    global ql_url, ql_session, token, envlist, ql_id
    port = check_port()  # 先确认青龙端口可用
    wslist = get_wskey()  # 没配 JD_WSCK 时直接退出, 不必再请求青龙
    ql_url = f'http://127.0.0.1:{port}/'
    ql_session = requests.session()
    token = ql_login()
    envlist = get_envs()  # 只请求一次 api/envs, 同时用于判断 id 键名和检索账号
    ql_id = detect_id_key(envlist)
    sleep_time = env_int("WSKEY_SLEEP", 10)
    try_count = env_int("WSKEY_TRY_COUNT", 1, minimum=1)
    try:
        for index, ws in enumerate(wslist):  # wslist变量 for循环  [wslist -> ws]
            handle_wskey(ws, sleep_time, try_count)
            if index < len(wslist) - 1:  # 最后一个账号处理完后无需再等待
                logger.info(f"暂停{sleep_time}秒\n")  # 标准日志输出
                time.sleep(sleep_time)
    finally:
        push_flush()  # 中途异常退出也要把已收集的消息推出去
    logger.info("执行完成\n--------------------")  # 标准日志输出
    sys.exit(0)  # 脚本退出


if __name__ == '__main__':  # Python主函数执行入口
    main()
