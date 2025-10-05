# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目概述

这是一个青龙面板自动签到脚本集合仓库，主要包含各种平台的自动签到和任务脚本。项目使用 Python 和 JavaScript 编写，通过环境变量配置账号信息，支持多种消息推送方式。

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
3. **多账号支持**: 所有脚本支持多账号配置
4. **错误重试**: 网络请求包含重试机制 (通常3次)
5. **Session管理**: 使用 `requests.session()` 保持会话
6. **SSL验证**: 部分脚本禁用SSL验证 (`verify=False`)

## Git提交规范

根据提交历史，本项目使用以下提交前缀:
- `feat:` 新功能
- `fix:` 修复问题
- `refactor:` 重构代码
- `chore:` 杂项任务

提交信息使用中文，清晰描述变更内容。

## 测试和调试

由于脚本需要真实账号信息，建议:
1. 使用少量测试账号验证功能
2. 检查日志输出确认推送内容
3. 注意环境变量格式 (换行、`&`分隔等)
4. 关注API变化和活动时效性

## 安全注意事项

- 环境变量中存储敏感信息 (Cookie, Token等)
- 不要在代码中硬编码账号密码
- 推送日志已做脱敏处理 (如手机号中间4位隐藏)
- backup目录存放已停用脚本，避免不必要的运行
