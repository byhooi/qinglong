/**
 * akino 抓包数据导出（一次性工具，跑完可删）
 *
 * 作用
 *   把 Surge/Loon 里 akino 模块存下的 10 份签到请求数据读出来，
 *   转成青龙「批量导入环境变量」的格式：CHECKIN_XXX=[{...}]
 *
 * 用法（Surge）
 *   1. 把本文件传到手机可访问的位置，或直接在编辑器里新建脚本粘贴内容
 *   2. 临时加一条 cron 执行一次，或在 Surge 的脚本编辑器里点运行
 *   3. 跑完看「脚本日志」，整段复制到青龙后台 → 环境变量 → 批量导入
 *   4. 通知里也会带一份，点通知即复制到剪贴板
 *
 * 用法（Loon）
 *   同上，脚本日志在「配置 → 脚本 → 日志」
 *
 * 注意
 *   导出的内容含 cookie/token，属于敏感信息。
 *   不要提交到 git，不要发到任何群里。
 */

const STORE_KEY = "akino";
const ENV_PREFIX = "CHECKIN_";

// 与 s/ 目录下 10 个模块的 ckName 一一对应
const CK_NAMES = [
    "mylink",   // mylink
    "sdl",      // 三得利
    "honda",    // 东风本田
    "ninebot",  // 九号电动
    "zyh",      // 卓悦汇
    "miniso",   // 名创优品
    "jtc",      // 捷停车
    "Syed",     // 深业
    "blug",     // 百晟广场
    "mixpark",  // 钧濠
];

function readStore() {
    try {
        const raw = $persistentStore.read(STORE_KEY);
        if (!raw) return {};
        return JSON.parse(raw) || {};
    } catch (e) {
        return {};
    }
}

function finish(lines, summary) {
    const text = lines.join("\n");

    console.log("");
    console.log("========== 青龙环境变量（批量导入以下内容） ==========");
    if (text) {
        console.log(text);
    } else {
        console.log("（没有可导出的数据）");
    }
    console.log("========== 导出结束 ==========");
    console.log("");
    console.log(summary.join("\n"));

    // 通知带剪贴板动作，点一下即可复制全部内容
    const body = summary.join("\n");
    try {
        $notification.post("akino 导出", body, "", {
            action: "clipboard",
            text: text,
        });
    } catch (e) {
        try {
            $notification.post("akino 导出", body, "", { updatePasteboard: text });
        } catch (e2) {
            $notification.post("akino 导出", body, "剪贴板不可用，请从脚本日志复制");
        }
    }

    $done({});
}

!(async () => {
    const store = readStore();
    const records = store.record || {};

    const lines = [];
    const summary = [];
    let found = 0;

    for (const ck of CK_NAMES) {
        const data = records[ck];

        if (!data || (Array.isArray(data) && data.length === 0)) {
            summary.push(`[缺失] ${ck}`);
            continue;
        }

        const list = Array.isArray(data) ? data : [data];
        const json = JSON.stringify(list);

        if (!json || json === "[]") {
            summary.push(`[缺失] ${ck}`);
            continue;
        }

        lines.push(`${ENV_PREFIX}${ck.toUpperCase()}=${json}`);
        summary.push(`[已导出] ${ck} - ${list.length} 个账号`);
        found++;
    }

    summary.push("");
    summary.push(`共 ${found} / ${CK_NAMES.length} 个站点有数据`);

    finish(lines, summary);
})();
