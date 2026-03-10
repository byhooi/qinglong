"""
new Env('华润通文体未来荟签到');
cron: 10 8 * * *
"""

"""
文体未来荟签到脚本
环境变量: wentiweilaihui (JSON格式)
格式示例: {"accounts":[{"account_name":"账号1","token":"xxx","mobile":"138xxx"},{"account_name":"账号2","token":"yyy","mobile":"139xxx"}]}
多账号在 accounts 数组中添加即可
"""
import json
import os
import sys
import time
import random
from datetime import datetime
from pathlib import Path
from api import WenTiWeiLaiHuiAPI

# 添加项目根目录到Python路径以导入sendNotify模块
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
    env_value = os.getenv('wentiweilaihui', '')
    if not env_value:
        return []

    try:
        config = json.loads(env_value)
        return config.get('accounts', [])
    except json.JSONDecodeError:
        print("❌ 环境变量 wentiweilaihui 格式错误，请检查JSON格式")
        return []


def process_account(account_config):
    """处理单个账号的签到"""
    account_name = account_config.get('account_name', '未知账号')
    token = account_config.get('token')
    mobile = account_config.get('mobile')

    # 初始化结果
    result_info = {
        'account_name': account_name,
        'mobile': mobile,
        'success': False,
        'error': None,
        'sign_message': None,
        'points': None,
        'available_points': None
    }

    print("=" * 50)
    print(f"账号: {account_name} ({mobile})")
    print("=" * 50)

    # 创建API实例
    api = WenTiWeiLaiHuiAPI(token, mobile, account_config.get('user_agent'))

    # 执行签到
    print("\n开始签到...")
    sign_result = api.sign_in()

    if sign_result.get("success"):
        msg = sign_result.get('msg', '签到成功')
        print(f"✓ 签到成功: {msg}")
        result_info['sign_message'] = msg
    else:
        msg = sign_result.get('msg', '签到失败')
        print(f"✗ 签到失败: {msg}")
        result_info['error'] = msg

    # 查询积分
    print("\n查询万象星积分...")
    points_result = api.query_points()

    if points_result.get("success"):
        data = points_result.get("data", {})
        points = data.get("points", 0)
        available_points = data.get("availablePoints", 0)
        hold_points = data.get("holdPoints", 0)

        print(f"✓ 查询成功")
        print(f"  总积分: {points}")
        print(f"  可用积分: {available_points}")
        print(f"  冻结积分: {hold_points}")

        result_info['points'] = points
        result_info['available_points'] = available_points
        result_info['success'] = True
    else:
        msg = points_result.get('msg', '查询失败')
        print(f"✗ 查询失败: {msg}")
        if not result_info['error']:
            result_info['error'] = msg

    print("\n" + "=" * 50)
    return result_info


def build_notification(all_results, start_time, end_time):
    """构建推送通知内容"""
    duration = (end_time - start_time).total_seconds()

    # 统计结果
    total_count = len(all_results)
    success_count = sum(1 for r in all_results if r.get('success'))
    failed_count = total_count - success_count

    # 构建通知标题
    if failed_count == 0:
        title = "文体未来荟签到成功 ✅"
    elif success_count == 0:
        title = "文体未来荟签到失败 ❌"
    else:
        title = "文体未来荟签到部分成功 ⚠️"

    # 构建通知内容
    content_parts = []

    for result in all_results:
        account_name = result.get('account_name', '未知账号')
        if result.get('success'):
            points = result.get('points', 0)
            available = result.get('available_points', 0)
            content_parts.append(f"✅ [{account_name}] 总积分: {points} | 可用: {available}")
        else:
            error = result.get('error', '未知错误')
            if len(error) > 30:
                error = error[:30] + "..."
            content_parts.append(f"❌ [{account_name}] {error}")

    content_parts.append(f"\n⏱️ 耗时: {int(duration)}秒")

    return title, "\n".join(content_parts)


def main():
    """主函数"""
    # 记录开始时间
    start_time = datetime.now()
    print("=" * 50)
    print("文体未来荟签到脚本")
    print(f"开始时间: {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 50)
    print()

    # 加载配置
    accounts = load_accounts()

    if not accounts:
        print("❌ 未获取到 wentiweilaihui 环境变量或其中没有账号信息")
        return

    print(f"📋 共获取到 {len(accounts)} 个账号")

    # 收集所有账号的结果
    all_results = []

    # 遍历所有账号
    for index, account in enumerate(accounts):
        if not account.get('token'):
            print(f"⚠️  跳过账号 {account.get('account_name', '未知')}: token 为空")
            print("=" * 50)
            all_results.append({
                'account_name': account.get('account_name', '未知'),
                'success': False,
                'error': 'token为空'
            })
            continue

        result = process_account(account)
        all_results.append(result)

        # 多账号间加延时
        if index < len(accounts) - 1:
            wait = random.randint(2, 5)
            print(f"等待 {wait} 秒后处理下一个账号...")
            time.sleep(wait)

    # 记录结束时间
    end_time = datetime.now()
    duration = (end_time - start_time).total_seconds()

    print("=" * 50)
    print("执行完成")
    print(f"结束时间: {end_time.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"执行耗时: {int(duration)} 秒")
    print("=" * 50)

    # 发送推送通知
    try:
        title, content = build_notification(all_results, start_time, end_time)
        send(title, content)
        print("✅ 推送通知发送成功")
    except Exception as e:
        print(f"❌ 推送通知失败: {str(e)}")


if __name__ == "__main__":
    main()
