/*
cron "10 8,22 * * *" jd_CheckCK.js, tag:京东CK检测by-ccwav
 */
// 原版说明参考 https://github.com/ccwav/QLScript2, 本文件为适配本仓库的精简版
//
// 功能: 检测青龙面板中所有 JD_COOKIE 的有效性, 失效自动禁用, 恢复可选自动启用, 结果按分组汇总后统一推送
// 依赖: 仓库根目录 sendNotify.js (推送, 缺失时降级为日志输出)、同目录 function/ql.js (青龙 API 封装)
//       function/ql.js 只需提供 getEnvs / getstatus / DisableCk / EnableCk 四个方法, 可直接使用 ccwav/QLScript2 仓库的同名文件
// 环境变量 (均可选):
//   CHECKCK_SHOWSUCCESSCK  = true       推送中附带有效账号列表
//   CHECKCK_CKALWAYSNOTIFY = true       即使没有任何变化也推送
//   CHECKCK_CKAUTOENABLE   = true       已恢复的账号自动启用 (默认只提示)
//   CHECKCK_CKNOWARNERROR  = true       检测出错的账号不触发推送
//   CHECKCK_ALLNOTIFY      = 文本        在推送内容末尾附加的温馨提示
//   BEANCHANGE_USERGP2/3/4 = pin1&pin2  按 pt_pin 分组, 每组单独汇总推送, 未分组账号走默认推送
//   WP_APP_TOKEN_ONE       = token      WxPusher 一对一推送 (需 sendNotify.js 提供 sendNotifybyWxPucher, 本仓库版本不支持时自动跳过)
//   QL_PORT                = 5700       青龙面板端口 (仅本仓库自带的 function/ql.js 读取, 上游 ql.js 固定走 5600)
const $ = new Env('CK检测');
const {
    getEnvs,
    DisableCk,
    EnableCk,
    getstatus
} = require('./function/ql');

let notify = null;
try {
    notify = require('../sendNotify'); // 脚本位于 jd/ 子目录, 推送模块在仓库根目录
} catch (e) {
    console.log(`⚠️ 未加载 sendNotify.js, 通知仅输出到日志: ${e.message}`);
}

const envFlag = (name) => String(process.env[name] || '').trim().toLowerCase() === 'true';
const ShowSuccess = envFlag('CHECKCK_SHOWSUCCESSCK');
const CKAlwaysNotify = envFlag('CHECKCK_CKALWAYSNOTIFY');
const CKAutoEnable = envFlag('CHECKCK_CKAUTOENABLE');
const NoWarnError = envFlag('CHECKCK_CKNOWARNERROR');
const WP_APP_TOKEN_ONE = process.env.WP_APP_TOKEN_ONE || '';
const BEAN_URL = 'https://bean.m.jd.com/beanDetail/index.action?resourceValue=bean';

let strAllNotify = '';
if (process.env.CHECKCK_ALLNOTIFY) {
    console.log(`检测到设定了温馨提示,将在推送信息中置顶显示...`);
    strAllNotify = `\n【✨✨✨✨温馨提示✨✨✨✨】\n` + process.env.CHECKCK_ALLNOTIFY;
    console.log(strAllNotify);
}

let cookie = '';

// 推送分组: 每个分组独立累计五类消息, 脚本结束时各自汇总推送一次
function newBucket(title, pins) {
    return { title, pins, index: 0, oerror: '', disable: '', enable: '', error: '', success: '' };
}
const buckets = [];
[2, 3, 4].forEach((n) => {
    const raw = process.env[`BEANCHANGE_USERGP${n}`];
    if (raw) {
        console.log(`检测到设定了分组推送${n}`);
        buckets.push(newBucket(`京东CK检测#${n}`, raw.split('&').map((p) => p.trim()).filter(Boolean)));
    }
});
const defaultBucket = newBucket($.name, []);

// 汇总推送 (缺少 sendNotify.js 时只打印)
async function pushNotify(title, content, params) {
    if (notify && typeof notify.sendNotify === 'function') {
        try {
            await notify.sendNotify(title, content, params);
        } catch (e) {
            console.log(`⚠️ 推送失败: ${e.message}`);
        }
    } else {
        console.log(`\n${title}\n${content}`);
    }
}

// WxPusher 一对一推送: 仅在设置 WP_APP_TOKEN_ONE 且 sendNotify.js 支持时发送, 否则跳过而不是报错
async function notifyOne(title, content, pin) {
    if (!WP_APP_TOKEN_ONE) return;
    if (notify && typeof notify.sendNotifybyWxPucher === 'function') {
        try {
            await notify.sendNotifybyWxPucher(title, content, pin);
        } catch (e) {
            console.log(`⚠️ 一对一推送失败: ${e.message}`);
        }
    } else {
        console.log(`⚠️ 当前 sendNotify.js 不支持 WxPusher 一对一推送(sendNotifybyWxPucher), 已跳过 ${pin} 的单独通知`);
    }
}

function buildSummary(b) {
    let msg = '';
    if (b.oerror) {
        msg += `👇👇👇👇👇检测出错账号👇👇👇👇👇\n` + b.oerror + `\n\n`;
    }
    if (b.disable) {
        msg += `👇👇👇👇👇自动禁用账号👇👇👇👇👇\n` + b.disable + `\n\n`;
    }
    if (b.enable) {
        msg += (CKAutoEnable ? `👇👇👇👇👇自动启用账号👇👇👇👇👇\n` : `👇👇👇👇👇账号已恢复👇👇👇👇👇\n`) + b.enable + `\n\n`;
    }
    msg += `👇👇👇👇👇失效账号👇👇👇👇👇\n` + (b.error || ` 一个失效的都没有呢，羡慕啊...\n`) + `\n\n`;
    if (ShowSuccess && b.success) {
        msg += `👇👇👇👇👇有效账号👇👇👇👇👇\n` + b.success + `\n`;
    }
    return msg;
}

async function pushSummary(b) {
    if (b.index === 0) return; // 该分组没有账号
    const needNotify = b.enable || b.disable || (b.oerror && !NoWarnError) || CKAlwaysNotify;
    if (!needNotify) return;
    let msg = buildSummary(b);
    console.log(`${b.title}：`);
    console.log(msg);
    if (strAllNotify) msg += `\n` + strAllNotify;
    await pushNotify(b.title, msg, { url: BEAN_URL });
}

!(async () => {
    // 不依赖 ql.js 是否已按名称过滤, 这里自己只保留 JD_COOKIE
    const envs = ((await getEnvs()) || []).filter((env) => env && env.name === 'JD_COOKIE');
    if (!envs.length) {
        $.msg($.name, '【提示】请先获取京东账号一cookie\n直接使用NobyDa的京东签到获取', 'https://bean.m.jd.com/bean/signIndex.action', {
            "open-url": "https://bean.m.jd.com/bean/signIndex.action"
        });
        return;
    }
    $.log(`\n默认不自动启用CK，开启变量CHECKCK_CKAUTOENABLE='true'`);
    for (let i = 0; i < envs.length; i++) {
        const env = envs[i];
        if (!env.value) continue;
        const tempid = env._id !== undefined ? env._id : env.id;
        cookie = env.value;
        const pinMatch = cookie.match(/pt_pin=([^; ]+)(?=;?)/);
        if (!pinMatch) {
            console.log(`【京东账号${i + 1}】变量值中没有 pt_pin, 跳过\n`);
            continue;
        }
        $.UserName = pinMatch[1];
        $.UserName2 = decodeURIComponent($.UserName);
        $.index = i + 1;
        $.isLogin = true;
        $.error = '';
        $.NoReturn = '';
        $.nickName = '';

        console.log(`开始检测【京东账号${$.index}】${$.UserName2} ....\n`);
        const targets = buckets.filter((b) => b.pins.includes($.UserName) || b.pins.includes($.UserName2));
        if (targets.length) {
            console.log(`账号属于${targets.map((b) => b.title).join('、')}`);
        } else {
            console.log(`账号没有分组`);
            targets.push(defaultBucket);
        }

        await TotalBean();
        if ($.NoReturn) {
            console.log(`接口1检测失败，尝试使用接口2....\n`);
            await isLoginByX1a0He();
        } else if ($.isLogin) {
            if (!$.nickName) {
                console.log(`获取的别名为空，尝试使用接口2验证....\n`);
                await isLoginByX1a0He();
            } else {
                console.log(`成功获取到别名: ${$.nickName},Pass!\n`);
            }
        }

        // results: 本账号要写入所属分组的消息; field 对应分组的五类消息, raw 表示不加账号标题前缀
        const results = [];
        if ($.error) {
            console.log(`有错误，跳出....`);
            results.push({ field: 'oerror', text: $.error, raw: true });
        } else {
            let strnowstatus = await getstatus(tempid);
            if (strnowstatus == 99) {
                strnowstatus = env.status;
            }
            const showName = $.nickName || $.UserName2;
            if (!$.isLogin) {
                if (strnowstatus == 0) {
                    const DisableCkBody = await DisableCk(tempid);
                    const ok = DisableCkBody.code == 200;
                    let oneMsg = `京东账号: ${showName} 已失效${ok ? ',自动禁用成功!' : '!'}\n如果要继续挂机，请联系管理员重新登录账号，账号有效期为30天.`;
                    if (strAllNotify) oneMsg += `\n` + strAllNotify;
                    await notifyOne($.name, oneMsg, $.UserName2);
                    console.log(`京东账号${$.index} : ${showName} 已失效,自动禁用${ok ? '成功' : '失败'}!\n`);
                    results.push({ field: 'disable', text: ` (自动禁用${ok ? '成功' : '失败'}!)\n` });
                    results.push({ field: 'error', text: ` 已失效,自动禁用${ok ? '成功' : '失败'}!\n` });
                } else {
                    console.log(`京东账号${$.index} : ${showName} 已失效,已禁用!\n`);
                    results.push({ field: 'error', text: ` 已失效,已禁用.\n` });
                }
            } else if (strnowstatus == 1) {
                if (CKAutoEnable) {
                    const EnableCkBody = await EnableCk(tempid);
                    const ok = EnableCkBody.code == 200;
                    await notifyOne($.name, ok
                        ? `京东账号: ${showName} 已恢复,自动启用成功!\n祝您挂机愉快...`
                        : `京东账号: ${showName} 已恢复,但自动启用失败!\n请联系管理员处理...`, $.UserName2);
                    console.log(`京东账号${$.index} : ${showName} 已恢复,${ok ? '自动启用成功' : '但自动启用失败'}!\n`);
                    results.push({ field: 'enable', text: ` (自动启用${ok ? '成功' : '失败'}!)\n` });
                    if (ok) results.push({ field: 'success', text: ` (自动启用成功!)\n` });
                } else {
                    console.log(`京东账号${$.index} : ${showName} 已恢复，可手动启用!\n`);
                    results.push({ field: 'enable', text: ` 已恢复，可手动启用.\n` });
                }
            } else {
                console.log(`京东账号${$.index} : ${showName} 状态正常!\n`);
                results.push({ field: 'success', text: `\n` });
            }
        }

        for (const bucket of targets) {
            bucket.index += 1;
            const title = `【账号${bucket.index}🆔】${$.UserName2}`;
            for (const r of results) {
                bucket[r.field] += r.raw ? r.text : title + r.text;
            }
        }

        if (i < envs.length - 1) {
            console.log(`等待2秒.......\n`);
            await $.wait(2 * 1000);
        }
    }

    for (const bucket of [...buckets, defaultBucket]) {
        await pushSummary(bucket);
    }
})()
.catch((e) => $.logErr(e))
.finally(() => $.done())

function TotalBean() {
    return new Promise(async resolve => {
        const options = {
            url: "https://me-api.jd.com/user_new/info/GetJDUserInfoUnion",
            headers: {
                Host: "me-api.jd.com",
                Accept: "*/*",
                Connection: "keep-alive",
                Cookie: cookie,
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/106.0.0.0 Safari/537.36 Edg/106.0.1370.42",
                "Accept-Language": "zh-cn",
                "Referer": "https://home.m.jd.com/myJd/newhome.action?sceneval=2&ufc=&",
                "Accept-Encoding": "gzip, deflate, br"
            }
        }
        $.get(options, (err, resp, data) => {
            try {
                if (err) {
                    $.logErr(err)
                    $.nickName = decodeURIComponent($.UserName);
                    $.NoReturn = `${$.nickName} :` + `${JSON.stringify(err)}\n`;
                } else {
                    if (data) {
                        data = JSON.parse(data);
                        if (data['retcode'] === "1001") {
                            $.isLogin = false; //cookie过期
                            $.nickName = decodeURIComponent($.UserName);
                            return;
                        }
                        if (data['retcode'] === "0" && data.data && data.data.hasOwnProperty("userInfo")) {
                            $.nickName = (data.data.userInfo.baseInfo.nickname);
                        } else {
                            $.nickName = decodeURIComponent($.UserName);
                            console.log("Debug Code:" + data['retcode']);
                            $.NoReturn = `${$.nickName} :` + `服务器返回未知状态，不做变动\n`;
                        }
                    } else {
                        $.nickName = decodeURIComponent($.UserName);
                        $.log('京东服务器返回空数据');
                        $.NoReturn = `${$.nickName} :` + `服务器返回空数据，不做变动\n`;
                    }
                }
            } catch (e) {
                $.nickName = decodeURIComponent($.UserName);
                $.logErr(e)
                $.NoReturn = `${$.nickName} : 检测出错，不做变动\n`;
            }
            finally {
                resolve();
            }
        })
    })
}
// 接口2: 接口1无响应或拿不到别名时的二次验证; 接口2 也无响应时记为检测出错, 避免把网络故障误判成有效
function isLoginByX1a0He() {
    return new Promise((resolve) => {
        const options = {
            url: 'https://plogin.m.jd.com/cgi-bin/ml/islogin',
            headers: {
                "Cookie": cookie,
                "referer": "https://h5.m.jd.com/",
                "User-Agent": "jdapp;iPhone;10.1.2;15.0;network/wifi;Mozilla/5.0 (iPhone; CPU iPhone OS 15_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148;supportJDSHWK/1",
            },
        }
        $.get(options, (err, resp, data) => {
            try {
                if (err || !data) {
                    console.log(`使用X1a0He写的接口加强检测: 接口无响应，不作变更...\n`)
                    $.error = `${$.nickName || $.UserName2} :` + `使用X1a0He写的接口加强检测: 接口无响应...\n`
                } else {
                    data = JSON.parse(data);
                    if (data.islogin === "1") {
                        console.log(`使用X1a0He写的接口加强检测: Cookie有效\n`)
                    } else if (data.islogin === "0") {
                        $.isLogin = false;
                        console.log(`使用X1a0He写的接口加强检测: Cookie无效\n`)
                    } else {
                        console.log(`使用X1a0He写的接口加强检测: 未知返回，不作变更...\n`)
                        $.error = `${$.nickName || $.UserName2} :` + `使用X1a0He写的接口加强检测: 未知返回...\n`
                    }
                }
            } catch (e) {
                console.log(e);
                $.error = `${$.nickName || $.UserName2} :` + `使用X1a0He写的接口加强检测: 返回解析失败...\n`
            }
            finally {
                resolve();
            }
        });
    });
}

// prettier-ignore
function Env(t, e) {
    "undefined" != typeof process && JSON.stringify(process.env).indexOf("GITHUB") > -1 && process.exit(0);
    class s {
        constructor(t) {
            this.env = t
        }
        send(t, e = "GET") {
            t = "string" == typeof t ? {
                url: t
            }
             : t;
            let s = this.get;
            return "POST" === e && (s = this.post),
            new Promise((e, i) => {
                s.call(this, t, (t, s, r) => {
                    t ? i(t) : e(s)
                })
            })
        }
        get(t) {
            return this.send.call(this.env, t)
        }
        post(t) {
            return this.send.call(this.env, t, "POST")
        }
    }
    return new class {
        constructor(t, e) {
            this.name = t,
            this.http = new s(this),
            this.data = null,
            this.dataFile = "box.dat",
            this.logs = [],
            this.isMute = !1,
            this.isNeedRewrite = !1,
            this.logSeparator = "\n",
            this.startTime = (new Date).getTime(),
            Object.assign(this, e),
            this.log("", `🔔${this.name}, 开始!`)
        }
        isNode() {
            return "undefined" != typeof module && !!module.exports
        }
        isQuanX() {
            return "undefined" != typeof $task
        }
        isSurge() {
            return "undefined" != typeof $httpClient && "undefined" == typeof $loon
        }
        isLoon() {
            return "undefined" != typeof $loon
        }
        toObj(t, e = null) {
            try {
                return JSON.parse(t)
            } catch {
                return e
            }
        }
        toStr(t, e = null) {
            try {
                return JSON.stringify(t)
            } catch {
                return e
            }
        }
        getjson(t, e) {
            let s = e;
            const i = this.getdata(t);
            if (i)
                try {
                    s = JSON.parse(this.getdata(t))
                } catch {}
            return s
        }
        setjson(t, e) {
            try {
                return this.setdata(JSON.stringify(t), e)
            } catch {
                return !1
            }
        }
        getScript(t) {
            return new Promise(e => {
                this.get({
                    url: t
                }, (t, s, i) => e(i))
            })
        }
        runScript(t, e) {
            return new Promise(s => {
                let i = this.getdata("@chavy_boxjs_userCfgs.httpapi");
                i = i ? i.replace(/\n/g, "").trim() : i;
                let r = this.getdata("@chavy_boxjs_userCfgs.httpapi_timeout");
                r = r ? 1 * r : 20,
                r = e && e.timeout ? e.timeout : r;
                const[o, h] = i.split("@"),
                n = {
                    url: `http://${h}/v1/scripting/evaluate`,
                    body: {
                        script_text: t,
                        mock_type: "cron",
                        timeout: r
                    },
                    headers: {
                        "X-Key": o,
                        Accept: "*/*"
                    }
                };
                this.post(n, (t, e, i) => s(i))
            }).catch(t => this.logErr(t))
        }
        loaddata() {
            if (!this.isNode())
                return {}; {
                this.fs = this.fs ? this.fs : require("fs"),
                this.path = this.path ? this.path : require("path");
                const t = this.path.resolve(this.dataFile),
                e = this.path.resolve(process.cwd(), this.dataFile),
                s = this.fs.existsSync(t),
                i = !s && this.fs.existsSync(e);
                if (!s && !i)
                    return {}; {
                    const i = s ? t : e;
                    try {
                        return JSON.parse(this.fs.readFileSync(i))
                    } catch (t) {
                        return {}
                    }
                }
            }
        }
        writedata() {
            if (this.isNode()) {
                this.fs = this.fs ? this.fs : require("fs"),
                this.path = this.path ? this.path : require("path");
                const t = this.path.resolve(this.dataFile),
                e = this.path.resolve(process.cwd(), this.dataFile),
                s = this.fs.existsSync(t),
                i = !s && this.fs.existsSync(e),
                r = JSON.stringify(this.data);
                s ? this.fs.writeFileSync(t, r) : i ? this.fs.writeFileSync(e, r) : this.fs.writeFileSync(t, r)
            }
        }
        lodash_get(t, e, s) {
            const i = e.replace(/\[(\d+)\]/g, ".$1").split(".");
            let r = t;
            for (const t of i)
                if (r = Object(r)[t], void 0 === r)
                    return s;
            return r
        }
        lodash_set(t, e, s) {
            return Object(t) !== t ? t : (Array.isArray(e) || (e = e.toString().match(/[^.[\]]+/g) || []), e.slice(0, -1).reduce((t, s, i) => Object(t[s]) === t[s] ? t[s] : t[s] = Math.abs(e[i + 1]) >> 0 == +e[i + 1] ? [] : {}, t)[e[e.length - 1]] = s, t)
        }
        getdata(t) {
            let e = this.getval(t);
            if (/^@/.test(t)) {
                const[, s, i] = /^@(.*?)\.(.*?)$/.exec(t),
                r = s ? this.getval(s) : "";
                if (r)
                    try {
                        const t = JSON.parse(r);
                        e = t ? this.lodash_get(t, i, "") : e
                    } catch (t) {
                        e = ""
                    }
            }
            return e
        }
        setdata(t, e) {
            let s = !1;
            if (/^@/.test(e)) {
                const[, i, r] = /^@(.*?)\.(.*?)$/.exec(e),
                o = this.getval(i),
                h = i ? "null" === o ? null : o || "{}" : "{}";
                try {
                    const e = JSON.parse(h);
                    this.lodash_set(e, r, t),
                    s = this.setval(JSON.stringify(e), i)
                } catch (e) {
                    const o = {};
                    this.lodash_set(o, r, t),
                    s = this.setval(JSON.stringify(o), i)
                }
            } else
                s = this.setval(t, e);
            return s
        }
        getval(t) {
            return this.isSurge() || this.isLoon() ? $persistentStore.read(t) : this.isQuanX() ? $prefs.valueForKey(t) : this.isNode() ? (this.data = this.loaddata(), this.data[t]) : this.data && this.data[t] || null
        }
        setval(t, e) {
            return this.isSurge() || this.isLoon() ? $persistentStore.write(t, e) : this.isQuanX() ? $prefs.setValueForKey(t, e) : this.isNode() ? (this.data = this.loaddata(), this.data[e] = t, this.writedata(), !0) : this.data && this.data[e] || null
        }
        initGotEnv(t) {
            this.got = this.got ? this.got : require("got"),
            this.cktough = this.cktough ? this.cktough : require("tough-cookie"),
            this.ckjar = this.ckjar ? this.ckjar : new this.cktough.CookieJar,
            t && (t.headers = t.headers ? t.headers : {}, void 0 === t.headers.Cookie && void 0 === t.cookieJar && (t.cookieJar = this.ckjar))
        }
        get(t, e = (() => {})) {
            t.headers && (delete t.headers["Content-Type"], delete t.headers["Content-Length"]),
            this.isSurge() || this.isLoon() ? (this.isSurge() && this.isNeedRewrite && (t.headers = t.headers || {}, Object.assign(t.headers, {
                        "X-Surge-Skip-Scripting": !1
                    })), $httpClient.get(t, (t, s, i) => {
                    !t && s && (s.body = i, s.statusCode = s.status),
                    e(t, s, i)
                })) : this.isQuanX() ? (this.isNeedRewrite && (t.opts = t.opts || {}, Object.assign(t.opts, {
                        hints: !1
                    })), $task.fetch(t).then(t => {
                    const {
                        statusCode: s,
                        statusCode: i,
                        headers: r,
                        body: o
                    } = t;
                    e(null, {
                        status: s,
                        statusCode: i,
                        headers: r,
                        body: o
                    }, o)
                }, t => e(t))) : this.isNode() && (this.initGotEnv(t), this.got(t).on("redirect", (t, e) => {
                    try {
                        if (t.headers["set-cookie"]) {
                            const s = t.headers["set-cookie"].map(this.cktough.Cookie.parse).toString();
                            s && this.ckjar.setCookieSync(s, null),
                            e.cookieJar = this.ckjar
                        }
                    } catch (t) {
                        this.logErr(t)
                    }
                }).then(t => {
                    const {
                        statusCode: s,
                        statusCode: i,
                        headers: r,
                        body: o
                    } = t;
                    e(null, {
                        status: s,
                        statusCode: i,
                        headers: r,
                        body: o
                    }, o)
                }, t => {
                    const {
                        message: s,
                        response: i
                    } = t;
                    e(s, i, i && i.body)
                }))
        }
        post(t, e = (() => {})) {
            if (t.body && t.headers && !t.headers["Content-Type"] && (t.headers["Content-Type"] = "application/x-www-form-urlencoded"), t.headers && delete t.headers["Content-Length"], this.isSurge() || this.isLoon())
                this.isSurge() && this.isNeedRewrite && (t.headers = t.headers || {}, Object.assign(t.headers, {
                        "X-Surge-Skip-Scripting": !1
                    })), $httpClient.post(t, (t, s, i) => {
                    !t && s && (s.body = i, s.statusCode = s.status),
                    e(t, s, i)
                });
            else if (this.isQuanX())
                t.method = "POST", this.isNeedRewrite && (t.opts = t.opts || {}, Object.assign(t.opts, {
                        hints: !1
                    })), $task.fetch(t).then(t => {
                    const {
                        statusCode: s,
                        statusCode: i,
                        headers: r,
                        body: o
                    } = t;
                    e(null, {
                        status: s,
                        statusCode: i,
                        headers: r,
                        body: o
                    }, o)
                }, t => e(t));
            else if (this.isNode()) {
                this.initGotEnv(t);
                const {
                    url: s,
                    ...i
                } = t;
                this.got.post(s, i).then(t => {
                    const {
                        statusCode: s,
                        statusCode: i,
                        headers: r,
                        body: o
                    } = t;
                    e(null, {
                        status: s,
                        statusCode: i,
                        headers: r,
                        body: o
                    }, o)
                }, t => {
                    const {
                        message: s,
                        response: i
                    } = t;
                    e(s, i, i && i.body)
                })
            }
        }
        time(t, e = null) {
            const s = e ? new Date(e) : new Date;
            let i = {
                "M+": s.getMonth() + 1,
                "d+": s.getDate(),
                "H+": s.getHours(),
                "m+": s.getMinutes(),
                "s+": s.getSeconds(),
                "q+": Math.floor((s.getMonth() + 3) / 3),
                S: s.getMilliseconds()
            };
            /(y+)/.test(t) && (t = t.replace(RegExp.$1, (s.getFullYear() + "").substr(4 - RegExp.$1.length)));
            for (let e in i)
                new RegExp("(" + e + ")").test(t) && (t = t.replace(RegExp.$1, 1 == RegExp.$1.length ? i[e] : ("00" + i[e]).substr(("" + i[e]).length)));
            return t
        }
        msg(e = t, s = "", i = "", r) {
            const o = t => {
                if (!t)
                    return t;
                if ("string" == typeof t)
                    return this.isLoon() ? t : this.isQuanX() ? {
                        "open-url": t
                    }
                 : this.isSurge() ? {
                    url: t
                }
                 : void 0;
                if ("object" == typeof t) {
                    if (this.isLoon()) {
                        let e = t.openUrl || t.url || t["open-url"],
                        s = t.mediaUrl || t["media-url"];
                        return {
                            openUrl: e,
                            mediaUrl: s
                        }
                    }
                    if (this.isQuanX()) {
                        let e = t["open-url"] || t.url || t.openUrl,
                        s = t["media-url"] || t.mediaUrl;
                        return {
                            "open-url": e,
                            "media-url": s
                        }
                    }
                    if (this.isSurge()) {
                        let e = t.url || t.openUrl || t["open-url"];
                        return {
                            url: e
                        }
                    }
                }
            };
            if (this.isMute || (this.isSurge() || this.isLoon() ? $notification.post(e, s, i, o(r)) : this.isQuanX() && $notify(e, s, i, o(r))), !this.isMuteLog) {
                let t = ["", "==============📣系统通知📣=============="];
                t.push(e),
                s && t.push(s),
                i && t.push(i),
                console.log(t.join("\n")),
                this.logs = this.logs.concat(t)
            }
        }
        log(...t) {
            t.length > 0 && (this.logs = [...this.logs, ...t]),
            console.log(t.join(this.logSeparator))
        }
        logErr(t, e) {
            const s = !this.isSurge() && !this.isQuanX() && !this.isLoon();
            s ? this.log("", `❗️${this.name}, 错误!`, t.stack) : this.log("", `❗️${this.name}, 错误!`, t)
        }
        wait(t) {
            return new Promise(e => setTimeout(e, t))
        }
        done(t = {}) {
            const e = (new Date).getTime(),
            s = (e - this.startTime) / 1e3;
            this.log("", `🔔${this.name}, 结束! 🕛 ${s} 秒`),
            this.log(),
            (this.isSurge() || this.isQuanX() || this.isLoon()) && $done(t)
        }
    }
    (t, e)
}
