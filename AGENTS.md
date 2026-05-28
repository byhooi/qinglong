# Repository Guidelines

## Project Structure & Module Organization

本仓库是面向青龙面板的自动化脚本集合。根目录放通用脚本和通知模块，例如 `sendNotify.py`、`sendNotify.js`、`wskey.py`、`ydwx.py`。业务脚本按服务拆分目录，例如 `v2ex/main.py`、`huaruntong/huaruntong_wx/main.py`、`huaruntong/wentiweilaihui/api.py`。`backup/` 存放历史或备用脚本，修改前先确认是否仍被使用。

新增脚本优先放入独立目录，入口文件命名为 `main.py` 或清晰的 `*.js` 文件，并在文件顶部写明青龙任务名、cron 示例和所需环境变量。

## Build, Test, and Development Commands

本仓库没有统一构建流程。常用本地校验命令：

```powershell
python -m py_compile v2ex\main.py
python v2ex\main.py
node --check smzdm\smzdm_checkin.js
node smzdm\smzdm_checkin.js
```

`py_compile` 和 `node --check` 用于语法检查；直接运行脚本用于验证环境变量缺失、通知降级、异常处理等基础路径。

## Coding Style & Naming Conventions

Python 使用 4 空格缩进，函数和变量使用 `snake_case`，类名使用 `PascalCase`。JavaScript 使用 2 空格缩进，变量和函数使用 `camelCase`。代码注释、任务说明和环境变量说明使用中文。

脚本应从环境变量读取账号配置，不依赖本地 `config.json`。多账号建议支持 JSON 格式和换行或 `&` 分隔格式。通知优先复用根目录的 `sendNotify.py` 或 `sendNotify.js`，导入失败时应降级为控制台输出。

## Testing Guidelines

当前没有固定测试框架，也没有覆盖率要求。每次修改至少执行对应语言的语法检查，并测试无环境变量场景。涉及真实网络请求的脚本，应避免在代码中写入真实 cookie、token、手机号等敏感信息。

建议新增脚本时保留可验证的小函数，例如环境变量解析、结果格式化、通知内容构建，便于后续补充单元测试。

## Commit & Pull Request Guidelines

历史提交以简短中文说明为主，例如“新增 V2EX 每日签到脚本及相关功能”，也存在 `fix` 这类简略提交。新提交建议使用明确动宾结构：`修复 V2EX Cookie 解析`、`新增 SMZDM 签到脚本`。

PR 或变更说明应包含：修改目的、涉及文件、所需环境变量、已运行的验证命令，以及是否需要真实账号或网络环境复测。

## Security & Configuration Tips

不要提交真实 Cookie、Token、账号密码或推送密钥。示例配置使用 `xxx` 占位。处理日志时避免完整打印敏感请求头；必要时只打印账号序号、昵称或脱敏后的标识。
