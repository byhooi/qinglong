/**
 * akino 抓包数据 → 青龙环境变量 自动同步
 *
 * 作用
 *   把 Surge/Loon 里 akino 模块存下的签到请求数据，直接写进青龙面板的环境变量，
 *   全程不用复制粘贴。配置复用 jdcookie_ql_sync.js 已有的那几个 key，无需重配。
 *
 * 前置配置（若之前配过京东 Cookie 同步，这里已经齐了）
 *   ql_url          青龙地址，如 https://ql.example.com
 *   ql_client_id    青龙后台 → 应用设置 → 新建应用
 *   ql_client_secret 同上
 *
 * 用法
 *   Surge 加一条 cron，每天跑一次即可：
 *     akino同步 = type=cron,cronexp="0 9 * * *",script-path=<本文件 raw 地址>,timeout=120,wake-system=1
 *   也可以手动跑一次看结果。
 *
 * 数据格式注意
 *   akino 通过 Env.setjson 写入，而 setdata 又序列化了一次，
 *   所以持久化存储里是「JSON 字符串的字符串」，必须解两次才能拿到数组。
 *   本脚本的 decodeRecord 已处理，兼容只存一层的情况。
 */

const SCRIPT_NAME = 'akino → 青龙同步';
const SCRIPT_VERSION = '1.0.0';

const STORE_KEY = 'akino';
const ENV_PREFIX = 'CHECKIN_';

// 自动同步开关，与 jdcookie 的 auto_sync_jdcookie_ql 同一套路：
// 未设置时默认开启，BoxJS 里关掉才停止抓包即时同步
const AUTO_SYNC_KEY = 'auto_sync_akino_ql';

// 与桌面 s/ 目录下 10 个模块的 ckName 一一对应
const CK_NAMES = [
  'mylink',   // mylink
  'sdl',      // 三得利
  'honda',    // 东风本田
  'ninebot',  // 九号电动
  'zyh',      // 卓悦汇
  'miniso',   // 名创优品
  'jtc',      // 捷停车
  'Syed',     // 深业
  'blug',     // 百晟广场
  'mixpark',  // 钧濠
];

// 非 akino 架构的脚本，数据存在各自的 key 里，读不到 akino 存储，
// 需要单独从对应 key 导入。新增这类站点时在这里加一条。
const IMPORT_SOURCES = [
  // raw: true 表示存储的是纯文本凭证（如 userToken），原样写入青龙，
  // 由青龙端的 builder 用 token 现构造请求；否则按 JSON 解析成请求数组。
  { key: 'byhooi_1hai_sign_request', env: 'CHECKIN_1HAI', note: '一嗨租车' },
  { key: 'byhooi_huazhu_token', env: 'CHECKIN_HUAZHU', note: '华住会', raw: true },
];

const QL_API = {
  LOGIN: '/open/auth/token',
  ENVS: '/open/envs',
};

const TOKEN_CACHE_KEY = 'ql_token';
const TOKEN_EXPIRES_KEY = 'ql_token_expires';

// ---------- 日志脱敏 ----------

function redact(text) {
  let out = String(text);
  for (const key of ['ql_client_secret', 'ql_token']) {
    const secret = $persistentStore.read(key);
    if (typeof secret === 'string' && secret) out = out.split(secret).join('[REDACTED]');
  }
  return out
    .replace(/((?:client_secret|token)=)[^;&\s"\\]+/gi, '$1[REDACTED]')
    .replace(/(Bearer\s+)[^\s"\\]+/gi, '$1[REDACTED]')
    .replace(/("(?:cookie|set-cookie|authorization|token|client_secret)"\s*:\s*")([^"\\]|\\.)*"/gi, '$1[REDACTED]"');
}

function log(...messages) {
  console.log(redact(messages.join(' ')));
}

// ---------- 青龙面板 ----------

class QLPanel {
  constructor() {
    this.baseUrl = ($persistentStore.read('ql_url') || '').trim().replace(/\/$/, '');
    this.clientId = ($persistentStore.read('ql_client_id') || '').trim();
    this.clientSecret = ($persistentStore.read('ql_client_secret') || '').trim();
    this.token = $persistentStore.read(TOKEN_CACHE_KEY) || '';
    this.tokenExpires = parseInt($persistentStore.read(TOKEN_EXPIRES_KEY) || '0', 10);
  }

  checkConfig() {
    if (!this.baseUrl || !this.clientId || !this.clientSecret) {
      throw new Error('青龙配置不完整，需要 ql_url / ql_client_id / ql_client_secret');
    }
  }

  request(options, method = 'GET') {
    return new Promise((resolve, reject) => {
      options.method = method;
      const callback = (error, response, data) => {
        if (error) return reject(error);
        try {
          resolve(typeof data === 'string' ? JSON.parse(data) : data);
        } catch (e) {
          resolve(data);
        }
      };
      const client = $httpClient;
      const fn = client[method.toLowerCase()];
      if (typeof fn !== 'function') return reject(new Error(`不支持的请求方法: ${method}`));
      fn.call(client, options, callback);
    });
  }

  async getToken() {
    log('正在获取青龙 Token...');
    const options = {
      url: `${this.baseUrl}${QL_API.LOGIN}?client_id=${encodeURIComponent(this.clientId)}&client_secret=${encodeURIComponent(this.clientSecret)}`,
      headers: { 'Content-Type': 'application/json', 'User-Agent': 'Mozilla/5.0' },
    };
    const response = await this.request(options, 'GET');
    if (response?.code !== 200 || !response?.data?.token) {
      throw new Error(response?.message || '获取 Token 失败');
    }
    this.token = response.data.token;
    // 青龙 Token 有效期 7 天，这里按 6.5 天缓存
    this.tokenExpires = Date.now() + 6.5 * 24 * 60 * 60 * 1000;
    $persistentStore.write(this.token, TOKEN_CACHE_KEY);
    $persistentStore.write(String(this.tokenExpires), TOKEN_EXPIRES_KEY);
    log('Token 获取成功');
    return true;
  }

  async ensureToken() {
    if (!this.token || this.tokenExpires <= Date.now()) {
      await this.getToken();
    }
  }

  authHeaders() {
    return {
      Authorization: `Bearer ${this.token}`,
      'Content-Type': 'application/json',
      'User-Agent': 'Mozilla/5.0',
    };
  }

  async getEnvs(name) {
    await this.ensureToken();
    const options = {
      url: `${this.baseUrl}${QL_API.ENVS}?searchValue=${encodeURIComponent(name)}`,
      headers: this.authHeaders(),
    };
    const response = await this.request(options, 'GET');
    if (response?.code !== 200) throw new Error(response?.message || '查询环境变量失败');
    // searchValue 是模糊匹配，这里再精确过滤一次
    return (response.data || []).filter((item) => item && item.name === name);
  }

  async addEnv(name, value, remarks) {
    await this.ensureToken();
    const options = {
      url: `${this.baseUrl}${QL_API.ENVS}`,
      headers: this.authHeaders(),
      body: JSON.stringify([{ name, value, remarks }]),
    };
    const response = await this.request(options, 'POST');
    if (response?.code !== 200) throw new Error(response?.message || '新增环境变量失败');
    return true;
  }

  async updateEnv(envItem, name, value, remarks) {
    await this.ensureToken();
    const id = envItem.id || envItem._id;
    const options = {
      url: `${this.baseUrl}${QL_API.ENVS}`,
      headers: this.authHeaders(),
      body: JSON.stringify({ id, name, value, remarks }),
    };
    const response = await this.request(options, 'PUT');
    if (response?.code !== 200) throw new Error(response?.message || '更新环境变量失败');
    // 变量若被禁用，更新后顺手启用
    if (envItem.status === 1) {
      await this.enableEnv([id]);
    }
    return true;
  }

  async enableEnv(ids) {
    const options = {
      url: `${this.baseUrl}${QL_API.ENVS}/enable`,
      headers: this.authHeaders(),
      body: JSON.stringify(ids),
    };
    try {
      await this.request(options, 'PUT');
    } catch (e) {
      log(`启用变量失败（不影响数据）: ${e.message || e}`);
    }
  }
}

// ---------- akino 数据读取 ----------

/**
 * akino 的存储是「字符串套字符串」：
 *   setjson → JSON.stringify(userCookie)
 *   setdata → lodash_set(obj, 'record.<ck>', 上面的字符串) → JSON.stringify(obj)
 * 所以 record[ck] 是一个 JSON 字符串，需要再解一次。
 */
function decodeRecord(value) {
  let data = value;
  for (let i = 0; i < 2 && typeof data === 'string'; i++) {
    try {
      data = JSON.parse(data);
    } catch (e) {
      break;
    }
  }
  if (data === null || data === undefined || data === '') return [];
  return Array.isArray(data) ? data : [data];
}

function readAkinoRecords() {
  const raw = $persistentStore.read(STORE_KEY);
  if (!raw) return { records: {}, error: `持久化存储里没有 ${STORE_KEY}，akino 模块可能还没抓到数据` };

  let store;
  try {
    store = JSON.parse(raw);
  } catch (e) {
    return { records: {}, error: `${STORE_KEY} 不是合法 JSON，无法解析` };
  }

  // 正常结构是 { record: { <ckName>: ... } }
  if (store && typeof store === 'object' && store.record && typeof store.record === 'object') {
    return { records: store.record, error: '' };
  }
  return { records: {}, error: `存储结构异常，没有找到 record 字段（顶层键: ${Object.keys(store || {}).join(', ')}）` };
}

// ---------- 抓包即时同步 ----------

function parseArguments() {
  const args = {};
  if (typeof $argument === 'string' && $argument) {
    $argument.split('&').forEach((pair) => {
      const idx = pair.indexOf('=');
      if (idx > 0) {
        args[pair.slice(0, idx).trim()] = pair.slice(idx + 1).trim();
      }
    });
  }
  return args;
}

function autoSyncEnabled() {
  const value = $persistentStore.read(AUTO_SYNC_KEY);
  // 与 jdcookie 一致：未设置视为开启，BoxJS 里关掉才停
  return value === null || value === undefined || value === '' || value === 'true' || value === true;
}

/**
 * 抓包模式：作为 akino.js 的并行脚本挂在同一个 pattern 上，抓到请求就直接推青龙。
 * 直接用 $request 构造数据，不读 akino 的持久化存储，因此不依赖两个脚本的执行顺序。
 */
async function handleCapture() {
  const args = parseArguments();
  const ckName = (args.ckName || '').trim();

  if (!ckName) {
    log('抓包模式缺少 ckName 参数，跳过');
    return;
  }
  if (!autoSyncEnabled()) {
    log(`${ckName}: 自动同步已关闭，跳过`);
    return;
  }

  // 有些接口是适配层入口，多种业务共用一个 URL，靠 body 里的 action 区分。
  // 这种在原 akino 模块里用 bodyRegx 过滤，同步侧必须做同样的判断，
  // 否则查询类请求也会把数据写进去。
  const bodyRegx = (args.bodyRegx || '').trim();
  if (bodyRegx && $request.body) {
    let matched = true;
    try {
      matched = new RegExp(bodyRegx).test(String($request.body));
    } catch (e) {
      log(`${ckName}: bodyRegx 无效，跳过（${e.message || e}）`);
      return;
    }
    if (!matched) {
      log(`${ckName}: body 不匹配 bodyRegx，跳过`);
      return;
    }
  }

  // 有些站点的青龙端只需要一个 token（如华住会的 userToken），不需要完整请求。
  // tokenPath 指定从请求的哪里取，格式 cookie:userToken / header:X-Token / query:token
  const tokenPath = (args.tokenPath || '').trim();
  const envName = `${ENV_PREFIX}${ckName.toUpperCase()}`;
  const accountIndex = parseInt(args.accountIndex || '0', 10) || 0;

  if (tokenPath) {
    const sep = tokenPath.indexOf(':');
    const source = sep > 0 ? tokenPath.slice(0, sep).toLowerCase() : 'cookie';
    const key = sep > 0 ? tokenPath.slice(sep + 1) : tokenPath;
    const headers = $request.headers || {};
    let token = '';

    if (source === 'cookie') {
      const cookieText = headers.Cookie || headers.cookie || '';
      const matched = cookieText.match(new RegExp('(?:^|;\\s*)' + key + '=([^;]+)'));
      token = matched ? matched[1] : '';
    } else if (source === 'header') {
      token = headers[key] || headers[key.toLowerCase()] || '';
    } else if (source === 'query') {
      const matched = $request.url.match(new RegExp('[?&]' + key + '=([^&]+)'));
      token = matched ? decodeURIComponent(matched[1]) : '';
    }

    if (!token) {
      log(`${ckName}: 未从请求中取到 ${tokenPath}，跳过`);
      return;
    }

    // 华住会这类站点每次请求都带 token，全部同步会频繁调青龙 API。
    // 本地记一份上次的值，相同就直接跳过，不碰网络。
    const cacheKey = `akino_last_token_${ckName}`;
    if ($persistentStore.read(cacheKey) === token) {
      return;
    }

    const client = new QLPanel();
    client.checkConfig();
    const current = await client.getEnvs(envName);
    const remarks = `${ckName} - Surge 抓包同步`;

    if (current.length === 0) {
      await client.addEnv(envName, token, remarks);
      log(`${ckName}: 新增 ${envName}（token）`);
    } else if (current[0].value === token) {
      log(`${ckName}: token 未变化，跳过`);
    } else {
      await client.updateEnv(current[0], envName, token, remarks);
      log(`${ckName}: 已更新 ${envName}（token）`);
    }

    $persistentStore.write(token, cacheKey);
    return;
  }

  const item = {
    url: $request.url,
    method: ($request.method || 'GET').toLowerCase(),
    headers: $request.headers || {},
    body: $request.body || '',
  };

  const ql = new QLPanel();
  ql.checkConfig();

  const existing = await ql.getEnvs(envName);

  let accounts = [];
  if (existing.length > 0) {
    try {
      accounts = JSON.parse(existing[0].value);
    } catch (e) {
      accounts = [];
    }
    if (!Array.isArray(accounts)) accounts = [];
  }

  // 多账号按 accountIndex 就地替换，避免每次抓包把其他账号冲掉
  while (accounts.length <= accountIndex) accounts.push(null);
  accounts[accountIndex] = item;
  accounts = accounts.filter(Boolean);

  const value = JSON.stringify(accounts);
  const remarks = `${accounts.length} 个账号 - Surge 抓包同步`;

  if (existing.length === 0) {
    await ql.addEnv(envName, value, remarks);
    log(`${ckName}: 新增 ${envName}（${accounts.length} 个账号）`);
  } else if (existing[0].value === value) {
    log(`${ckName}: 值未变化，跳过`);
  } else {
    await ql.updateEnv(existing[0], envName, value, remarks);
    log(`${ckName}: 已更新 ${envName}（${accounts.length} 个账号）`);
  }
}

// ---------- 主流程 ----------

async function main() {
  const summary = [];
  const started = Date.now();

  log(`脚本版本: ${SCRIPT_VERSION}`);

  try {
    const { records, error } = readAkinoRecords();
    if (error) {
      // akino 存储为空不应中断，其他存储源（IMPORT_SOURCES）可能仍有数据
      log(`${error}，继续检查其他存储源`);
    }

    const available = CK_NAMES.filter((ck) => {
      const data = decodeRecord(records[ck]);
      return data.length > 0;
    });

    const importable = IMPORT_SOURCES.filter((src) => !!$persistentStore.read(src.key));

    if (available.length === 0 && importable.length === 0) {
      summary.push('失败: 存储里没有任何签到数据');
      return;
    }

    log(`akino 站点 ${available.length} / ${CK_NAMES.length} 有数据，其他存储源 ${importable.length} 个`);

    const ql = new QLPanel();
    ql.checkConfig();

    let added = 0;
    let updated = 0;
    let skipped = 0;
    const failed = [];

    for (const ck of CK_NAMES) {
      const envName = `${ENV_PREFIX}${ck.toUpperCase()}`;
      const accounts = decodeRecord(records[ck]);

      if (accounts.length === 0) {
        log(`跳过 ${envName}: 无数据`);
        continue;
      }

      // 环境变量值就是 akino 原始数组的 JSON，与 replay.py 期望的格式一致
      const value = JSON.stringify(accounts);
      const remarks = `${accounts.length} 个账号 - 由 Surge 同步`;

      try {
        const existing = await ql.getEnvs(envName);

        if (existing.length === 0) {
          await ql.addEnv(envName, value, remarks);
          log(`新增 ${envName}（${accounts.length} 个账号）`);
          added++;
        } else {
          const target = existing[0];
          if (target.value === value) {
            if (target.status === 1) await ql.enableEnv([target.id || target._id]);
            log(`跳过 ${envName}: 值未变化`);
            skipped++;
          } else {
            await ql.updateEnv(target, envName, value, remarks);
            log(`更新 ${envName}（${accounts.length} 个账号）`);
            updated++;
          }
        }
      } catch (e) {
        const reason = e?.message || String(e);
        log(`失败 ${envName}: ${reason}`);
        failed.push(`${envName}: ${reason}`);
      }

      // 避免请求过快被青龙限流
      await new Promise((resolve) => setTimeout(resolve, 400));
    }

    // 非 akino 架构的脚本：直接从各自的存储 key 导入，把 Surge 里现有的 token 搬过去
    for (const src of IMPORT_SOURCES) {
      const raw = $persistentStore.read(src.key);
      if (!raw) {
        log(`${src.note}: Surge 里没有数据，跳过`);
        continue;
      }

      let value;
      let detail = '';

      if (src.raw) {
        // 纯文本凭证，原样写入
        value = String(raw).trim();
        if (!value) {
          log(`${src.note}: 数据为空，跳过`);
          continue;
        }
        detail = 'token';
      } else {
        let parsed;
        try {
          parsed = JSON.parse(raw);
        } catch (e) {
          log(`${src.note}: 存储不是合法 JSON，跳过`);
          continue;
        }

        const list = (Array.isArray(parsed) ? parsed : [parsed])
          .filter((item) => item && item.url)
          .map((item) => ({
            url: item.url,
            method: (item.method || 'POST').toLowerCase(),
            headers: item.headers || {},
            body: typeof item.body === 'string' ? item.body : '',
          }));

        if (list.length === 0) {
          log(`${src.note}: 没有可用数据，跳过`);
          continue;
        }
        value = JSON.stringify(list);
        detail = `${list.length} 条`;
      }

      const remarks = `${src.note} - Surge 存储导入`;

      try {
        const existing = await ql.getEnvs(src.env);
        if (existing.length === 0) {
          await ql.addEnv(src.env, value, remarks);
          log(`导入 ${src.env}（${detail}）`);
          added++;
        } else if (existing[0].value === value) {
          log(`跳过 ${src.env}: 值未变化`);
          skipped++;
        } else {
          await ql.updateEnv(existing[0], src.env, value, remarks);
          log(`更新 ${src.env}（${detail}）`);
          updated++;
        }
      } catch (e) {
        const reason = e?.message || String(e);
        log(`失败 ${src.env}: ${reason}`);
        failed.push(`${src.env}: ${reason}`);
      }

      await new Promise((resolve) => setTimeout(resolve, 400));
    }

    const seconds = ((Date.now() - started) / 1000).toFixed(1);
    summary.push(`新增 ${added} | 更新 ${updated} | 跳过 ${skipped}`);
    if (failed.length > 0) summary.push(`失败 ${failed.length}: ${failed.join('; ')}`);
    summary.push(`耗时 ${seconds} 秒`);
  } catch (e) {
    log(`执行异常: ${e?.stack || e?.message || e}`);
    summary.push(`失败: ${e?.message || e}`);
  } finally {
    const content = summary.join('\n');
    log(content);
    $notification.post(SCRIPT_NAME, '', redact(content));
    $done({});
  }
}

// 抓包请求走即时同步，cron / BoxJS 手动按钮走全量同步
if (typeof $request !== 'undefined') {
  handleCapture()
    .catch((err) => {
      console.log(redact(`抓包同步出错: ${err?.message || err}`));
    })
    .finally(() => {
      $done({});
    });
} else {
  main().catch((err) => {
    console.log(redact(`脚本执行出错: ${err?.message || err}`));
    $done({});
  });
}
