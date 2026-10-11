#!/usr/bin/env node
/**
 * dylan 系列京东脚本 —— 字符串解码 / 反混淆工具
 *
 * 背景
 *   dylan 系列脚本（jd_OnceApply.js、jd_AutoEval.js 等）把全部字符串塞进一个
 *   数组，运行时再用「LZString 解压 + 自定义字符表 base64 变体 + 变长编码」
 *   的解码函数还原，因此源码里看不到任何明文，排查问题时很难读。
 *   本工具在 Node vm 沙箱里跑出这些解码函数，把明文批量还原出来。
 *
 * 用法
 *   node tools/decode-dylan.js <脚本路径>                  # 列出全部明文（去重排序）
 *   node tools/decode-dylan.js <脚本路径> --map            # 带来源的完整映射
 *   node tools/decode-dylan.js <脚本路径> --grep cookie    # 只显示含关键字的条目
 *
 *   示例：
 *     node tools/decode-dylan.js ../jdpro/jd_OnceApply.js
 *     node tools/decode-dylan.js ../jdpro/jd_AutoEval.js --grep http
 *
 * 原理
 *   1. 前缀切分
 *      混淆脚本的结构固定为：
 *        <字符串表 + LZString + 若干解码函数>;const A=$[…].isNode()?require("./x"):"";…
 *      取第一个 require( 之前、最近一个 ; 之后的代码作为「前缀」。
 *   2. 沙箱执行 + 自动补桩
 *      前缀会引用少量定义在文件后段的符号（SeE5BEt、PYxAzG 之类的空操作包装，
 *      以及脚本自带的 Env 类）。捕获 ReferenceError 逐个补空桩并重跑，
 *      直到前缀能执行通过——桩函数名因脚本而异，所以自动发现而不是硬编码。
 *   3. 导出顶层绑定
 *      字符串表和解码函数多为顶层 const，不会挂到 globalThis，从沙箱对象上
 *      取不到。因此把候选标识符拼成导出语句，与前缀放进同一个 Script 执行。
 *   4. 交叉解码
 *      一个脚本里往往有不止一层解码器（每层字符表不同）。用每个候选解码函数
 *      去解每张候选表的每个元素，收集全部可打印结果——比猜「哪个函数配哪张表」稳。
 *
 * 注意
 *   - 解出的是「脚本中出现的字符串」，不是反编译后的可读源码；控制流仍是混淆的。
 *   - 部分字符串要等运行时才解密（依赖环境变量、接口返回值等），工具解不出，
 *     会以乱码形式被过滤掉，属正常现象。
 */

'use strict';

const fs = require('fs');
const vm = require('vm');

/** 自动补桩的最大重试次数，防止前缀里有别的错误时死循环 */
const MAX_STUB_RETRY = 200;

/* ------------------------------ 1. 前缀切分 ------------------------------ */

/**
 * 切出「字符串表 + 解码函数」这段前缀。
 *
 * 不能用「第一个 require( 之前的最后一个分号」定位：有的脚本（jd_AutoEval.js）
 * 在混淆区中间就出现了 require(，那样会切得过短。
 *
 * 混淆器的结构固定：初始化段以 `const X=$[<解码调用>]()?...` 开头（$ 是 Env 实例，
 * 第一个 $[...] 调用即业务代码起点）。以此为界切分最稳。
 * 找不到该特征时，回退到「第一个 require( 之前」。
 */
function extractPrefix(src) {
  const marker = /const\s+[A-Za-z_$][\w$]*\s*=\s*\$\s*\[/.exec(src);
  if (marker) return src.slice(0, marker.index);

  const at = src.indexOf('require(');
  if (at < 0) throw new Error('源码中找不到 require(，可能不是 dylan 混淆脚本');
  return src.slice(0, at);
}

/**
 * 收集候选标识符。
 *
 * 顶层绑定并不都写在前缀里：jd_AutoEval.js 的解码函数是 `function` 声明，
 * 散布在文件后段。因此扫描范围是「前缀 + 全文件的函数声明」。
 * 混进局部名没关系，导出阶段有 try/catch 兜底。
 */
function candidateNames(src) {
  const names = new Set();
  const patterns = [
    /(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*=/g,
    /function\s+([A-Za-z_$][\w$]*)\s*\(/g,
  ];
  for (const re of patterns) {
    let m;
    while ((m = re.exec(src)) !== null) names.add(m[1]);
  }
  return [...names];
}

/* ---------------------------- 2. 候选标识符 ------------------------------ */

/* ------------------------------- 3. 沙箱 --------------------------------- */

function makeSandbox(stubs) {
  const sandbox = {
    console,
    require,
    process,
    Buffer,
    setTimeout,
    clearTimeout,
    setInterval,
    clearInterval,
    module: { exports: {} },
    exports: {},
  };
  sandbox.global = sandbox;
  sandbox.globalThis = sandbox;

  // Env 是脚本自带的日志类构造器，给个最小可用实现即可
  sandbox.Env = function () {
    return {
      getEnv: () => 'Node.js',
      isNode: () => true,
      getval: () => '',
      getdata: () => '',
      setdata: () => true,
      log() {},
      info() {},
      warn() {},
      error() {},
      debug() {},
      done() {},
      wait: () => Promise.resolve(),
      get() {},
      post() {},
      send: () => Promise.resolve(''),
    };
  };

  for (const name of stubs) sandbox[name] = function () {};
  return sandbox;
}

/* --------------------- 4. 执行前缀并导出顶层绑定 -------------------------- */

function loadBindings(prefix, filename, allNames) {
  const names = allNames;
  const exportCode = [
    '',
    ';globalThis.__BINDINGS__ = [];',
    '(function () {',
    '  var __v;',
    ...names.map(
      (n) => `  try { __v = ${n}; if (__v !== undefined) __BINDINGS__.push(['${n}', __v]); } catch (e) {}`
    ),
    '})();',
    '',
  ].join('\n');

  const stubs = new Set();
  for (let attempt = 0; attempt < MAX_STUB_RETRY; attempt++) {
    const sandbox = makeSandbox(stubs);
    vm.createContext(sandbox);
    try {
      vm.runInContext(prefix + exportCode, sandbox, { filename });
      return sandbox.__BINDINGS__;
    } catch (e) {
      const m = /([A-Za-z_$][\w$]*) is not defined/.exec(e.message);
      if (m && m[1] !== 'Env' && !stubs.has(m[1])) {
        stubs.add(m[1]);
        continue;
      }
      throw new Error(`前缀执行失败：${e.message}`);
    }
  }
  throw new Error(`补桩超过 ${MAX_STUB_RETRY} 次，放弃`);
}

/* ----------------------------- 5. 交叉解码 ------------------------------- */

/** 过滤掉解码失败产生的乱码（控制字符 / Unicode 替换字符） */
function isPrintable(s) {
  if (/[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]/.test(s)) return false;
  if (s.includes('�')) return false;
  return true;
}

function decodeAll(bindings) {
  const decoders = bindings.filter(
    ([, v]) => typeof v === 'function' && /indexOf/.test(v.toString())
  );
  const tables = bindings.filter(([, v]) => Array.isArray(v) && v.length >= 8);

  const rows = [];
  const seen = new Set();

  for (const [tName, table] of tables) {
    for (const [dName, decode] of decoders) {
      for (let i = 0; i < table.length; i++) {
        const raw = table[i];
        if (typeof raw !== 'string' || raw.length < 2) continue;

        let text;
        try {
          text = decode(raw);
        } catch {
          continue;
        }
        if (typeof text !== 'string' || text.length < 2) continue;
        if (!isPrintable(text)) continue;

        const key = `${dName}\u0000${tName}\u0000${i}`;
        if (seen.has(key)) continue;
        seen.add(key);
        rows.push({ decoder: dName, table: tName, index: i, text });
      }
    }
  }
  return rows;
}

/* -------------------------------- 入口 ---------------------------------- */

function main() {
  const argv = process.argv.slice(2);
  const target = argv.find((a) => !a.startsWith('--'));
  if (!target) {
    console.error('用法：node tools/decode-dylan.js <脚本路径> [--map] [--grep <关键字>]');
    process.exit(1);
  }

  const asMap = argv.includes('--map');
  const grepAt = argv.indexOf('--grep');
  const grep = grepAt >= 0 ? argv[grepAt + 1] : null;

  const src = fs.readFileSync(target, 'utf8');
  const prefix = extractPrefix(src);
  // 候选标识符取自全文件（解码函数可能散落在前缀之后）
  const bindings = loadBindings(prefix, target, candidateNames(src));

  const rows = decodeAll(bindings);
  const filtered = grep ? rows.filter((r) => r.text.includes(grep)) : rows;

  if (asMap) {
    for (const r of filtered) {
      console.log(`${r.table}[${r.index}]\t${r.decoder}\t${r.text}`);
    }
  } else {
    for (const s of [...new Set(filtered.map((r) => r.text))].sort()) console.log(s);
  }

  // 统计走 stderr，stdout 保持为纯结果，方便重定向
  console.error(
    `# 顶层绑定 ${bindings.length} 个 | 解码器 ${new Set(rows.map((r) => r.decoder)).size} 个 | ` +
      `字符串表 ${new Set(rows.map((r) => r.table)).size} 张 | 明文 ${new Set(rows.map((r) => r.text)).size} 条`
  );
}

main();
