# 青龙面板自动签到脚本集合

自动化签到脚本集合，支持多平台、多账号，适配青龙面板。

## ✨ 功能特点

- 🔄 **多平台支持** - 集成多个平台的自动签到脚本
- 👥 **多账号管理** - 支持同一平台多个账号批量签到
- 📢 **智能推送** - 关键词过滤，只推送重要信息
- 🔒 **安全配置** - 通过环境变量管理敏感信息，无需硬编码
- 🛡️ **容错机制** - 自动重试、异常捕获、降级处理
- 📱 **多种推送方式** - 支持 15+ 种消息推送服务

## 📋 支持的平台

### 活跃脚本

| 平台 | 脚本文件 | Cron 表达式 | 环境变量 |
|------|---------|------------|----------|
| 顺丰速运 | `sfsy.py` | `12 */6 * * *` | `sfsyUrl` |
| 一点万象 | `ydwx.py` | `2 8 * * *` | `ydwx_deviceParams`, `ydwx_token` |

### 备份脚本

`backup/` 目录包含已停用或历史版本的签到脚本，保留作为参考。

## 🚀 快速开始

### 方式一：青龙面板部署（推荐）

1. **拉取脚本仓库**
   ```bash
   ql repo https://github.com/byhooi/qinglong.git
   ```

2. **配置环境变量**

   在青龙面板中添加对应脚本的环境变量（详见下方配置说明）

3. **添加定时任务**

   根据脚本的 Cron 表达式添加定时任务，或手动运行测试

### 方式二：本地运行

1. **克隆仓库**
   ```bash
   git clone https://github.com/byhooi/qinglong.git
   cd qinglong
   ```

2. **安装依赖**
   ```bash
   pip install requests
   ```

3. **设置环境变量并运行**
   ```bash
   # Windows
   set sfsyUrl=你的URL
   python sfsy.py

   # Linux/macOS
   export sfsyUrl="你的URL"
   python sfsy.py
   ```

## ⚙️ 环境变量配置

### 顺丰速运 (sfsy.py)

**环境变量名**: `sfsyUrl`

**获取方式**:
1. 打开顺丰速运小程序或APP
2. 进入「我的」-「积分」
3. 抓取以下任意一种 URL:
   - `https://mcs-mimp-web.sf-express.com/mcs-mimp/share/weChat/shareGiftReceiveRedirect`
   - `https://mcs-mimp-web.sf-express.com/mcs-mimp/share/app/shareRedirect`
   - `https://mcs-mimp-web.sf-express.com/mcs-mimp/share/weChat/activityRedirect`

**多账号配置**: 使用换行符分隔多个 URL

**指定用户推送**: 在 URL 末尾添加 `@UID_xxx`

**示例**:
```
https://mcs-mimp-web.sf-express.com/mcs-mimp/share/weChat/activityRedirect?...
https://mcs-mimp-web.sf-express.com/mcs-mimp/share/weChat/activityRedirect?...@UID_123
```

### 一点万象 (ydwx.py)

**环境变量名**: `ydwx_deviceParams`, `ydwx_token`

**获取方式**:
1. 登录一点万象APP
2. 抓取 `https://app.mixcapp.com/mixc/gateway` 请求
3. 从请求体中提取 `deviceParams` 和 `token`

**多账号配置**: 使用 `&` 分隔多个账号

**示例**:
```
ydwx_deviceParams=设备参数1&设备参数2
ydwx_token=token1&token2
```

## 📢 推送通知配置

脚本支持多种推送方式，通过环境变量配置（选择其中一种即可）：

| 推送方式 | 环境变量 | 说明 |
|---------|---------|------|
| Bark | `BARK`, `BARK_PUSH` | iOS 推送通知 |
| Server酱 | `PUSH_KEY` | 微信推送 |
| Telegram | `TG_BOT_TOKEN`, `TG_USER_ID` | TG 机器人推送 |
| 钉钉 | `DD_BOT_TOKEN`, `DD_BOT_SECRET` | 钉钉群机器人 |
| 企业微信 | `QYWX_KEY`, `QYWX_AM` | 企业微信推送 |
| PushPlus | `PUSH_PLUS_TOKEN` | 微信推送Plus+ |
| 飞书 | `FS_KEY` | 飞书群机器人 |

更多推送方式详见 `sendNotify.py` 或 `sendNotify.js`

### 推送通知特点

- ✅ **关键词过滤** - 只推送包含关键信息的内容（签到结果、积分变化等）
- ✅ **完整日志** - 控制台始终打印所有日志，方便调试
- ✅ **统一推送** - 所有账号处理完成后统一推送，避免频繁通知

## 📝 注意事项

### 安全提示

- ⚠️ 所有敏感信息（Cookie, Token等）都应通过环境变量配置
- ⚠️ 切勿在代码中硬编码账号密码
- ⚠️ 推送日志已做脱敏处理（如手机号中间4位隐藏）
- ⚠️ 不要将包含敏感信息的配置文件提交到 Git

### 使用建议

- 📌 首次使用建议先用单个账号测试
- 📌 注意环境变量的分隔符格式（换行 vs `&`）
- 📌 定期检查脚本运行日志，关注API变化
- 📌 活动结束的脚本会移至 `backup/` 目录，请勿误用

## 🔧 开发相关

如需开发新的签到脚本或修改现有脚本，请参考 [CLAUDE.md](CLAUDE.md)，其中包含：

- 代码规范和设计模式
- 新增脚本的标准流程
- 关键实现细节
- 调试技巧和常见问题排查

## 📄 License

本项目仅供学习交流使用，请勿用于商业用途。

## 🤝 贡献

欢迎提交 Issue 和 Pull Request！

提交代码时请遵循项目的 Git 提交规范：

- `feat:` 新功能
- `fix:` 修复问题
- `refactor:` 重构代码
- `docs:` 文档更新
- `chore:` 杂项任务

提交信息使用中文，清晰描述变更内容。

## ⚠️ 免责声明

本项目仅供学习研究使用，使用本项目所产生的一切后果由使用者自行承担，与项目作者无关。请遵守相关平台的用户协议和服务条款。
