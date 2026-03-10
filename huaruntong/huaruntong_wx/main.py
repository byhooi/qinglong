"""
new Env('华润通微信版签到');
cron: 20 8 * * *
"""

"""
华润通微信版签到脚本
环境变量: hrt_wx (JSON格式)
格式示例: {"accounts":[{"account_name":"账号1","token":"xxx"},{"account_name":"账号2","token":"yyy"}]}
多账号在 accounts 数组中添加即可
"""
import json
import os
import sys
import time
import random
from datetime import datetime
from pathlib import Path
from api import HuaRunTongAPI

# 添加项目根目录到Python路径
current_dir = Path(__file__).parent
project_root = current_dir.parent.parent
sys.path.insert(0, str(project_root))

try:
    from sendNotify import send
except:
    def send(title, content):
        print(f"\n{title}\n{content}")


def load_accounts():
    """从环境变量加载账号配置"""
    env_value = os.getenv('hrt_wx', '')
    if not env_value:
        return []

    try:
        config = json.loads(env_value)
        return config.get('accounts', [])
    except json.JSONDecodeError:
        print("❌ 环境变量 hrt_wx 格式错误，请检查JSON格式")
        return []


def process_account(account_config):
    """处理单个账号的签到"""
    account_name = account_config.get('account_name', '未知账号')

    result_info = {
        'account_name': account_name,
        'success': False,
        'error': None,
        'message': None,
        'response': None
    }

    print("=" * 50)
    print(f"账号: {account_name}")
    print("=" * 50)

    # 初始化API
    api = HuaRunTongAPI(
        token=account_config.get("token"),
        answer_result=account_config.get("answerResult", 1),
        channel_id=account_config.get("channelId", "APP"),
        merchant_code=account_config.get("merchantCode", "1641000001532"),
        store_code=account_config.get("storeCode", "qiandaosonjifen"),
        sys_id=account_config.get("sysId", "T0000001"),
        transaction_uuid=account_config.get("transactionUuid", ""),
        invite_code=account_config.get("inviteCode", ""),
        user_agent=account_config.get("user_agent")
    )

    # 发送请求
    print("\n发送签到请求...")
    result = api.sign_in()

    # 解析结果
    if result.get('code') == "S0A00000":
        result_info['success'] = True
        result_info['message'] = result.get('message', '签到成功')
        result_info['response'] = result
        print("✅ 签到成功")
    else:
        result_info['error'] = result.get('msg', '签到失败')
        result_info['response'] = result.get('msg')
        print(f"❌ 签到失败: {result_info['error']}")

    print("响应:")
    print(json.dumps(result, indent=2, ensure_ascii=False))
    print("\n" + "=" * 50)

    return result_info


def build_notification(all_results, start_time, end_time):
    """构建推送通知内容"""
    duration = (end_time - start_time).total_seconds()

    total_count = len(all_results)
    success_count = sum(1 for r in all_results if r.get('success'))
    failed_count = total_count - success_count

    if failed_count == 0:
        title = "华润通签到成功 ✅"
    elif success_count == 0:
        title = "华润通签到失败 ❌"
    else:
        title = "华润通签到部分成功 ⚠️"

    content_parts = []
    for result in all_results:
        account_name = result.get('account_name', '未知账号')
        if result.get('success'):
            message = result.get('message', '签到成功')
            content_parts.append(f"✅ [{account_name}] {message}")
        else:
            error = result.get('error', '未知错误')
            if len(error) > 30:
                error = error[:30] + "..."
            content_parts.append(f"❌ [{account_name}] {error}")

    content_parts.append(f"\n⏱️ 耗时: {int(duration)}秒")
    return title, "\n".join(content_parts)


def main():
    """主函数"""
    start_time = datetime.now()
    print("=" * 50)
    print("华润通微信版签到脚本")
    print(f"开始时间: {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 50)
    print()

    accounts = load_accounts()

    if not accounts:
        print("❌ 未获取到 hrt_wx 环境变量或其中没有账号信息")
        return

    print(f"📋 共获取到 {len(accounts)} 个账号")

    all_results = []
    for index, account in enumerate(accounts):
        if not account.get('token'):
            print(f"⚠️  跳过账号 {account.get('account_name', '未知')}: token 为空")
            all_results.append({
                'account_name': account.get('account_name', '未知'),
                'success': False,
                'error': 'token为空'
            })
            continue

        result = process_account(account)
        all_results.append(result)

        if index < len(accounts) - 1:
            wait = random.randint(2, 5)
            print(f"等待 {wait} 秒后处理下一个账号...")
            time.sleep(wait)

    end_time = datetime.now()
    duration = (end_time - start_time).total_seconds()

    print("=" * 50)
    print("执行完成")
    print(f"结束时间: {end_time.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"执行耗时: {int(duration)} 秒")
    print("=" * 50)

    try:
        title, content = build_notification(all_results, start_time, end_time)
        send(title, content)
        print("✅ 推送通知发送成功")
    except Exception as e:
        print(f"❌ 推送通知失败: {str(e)}")


if __name__ == "__main__":
    main()
