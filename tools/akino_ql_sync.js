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

// ---------- 主流程 ----------

async function main() {
  const summary = [];
  const started = Date.now();

  log(`脚本版本: ${SCRIPT_VERSION}`);

  try {
    const { records, error } = readAkinoRecords();
    if (error) {
      summary.push(`失败: ${error}`);
      return;
    }

    const available = CK_NAMES.filter((ck) => {
      const data = decodeRecord(records[ck]);
      return data.length > 0;
    });

    if (available.length === 0) {
      summary.push('失败: 存储里没有任何签到数据');
      return;
    }

    log(`发现 ${available.length} / ${CK_NAMES.length} 个站点有数据`);

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

main().catch((err) => {
  console.log(redact(`脚本执行出错: ${err?.message || err}`));
  $done({});
});
