# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目概述

这是一个青龙面板自动签到脚本集合仓库，主要包含各种平台的自动签到和任务脚本。项目使用 Python 和 JavaScript 编写，通过环境变量配置账号信息，支持多种消息推送方式。

**核心设计理念**:
- **零硬编码**: 所有敏感信息通过环境变量配置
- **智能推送**: 关键词过滤机制，只推送重要信息
- **容错处理**: 自动重试、异常捕获、降级处理
- **多账号支持**: 统一的多账号处理架构

## 脚本类型和结构

### 主要脚本

1. **顺丰速运签到** (`sfsy.py`)
   - Cron: `12 */6 * * *`
   - 环境变量: `sfsyUrl` (URL格式，多账号换行分割)
   - 支持功能: 签到、会员日任务、积分查询
   - 可选: 末尾添加 `@UID_xxx` 指定特定用户推送

2. **一点万象签到** (`ydwx.py`)
   - Cron: `2 8 * * *`
   - 环境变量: `ydwx_deviceParams`, `ydwx_token` (多账号用 `&` 分隔)

3. **备份脚本** (`backup/`)
   - 包含已停用或历史版本的签到脚本
   - 如: GLaDOS、999会员中心、混合公园等

### 推送通知模块

两个通知模块可互换使用:

- `sendNotify.js` (JavaScript版本)
- `sendNotify.py` (Python版本)

支持的推送方式:
- Bark
- Server酱 (PUSH_KEY)
- Telegram Bot (TG_BOT_TOKEN, TG_USER_ID)
- 钉钉机器人 (DD_BOT_TOKEN, DD_BOT_SECRET)
- 企业微信 (QYWX_KEY, QYWX_AM)
- PushPlus (PUSH_PLUS_TOKEN)
- 飞书 (FS_KEY)
- gotify, go-cqhttp, iGot 等

## 环境变量配置

所有脚本通过环境变量获取配置，支持以下方式:
- 青龙面板环境变量
- 系统环境变量 (`os.environ`)
- GitHub Actions Secrets

## 代码规范

### Python脚本结构
```python
#!/usr/bin/python3
# -*- coding: utf-8 -*-
"""
new Env('脚本名称');
Cron:"执行时间";
"""

# 导入通知模块
try:
    from notify import send
except:
    def send(title, content):
        print(f"\n{title}\n{content}")
```

### 关键设计模式

1. **日志系统**: 使用全局 `send_msg` 和 `one_msg` 收集日志
2. **关键词过滤**: 只推送包含关键词的重要信息，减少推送噪音
   - 在 `Log()` 函数中定义 `push_keywords` 列表
   - 控制台始终打印所有日志，推送仅包含关键词的信息
3. **多账号支持**: 所有脚本支持多账号配置
   - 环境变量使用换行符 (`\n`) 或 `&` 分隔多账号
   - 支持 `@UID_xxx` 后缀指定特定用户推送
4. **错误重试**: 网络请求包含重试机制 (通常3次)
5. **Session管理**: 使用 `requests.session()` 保持会话
6. **SSL验证**: 部分脚本禁用SSL验证 (`verify=False`)
7. **统一推送**: 所有账号处理完成后统一调用 `send()` 推送，避免频繁通知

### 关键实现细节

**签名生成** (`sfsy.py` 为例):
- 使用 MD5 签名验证请求
- 时间戳 + token + sysCode 组合生成签名
- `getSign()` 方法自动更新请求头

**日期条件任务** (如会员日):
- 使用 `datetime.now().day` 判断日期范围
- 只在特定日期执行，非执行时间不推送通知

**API请求封装**:
- `do_request()` 统一处理 GET/POST 请求
- 自动重试、超时控制、异常捕获
- 返回标准化 JSON 格式

**通知模块架构**:
- `sendNotify.py` 和 `sendNotify.js` 功能完全等价
- 支持 15+ 种推送方式，通过环境变量配置
- 推送配置优先级: 环境变量 > 脚本内默认值
- 超时时间统一为 15 秒

## Git提交规范

根据提交历史，本项目使用以下提交前缀:
- `feat:` 新功能
- `fix:` 修复问题
- `refactor:` 重构代码
- `docs:` 文档更新
- `chore:` 杂项任务

提交信息使用中文，清晰描述变更内容。

## 开发工作流

### 新增签到脚本的标准流程

1. **选择语言和模板**
   - Python脚本: 参考 `sfsy.py` (复杂API交互) 或 `ydwx.py` (简单签到)
   - JavaScript脚本: 参考 `backup/mixpark.js`

2. **实现核心功能**
   - 添加脚本头部注释 (`new Env`, `Cron`)
   - 实现登录和签到逻辑
   - 添加重试机制和错误处理
   - 使用 `send_msg` 和 `one_msg` 收集日志

3. **配置推送通知**
   - 导入 `notify.send` 或 `sendNotify.send`
   - 定义 `push_keywords` 过滤重要信息
   - 统一推送: 所有账号处理完成后调用一次 `send()`

4. **测试和调试**
   - 设置环境变量测试
   - 验证多账号支持
   - 检查日志输出和推送内容

5. **文档更新**
   - 在本文件中添加脚本说明
   - 更新环境变量配置说明

### 停用脚本的处理

当某个平台活动结束或API失效时:
1. 将脚本移至 `backup/` 目录
2. 提交信息使用 `refactor: 停用xxx签到` 格式
3. 不删除代码，保留作为参考

## 常用命令

**本地测试脚本**:
```bash
# Python 脚本
python sfsy.py
python ydwx.py

# 设置环境变量后运行 (Windows)
set sfsyUrl=你的URL
python sfsy.py

# 设置环境变量后运行 (Linux/macOS)
export sfsyUrl="你的URL"
python sfsy.py
```

**青龙面板部署**:
1. 在青龙面板添加环境变量
2. 添加定时任务，配置 Cron 表达式
3. 手动运行或等待定时执行

**Git操作**:
```bash
# 查看仓库状态
git status

# 提交更改
git add .
git commit -m "feat: 添加xxx签到脚本"

# 推送到远程
git push origin master
```

## 测试和调试

### 本地测试建议
由于脚本需要真实账号信息:
1. 使用少量测试账号验证功能
2. 检查日志输出确认推送内容
3. 注意环境变量格式 (换行、`&`分隔等)
4. 关注API变化和活动时效性

### 调试技巧
- **查看完整日志**: 所有日志都会在控制台打印，推送仅包含关键信息
- **测试单账号**: 使用单个账号的环境变量快速验证逻辑
- **模拟API响应**: 修改代码临时返回固定 JSON 测试边界情况
- **检查签名**: 对于需要签名的API，打印签名前的字符串对比

### 常见问题排查
- **签到失败**: 检查 URL 格式是否正确，token 是否过期
- **无推送通知**: 确认推送配置环境变量已设置，检查关键词过滤
- **多账号失败**: 检查分隔符是否正确 (换行 vs `&`)
- **网络错误**: 检查代理设置，某些脚本禁用了 SSL 验证

## 安全注意事项

- 环境变量中存储敏感信息 (Cookie, Token等)
- 不要在代码中硬编码账号密码
- 推送日志已做脱敏处理 (如手机号中间4位隐藏)
- backup目录存放已停用脚本，避免不必要的运行
