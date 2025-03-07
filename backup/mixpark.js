/**
 * cron: 1 0 * * *
 */

const axios = require('axios');
const notify = require('./sendNotify');

// 从环境变量获取 mkey 和 token
const Mkey = process.env.MixPark_MKEY;
const token = process.env.MixPark_TOKEN;

async function signIn() {
    const url = '/clientApi/signInRecordAdd';

    const requestBody = {
        token: token,
        version: "4.11.24",
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
}

main();
