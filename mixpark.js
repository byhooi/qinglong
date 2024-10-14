/**
 * cron: 1 0 * * *
 */

// 引入青龙面板提供的 Env
const { Env } = require('./ql');
// 或者尝试：const Env = require('./ql').Env;

const $ = new Env('钧濠MixPark签到');

// 如果 axios 已经全局安装，可以直接使用
const axios = require('axios');
// 如果没有全局安装，可能需要先安装：npm install axios

// sendNotify 通常是青龙面板提供的，路径可能需要调整
const notify = require('./sendNotify');
// 如果上面的路径不对，可以尝试：const notify = require('/ql/scripts/sendNotify');

// 从环境变量获取 mkey 和 token
const Mkey = process.env.MixPark_MKEY;
const token = process.env.MixPark_TOKEN;

async function signIn() {
    const url = '/clientApi/signInRecordAdd';

    const requestBody = {
        token: token,
        version: "4.11.23",
        bid: "ejga",
        mkeyUrl: url,
        mkey: Mkey
    };

    const headers = {
        'content-type': 'application/json'
    };

    try {
        const response = await axios.post('https://wox2019.woxshare.com' + url, requestBody, { headers });
        return response.data;
    } catch (error) {
        console.error('签到失败:', error.message);
        return null;
    }
}

async function main() {
    try {
        console.log('开始执行钧濠MixPark签到脚本');
        const result = await signIn();
        let message = '';

        if (result) {
            if (result.errCode === 0) {
                message = `签到成功! 获得${result.detail.integral}积分, 总积分: ${result.detail.totalIntegral}`;
            } else if (result.errCode === 60101) {
                message = `今日已签到: ${result.errMsg}`;
            } else {
                message = `签到失败: ${result.errMsg}`;
            }
        } else {
            message = '签到操作失败,请检查网络连接';
        }

        console.log(message);
        
        // 使用本地的 sendNotify 发送通知
        await notify.sendNotify("MixPark签到结果", message);
    } catch (error) {
        console.error('签到过程中出错:', error);
        await notify.sendNotify('钧濠MixPark签到', `签到失败: ${error.message}`);
    }
}

main();
