/*
 * 青龙面板 API 封装 (jd_CheckCK.js 依赖)
 *
 * 提供: getEnvs / getEnvById / getstatus / DisableCk / EnableCk
 * 只使用 Node 原生模块 (http/fs/crypto), 不依赖 got/axios, 避免青龙内置依赖版本差异
 *
 * token 获取策略与 wskey.py 保持一致:
 *   1. 从 /ql/data/db/keyv.sqlite (取最后一个 token) 和 auth.json 收集候选 token
 *   2. 用 GET /api/user 逐个验证, 全部失效则用 auth.json 中的用户名密码重新登录 (支持两步验证 TOTP)
 *
 * 环境变量: QL_PORT (青龙端口, 默认 5700)
 */
'use strict';

const fs = require('fs');
const http = require('http');
const crypto = require('crypto');

const QL_HOST = '127.0.0.1';
const QL_PORT = /^\d+$/.test(String(process.env.QL_PORT || '')) ? Number(process.env.QL_PORT) : 5700;
const KEYV_FILE = '/ql/data/db/keyv.sqlite';
const AUTH_FILES = ['/ql/data/config/auth.json', '/ql/config/auth.json'];
const TIMEOUT = 10000;

let cachedToken = '';

function request(method, path, { body, token } = {}) {
    return new Promise((resolve, reject) => {
        const headers = { Accept: 'application/json' };
        let payload = '';
        if (body !== undefined) {
            payload = typeof body === 'string' ? body : JSON.stringify(body);
            headers['Content-Type'] = 'application/json;charset=UTF-8';
            headers['Content-Length'] = Buffer.byteLength(payload);
        }
        if (token) {
            headers.Authorization = `Bearer ${token}`;
        }
        const req = http.request({ host: QL_HOST, port: QL_PORT, path, method, headers, timeout: TIMEOUT }, (res) => {
            const chunks = [];
            res.on('data', (chunk) => chunks.push(chunk));
            res.on('end', () => {
                const text = Buffer.concat(chunks).toString('utf8');
                let data = null;
                try {
                    data = text ? JSON.parse(text) : null;
                } catch (e) {
                    data = null;
                }
                resolve({ status: res.statusCode, data, text });
            });
        });
        req.on('timeout', () => req.destroy(new Error(`青龙接口超时: ${method} ${path}`)));
        req.on('error', (err) => reject(new Error(`青龙接口请求失败: ${method} ${path} ${err.message}`)));
        if (payload) {
            req.write(payload);
        }
        req.end();
    });
}

function readFileSafe(file, encoding) {
    try {
        return fs.readFileSync(file, encoding);
    } catch (e) {
        return '';
    }
}

// auth.json 提供用户名/密码/两步验证密钥 (新版青龙的 token 已迁移到 keyv 文件)
function readAuthConfig() {
    for (const file of AUTH_FILES) {
        const text = readFileSafe(file, 'utf8');
        if (!text) continue;
        try {
            return JSON.parse(text);
        } catch (e) {
            // 文件损坏, 尝试下一个
        }
    }
    return {};
}

// 收集所有可能有效的 token, 去重后逐个验证
function candidateTokens(auth) {
    const tokens = [];
    const keyv = readFileSafe(KEYV_FILE, 'latin1');
    const matches = keyv.match(/"token":"([^"]*)"/g) || [];
    if (matches.length) {
        tokens.push(matches[matches.length - 1].replace(/^"token":"|"$/g, ''));
    }
    if (auth.token) {
        tokens.push(auth.token);
    }
    return [...new Set(tokens.filter(Boolean))];
}

function base32Decode(input) {
    const alphabet = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ234567';
    let bits = '';
    for (const ch of String(input).toUpperCase().replace(/=+$/, '')) {
        const val = alphabet.indexOf(ch);
        if (val === -1) throw new Error('twoFactorSecret 不是合法的 base32');
        bits += val.toString(2).padStart(5, '0');
    }
    const bytes = [];
    for (let i = 0; i + 8 <= bits.length; i += 8) {
        bytes.push(parseInt(bits.slice(i, i + 8), 2));
    }
    return Buffer.from(bytes);
}

// 青龙两步验证使用标准 TOTP (30 秒步长, 6 位)
function totp(secret) {
    const counter = Buffer.alloc(8);
    counter.writeUInt32BE(0, 0);
    counter.writeUInt32BE(Math.floor(Date.now() / 1000 / 30), 4);
    const mac = crypto.createHmac('sha1', base32Decode(secret)).update(counter).digest();
    const offset = mac[mac.length - 1] & 0x0f;
    const binary = mac.readUInt32BE(offset) & 0x7fffffff;
    return String(binary % 1000000).padStart(6, '0');
}

async function verifyToken(token) {
    try {
        const res = await request('GET', '/api/user', { token });
        return res.status === 200;
    } catch (e) {
        return false;
    }
}

const hasToken = (res) => res.status === 200 && res.data && res.data.code === 200 && res.data.data && res.data.data.token;

async function loginByPassword(auth) {
    if (!auth.username || !auth.password) {
        throw new Error('青龙 token 已失效, 且 auth.json 中没有用户名密码, 无法自动登录, 请在面板重新登录');
    }
    const body = { username: auth.username, password: auth.password };
    let res = await request('POST', '/api/user/login', { body });
    if (hasToken(res)) {
        return res.data.data.token;
    }
    if (res.status === 200 && res.data && res.data.code === 420) {
        if (!auth.twoFactorSecret) {
            throw new Error('青龙开启了两步验证但 auth.json 中没有 twoFactorSecret, 无法自动登录');
        }
        res = await request('PUT', '/api/user/two-factor/login', { body: { ...body, code: totp(auth.twoFactorSecret) } });
        if (hasToken(res)) {
            return res.data.data.token;
        }
        throw new Error(`青龙两步验证登录失败: HTTP ${res.status} ${res.text.slice(0, 200)}`);
    }
    // 兼容旧版青龙登录接口
    res = await request('POST', '/api/login', { body });
    if (res.data && res.data.data && res.data.data.token) {
        return res.data.data.token;
    }
    throw new Error(`青龙登录失败: HTTP ${res.status} ${res.text.slice(0, 200)}`);
}

async function getToken() {
    if (cachedToken) return cachedToken;
    const auth = readAuthConfig();
    for (const token of candidateTokens(auth)) {
        if (await verifyToken(token)) {
            cachedToken = token;
            return token;
        }
    }
    console.log('青龙 token 失效, 使用 auth.json 中的账号重新登录');
    cachedToken = await loginByPassword(auth);
    return cachedToken;
}

async function api(method, path, body) {
    const token = await getToken();
    const res = await request(method, path, { body, token });
    if (!res.data || typeof res.data !== 'object') {
        throw new Error(`青龙接口 ${method} ${path} 返回异常: HTTP ${res.status} ${res.text.slice(0, 200)}`);
    }
    return res.data;
}

// 兼容新旧版本青龙的 id / _id 字段
const envId = (env) => (env._id !== undefined ? env._id : env.id);

// 获取全部 JD_COOKIE 变量 (含已禁用), 每项包含 id/_id、value、status (0 启用 / 1 禁用)、remarks
async function getEnvs() {
    const body = await api('GET', `/api/envs?searchValue=JD_COOKIE&t=${Date.now()}`);
    if (body.code !== 200 || !Array.isArray(body.data)) {
        throw new Error(`获取青龙环境变量失败: ${JSON.stringify(body).slice(0, 200)}`);
    }
    return body.data.filter((env) => env.name === 'JD_COOKIE');
}

async function findEnv(eid) {
    const envs = await getEnvs();
    return envs.find((env) => String(envId(env)) === String(eid));
}

async function getEnvById(eid) {
    const env = await findEnv(eid);
    return env ? env.value : '';
}

// 找不到时返回 99, 调用方回退到列表中的 status
async function getstatus(eid) {
    const env = await findEnv(eid);
    return env ? env.status : 99;
}

async function DisableCk(eid) {
    return api('PUT', `/api/envs/disable?t=${Date.now()}`, [eid]);
}

async function EnableCk(eid) {
    return api('PUT', `/api/envs/enable?t=${Date.now()}`, [eid]);
}

module.exports = {
    getEnvs,
    getEnvById,
    getstatus,
    DisableCk,
    EnableCk,
};
