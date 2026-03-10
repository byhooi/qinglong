"""
new Env('华润通999答题');
cron: 15 8 * * *
"""

"""
华润通999答题脚本
环境变量: hrt_999 (JSON格式)
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
from api import QuizAPI

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
    env_value = os.getenv('hrt_999', '')
    if not env_value:
        return []

    try:
        config = json.loads(env_value)
        return config.get('accounts', [])
    except json.JSONDecodeError:
        print("❌ 环境变量 hrt_999 格式错误，请检查JSON格式")
        return []


def find_correct_answer(question_data):
    """
    从题目数据中找出正确答案

    :param question_data: 题目数据
    :return: 正确答案的选项代码列表
    """
    options = question_data.get('question', {}).get('options', [])
    correct_options = []

    for option in options:
        if option.get('right'):
            correct_options.append(option.get('optionCode'))

    return correct_options


def process_account(account_config):
    """处理单个账号的答题"""
    account_name = account_config.get('account_name', '未知账号')
    mobile = account_config.get('mobile', '')

    # 初始化结果
    result_info = {
        'account_name': account_name,
        'mobile': mobile,
        'success': False,
        'error': None,
        'question': None,
        'answer': None
    }

    # 初始化 API
    api = QuizAPI(
        token=account_config["token"],
        mobile=mobile,
        user_agent=account_config.get("user_agent")
    )

    print("=" * 50)
    print(f"账号: {account_name} ({mobile})")
    print("开始答题...")
    print("=" * 50)

    # 获取题目
    print("\n📝 正在获取题目...")
    result = api.get_question()

    if result.get('resultCode') != '0':
        error_msg = result.get('message', '未知错误')
        print(f"❌ 获取题目失败: {error_msg}")
        result_info['error'] = f"获取题目失败: {error_msg}"
        return result_info

    # 解析题目
    question_data = result.get('data', {}).get('knowledgeQuestionData')
    if not question_data:
        print("❌ 题目数据为空")
        result_info['error'] = '题目数据为空'
        return result_info

    question_id = question_data.get('questionId')
    question_text = question_data.get('question', {}).get('questionContents', [''])[0]
    options = question_data.get('question', {}).get('options', [])

    # 限制题目长度用于通知
    result_info['question'] = question_text[:30] + '...' if len(question_text) > 30 else question_text

    print(f"\n题目: {question_text}")
    print("\n选项:")
    for option in options:
        option_code = option.get('optionCode')
        option_text = option.get('optionContents', [''])[0]
        is_right = "✅" if option.get('right') else ""
        print(f"  {option_code}. {option_text} {is_right}")

    # 找出正确答案
    correct_options = find_correct_answer(question_data)
    if not correct_options:
        print("\n❌ 未找到正确答案")
        result_info['error'] = '未找到正确答案'
        return result_info

    result_info['answer'] = ', '.join(correct_options)
    print(f"\n💡 正确答案: {result_info['answer']}")

    # 提交答案
    print("\n📤 正在提交答案...")
    submit_result = api.submit_answer(question_id, correct_options)

    if submit_result.get('resultCode') == '0':
        print("✅ 答题成功!")
        result_info['success'] = True
    else:
        error_msg = submit_result.get('message', '未知错误')
        print(f"❌ 答题失败: {error_msg}")
        result_info['error'] = f"答题失败: {error_msg}"

    print("\n" + "=" * 50)
    return result_info


def build_notification(all_results, start_time, end_time):
    """构建推送通知内容"""
    duration = (end_time - start_time).total_seconds()

    total_count = len(all_results)
    success_count = sum(1 for r in all_results if r.get('success'))
    failed_count = total_count - success_count

    if failed_count == 0:
        title = "华润通999答题成功 ✅"
    elif success_count == 0:
        title = "华润通999答题失败 ❌"
    else:
        title = "华润通999答题部分成功 ⚠️"

    content_parts = []
    for result in all_results:
        account_name = result.get('account_name', '未知账号')
        if result.get('success'):
            content_parts.append(f"✅ [{account_name}] 答题成功")
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
    print("华润通999答题脚本")
    print(f"开始时间: {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 50)
    print()

    accounts = load_accounts()

    if not accounts:
        print("❌ 未获取到 hrt_999 环境变量或其中没有账号信息")
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
