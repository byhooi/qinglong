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
import logging
import sys

# 尝试导入 notify，如果失败则导入 sendNotify
try:
    import notify
except ImportError:
    try:
        import sendNotify as notify
    except ImportError:
        notify = None
        print("未找到 notify 或 sendNotify 模块，无法发送通知。")

# 配置日志
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# --- Constants ---
API_SUCCESS_CODE = 0
DEFAULT_TEMP_ID = "16408240716151126162"
SHARE_FROM_VALUE = 1
SHARE_TARGET_VALUE = 0
MAX_SHARE_ATTEMPTS = 5
MAX_GAME_ATTEMPTS = 3

def process_account(index, account_str, pzid, headers):
    """处理单个达美乐账户的分享和抽奖逻辑"""
    account_message = []
    
    parts = account_str.split('#')
    openid = parts[0]
    remark = parts[1] if len(parts) > 1 else ""
    
    account_info_str = f"账号{index} {remark}"
    logging.info(f"\n=======开始执行 {account_info_str}=======")
    
    game_done_url = f"https://game.dominos.com.cn/{pzid}/game/gameDone"
    sharing_done_url = f"https://game.dominos.com.cn/{pzid}/game/sharingDone"

    # 分享逻辑
    share_success = False
    for attempt in range(1, MAX_SHARE_ATTEMPTS + 1):
        share_payload = f"openid={openid}&from={SHARE_FROM_VALUE}&target={SHARE_TARGET_VALUE}"
        try:
            res = requests.post(sharing_done_url, data=share_payload, headers=headers).json()
            error_message = res.get("errorMessage")
            status_code = res.get("statusCode")
            
            if error_message == "今日分享已用完，请明日再来":
                logging.info(f"{account_info_str} 分享已达上限，开始抽奖")
                share_success = True
                break
            elif status_code == API_SUCCESS_CODE:
                logging.info(f"{account_info_str} 分享成功，第 {attempt} 次尝试。")
                # 原始代码逻辑是只要成功或达到上限就跳出，但循环还在继续，这里我们假设需要刷分享次数吗？
                # 参考 backup/dml.py，它是 while True 直到 "今日分享已用完"。
                # 参考 dml.py，它是尝试 5 次。
                # 既然 backup/dml.py 之前是 while True 直到已用完，我们这里保持尝试直到上限，但为了避免死循环，使用 MAX_SHARE_ATTEMPTS
                pass 
            else:
                logging.warning(f"{account_info_str} 分享失败: {error_message}")
                # 不中断，继续尝试
        except requests.exceptions.RequestException as e:
            logging.error(f"{account_info_str} 分享API请求失败: {e}")
            break
        except json.JSONDecodeError as e:
            logging.error(f"{account_info_str} 分享JSON解析失败: {e}")
            break
            
        time.sleep(1) # 稍微等待避免过快

    # 抽奖逻辑
    game_payload = f"openid={openid}&score=d8XtWSEx0zRy%2BxdeJriXZeoTek6ZVZdadlxdTFiN9yrxt%2BSIax0%2BRccbkObBZsisYFTquPg%2FG2cnGPBlGV2f32C6D5q3FFhgvcfJP9cKg%2BXs6l7J%2BEcahicPml%2BZWp3P4o1pOQvNdDUTQgtO6NGY0iijZ%2FLAmITy5EJU8dAc1EnbvhOYG36Qg1Ji4GDRoxAfRgmELvpLM6JSFlCEKG2C2s%2BJCevOJo7kwsLJCvwbVgeewhKSAyCZYnJQ4anmPgvrv6iUIiFQP%2Bj6%2B5p1VETe5xfawQ4FQ4w0mttXP0%2BhX39n1dzDrfcSkYkUaWPkIFlHAX7QPT3IgG6MhIKCvB%2BUcw%3D%3D&tempId={DEFAULT_TEMP_ID}"
    
    # 原始 backup 循环3次
    for attempt in range(1, MAX_GAME_ATTEMPTS + 1):
        try:
            response = requests.post(game_done_url, data=game_payload, headers=headers)
            response_json = response.json()
            status_code = response_json.get("statusCode")

            if status_code == API_SUCCESS_CODE:
                prize = response_json.get("content", {}).get("name")
                if prize:
                    logging.info(f"{account_info_str} 第{attempt}次抽奖结果: {prize}")
                    # 只有一等奖才记录到通知消息
                    if "一等奖" in prize:
                        account_message.append(f"{account_info_str} 中得: {prize}")
                else:
                    logging.warning(f"{account_info_str} 第{attempt}次抽奖成功但未获取到奖品名称。")
            else:
                err = response_json.get("errorMessage", "未知错误")
                logging.warning(f"{account_info_str} 第{attempt}次抽奖失败: {err}")
                account_message.append(f"{account_info_str} 第{attempt}次抽奖出错: {err}")
                break # 出错则跳出
        except requests.exceptions.RequestException as e:
            logging.error(f"{account_info_str} 第{attempt}次抽奖API请求失败: {e}")
            break
        except json.JSONDecodeError as e:
            logging.error(f"{account_info_str} 第{attempt}次抽奖JSON解析失败: {e}")
            break
        except Exception as e:
             logging.error(f"{account_info_str} 第{attempt}次抽奖发生未知错误: {e}")
             break
        
        time.sleep(1)

    return "\n".join(account_message)

def main():
    # from dotenv import load_dotenv
    # load_dotenv() # 如果本地运行需要加载 .env，但在青龙面板通常不需要
    
    accounts_str = os.getenv('dmlck')
    pzid = os.getenv('pzid')

    if not accounts_str:
        logging.error("未找到 dmlck 环境变量，退出。")
        return
        
    if not pzid:
        logging.error("未找到 pzid 环境变量，退出。")
        return

    accounts_list = accounts_str.split('@')
    num_of_accounts = len(accounts_list)
    logging.info(f"获取到 {num_of_accounts} 个账号")

    headers = {
        'User-Agent': "Mozilla/5.0 (Linux; Android 12; M2012K11AC Build/SKQ1.211006.001; wv) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/122.0.6261.120 Mobile Safari/537.36 XWEB/1220133 MMWEBSDK/20240404 MMWEBID/8518 MicroMessenger/8.0.49.2600(0x2800313D) WeChat/arm64 Weixin NetType/WIFI Language/zh_CN ABI/arm64 MiniProgramEnv/android", # 使用 dml.py 更现代的 UA
        'Accept-Encoding': "gzip,compress,br,deflate",
        'Content-Type': "application/x-www-form-urlencoded",
        'charset': "utf-8",
        'Referer': f"https://servicewechat.com/wx887bf6ad752ca2f3/63/page-frame.html" # 保持 backup 的 Referer, 注意这里微信号可能不同? dml.py 是 wx887bf6ad752ca2f2, backup 是 wx887bf6ad752ca2f3 (可能是不同的小程序版本或同一个)
    }

    all_messages = []

    for i, account in enumerate(accounts_list, start=1):
        if not account:
            continue
        msg = process_account(i, account, pzid, headers)
        if msg:
            all_messages.append(msg)

    if all_messages:
        final_message = "\n".join(all_messages)
        logging.info("======= 推送消息 =======")
        logging.info(final_message)
        if notify:
            try:
                notify.send('达美乐一等奖通知', final_message)
            except Exception as e:
                logging.error(f"推送失败: {e}")
        else:
            logging.warning("未配置通知模块，跳过推送。")

if __name__ == "__main__":
    main()