# dylan 系列脚本反混淆说明

`jd_OnceApply.js`、`jd_AutoEval.js` 这类来自 dylan（`t.me/dylan_jdpro`）的京东脚本是**混淆发布**的：
源码里看不到任何明文，排查问题（缺依赖、接口变了、cookie 类型对不上）时基本读不动。

本文记录这类脚本的混淆结构，以及配套的解码工具 `decode-dylan.js` 的用法和原理。

## 混淆结构

文件是「一行字符串表 + 一行业务代码」的形态，典型如 `jd_OnceApply.js`：

```
1-5    头部注释 + const $ = new Env('一键价保');
6      字符串表 + LZString + 解码函数 + 业务代码   （单行 10 万字符）
7      function Env(o,t){...}                      （日志/请求类）
```

解码链是三层叠加：

| 层 | 作用 |
|---|---|
| 数组表 | 所有字符串的密文，形如 `const zjkh3t=[0x0,null,0x20,...,"UA",...]` |
| 字符表变体 | 自定义 base64 字母表，如 `"A9dS<JT:>=uoWG,v.p!/7qw*ZMz@xm]%B0..."` |
| 变长编码 | 每个字符按 5 或 6 位打包（LZString 的 `_decompress` 变体） |

解码入口是形如 `xKYEU0(idx)` 的小函数，内部 `if (缓存未命中) return 缓存[i] = YEK25P(qc8mg5[i])`——
即「取字符表第 i 项 → 交给解码器还原」。**表和解码函数名每个脚本都不同**（`jd_OnceApply.js`
是 `zjkh3t`/`xKYEU0`，`jd_AutoEval.js` 是 `Ne6koN`/`cBfKBIC`），所以工具靠特征识别而非硬编码。

## 工具用法

```bash
# 列出全部明文（去重排序）
node tools/decode-dylan.js ../jdpro/jd_OnceApply.js

# 带来源标注（第几张表、哪个解码器、原始下标）
node tools/decode-dylan.js ../jdpro/jd_OnceApply.js --map

# 只查关键字
node tools/decode-dylan.js ../jdpro/jd_AutoEval.js --grep cookie
node tools/decode-dylan.js ../jdpro/jd_AutoEval.js --grep user-agent
```

结果输出到 stdout，统计信息输出到 stderr，因此可以直接重定向：

```bash
node tools/decode-dylan.js ../jdpro/jd_OnceApply.js > once.txt 2>/dev/null
```

实测效果：

| 脚本 | 顶层绑定 | 解码器 | 字符串表 | 明文 |
|---|---|---|---|---|
| `jd_OnceApply.js` | 20 | 1 | 1 | 125 |
| `jd_AutoEval.js` | 21 | 1 | 1 | 497 |

## 工具原理

### 1. 前缀切分

混淆器的初始化段以 `const X=$[<解码调用>]()?...` 开头（`$` 是 `Env` 实例，
第一个 `$[...]` 调用即业务代码起点）。以该特征为界，切出前面的「字符串表 + 解码函数」段。

> 为什么不取「第一个 `require(` 之前」？因为 `jd_AutoEval.js` 在混淆区中间就出现了
> `require(`，那样会切得过短、语法不完整。特征匹配失败时才回退到这个方式。

### 2. 沙箱执行 + 自动补桩

前缀会引用少量**定义在文件后段**的符号：`SeE5BEt`、`PYxAzG` 这类空操作包装
（文件末尾才定义成 `function SeE5BEt(){SeE5BEt=function(){}}`），以及脚本自带的 `Env` 类。

工具在 Node `vm` 沙箱里执行前缀，捕获 `ReferenceError: X is not defined`，
把 `X` 补成空桩函数后重跑，直到执行通过。**桩名因脚本而异，所以自动发现而不是硬编码。**

### 3. 导出顶层绑定

字符串表和解码函数多是顶层 `const`/`function`，不会挂到 `globalThis`，
从沙箱对象上直接取不到。因此把候选标识符拼成导出语句，与前缀放进**同一个 Script** 执行：

```js
try { __v = zjkh3t; if (__v !== undefined) __BINDINGS__.push(['zjkh3t', __v]); } catch (e) {}
```

候选标识符从**全文件**扫描（`const/let/var` 赋值 + `function` 声明）——因为
`jd_AutoEval.js` 的解码函数散布在文件后段。混进局部名没关系，`try/catch` 会兜住。

### 4. 交叉解码

一个脚本里往往有不止一层解码器（每层字符表不同）。工具用**每个候选解码函数**去解
**每张候选表**的每个元素，收集全部可打印结果 —— 比猜「哪个函数配哪张表」稳。

输出前过滤掉解码失败产生的乱码（控制字符、U+FFFD）。

## 局限性

- 解出的是**脚本中出现的字符串**，不是反编译后的可读源码；控制流仍是混淆的。
- 部分字符串要**运行时**才解密（依赖环境变量、接口返回值等），工具解不出，
  会以乱码形式被过滤掉，属正常现象。
- 工具只读源码，不执行脚本的业务逻辑，不会发网络请求。

## 相关记录

排查 `Cannot find module './sendNotify'` 时的结论：

- 报错原因是 `require('./sendNotify')` 按**脚本自身所在目录**解析，而该文件在仓库根目录
  （同目录的 `jd/jd_CheckCK.js` 用的是 `require('../sendNotify')`）。
- 这两个脚本依赖一整套 dylan 框架文件，仓库 `byhooi/jdpro` 里齐全：
  `jdCookie.js`、`USER_AGENTS.js`、`sendNotify.js`、`function/{dylib,dylans,dylanx,proxy,dyland,ql}.js`。
- 需安装的 npm 包：`got`、`tough-cookie`、`crypto-js`、`big-integer`、`axios`、`jsdom`、
  `https-proxy-agent`、`socks-proxy-agent`、`dotenv`、`ini`、`global-agent`、`tunnel`；
  `jd_AutoEval.js` 另需 `sharp`。
- **cookie 类型**：两者都走 H5/移动端接口（`api.m.jd.com/client.action?functionId=...`），
  用标准 `JD_COOKIE`（`pt_key=...;pt_pin=...`），不涉及 wskey / appid。
