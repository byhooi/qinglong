# -*- coding: utf-8 -*-
"""
站点配置表

每个站点对应桌面 s/ 目录下的一个 .sgmodule。配置项来自模块头部的 #!arguments：
    ckName  -> 环境变量后缀（CHECKIN_<CKNAME>）
    hostname / regx -> 默认 URL
    cron    -> 建议的青龙定时

环境变量统一命名：CHECKIN_<CKNAME 大写>
    CHECKIN_MYLINK / CHECKIN_SDL / CHECKIN_HONDA / CHECKIN_NINEBOT / CHECKIN_ZYH
    CHECKIN_MINISO / CHECKIN_JTC / CHECKIN_SYED / CHECKIN_BLUG / CHECKIN_MIXPARK

值为 akino 抓包产出的 JSON 数组，格式见 replay.py 顶部说明。
"""

from __future__ import annotations

from replay import SiteConfig

# 通用成功/失败关键字，各站点可覆盖。
# 「已签到」类文案一律算成功：重复签到不是故障，不该让青龙标红。
# 失败词特意写窄，避免响应正文里出现「失败」二字就误判。
COMMON_SUCCESS_KEYWORDS = (
    "签到成功",
    "签到完成",
    "已签到",
    "已经签到",
    "今日已签到",
    "不可重复签到",
    "重复签到",
    "已领取",
    "领取成功",
    "success",
    "SUCCESS",
)
COMMON_FAIL_KEYWORDS = (
    "签到失败",
    "token失效",
    "token过期",
    "登录已过期",
    "请重新登录",
    "未登录",
    "用户不存在",
)


SITES: dict[str, SiteConfig] = {
    "mylink": SiteConfig(
        key="mylink",
        name="mylink",
        env_names=("CHECKIN_MYLINK",),
        default_url="https://mylink.komect.com/v1/api/eas/sign/sign_in",
        default_method="POST",
        success_keywords=COMMON_SUCCESS_KEYWORDS,
        fail_keywords=COMMON_FAIL_KEYWORDS,
        # 响应结构固定为 {body:{}, header:{resultCode, resultMsg}}，
        # 消息只在 header 下，精确取比递归猜可靠
        message_path="header.resultMsg",
        cron="30 8 * * *",
    ),
    "sdl": SiteConfig(
        key="sdl",
        name="三得利签到",
        env_names=("CHECKIN_SDL",),
        default_url="https://xiaodian.miyatech.com/api/coupon/auth/signIn",
        default_method="POST",
        success_keywords=COMMON_SUCCESS_KEYWORDS,
        fail_keywords=COMMON_FAIL_KEYWORDS,
        cron="30 8 * * *",
    ),
    "honda": SiteConfig(
        key="honda",
        name="东风本田签到",
        env_names=("CHECKIN_HONDA",),
        default_url=(
            "https://weixin.dongfeng-honda.com/weicheapi/honda-center-docking"
            "/marketingOperations/adapterInterface"
        ),
        default_method="POST",
        success_keywords=COMMON_SUCCESS_KEYWORDS,
        fail_keywords=COMMON_FAIL_KEYWORDS,
        cron="30 8 * * *",
        note="接口是适配层入口，可能依赖 body 中的 action 字段，重放时必须原样带上 body",
    ),
    "ninebot": SiteConfig(
        key="ninebot",
        name="九号电动签到",
        env_names=("CHECKIN_NINEBOT",),
        default_url="https://cn-cbu-gateway.ninebot.com/portal/api/user-sign/v2/sign",
        default_method="POST",
        success_keywords=COMMON_SUCCESS_KEYWORDS,
        fail_keywords=COMMON_FAIL_KEYWORDS,
        cron="30 0 * * *",
    ),
    "zyh": SiteConfig(
        key="zyh",
        name="卓悦汇签到",
        env_names=("CHECKIN_ZYH",),
        default_url="https://m.mallcoo.cn/api/user/User/CheckinV2",
        default_method="POST",
        success_keywords=COMMON_SUCCESS_KEYWORDS,
        fail_keywords=COMMON_FAIL_KEYWORDS,
        cron="4 8 * * *",
    ),
    "miniso": SiteConfig(
        key="miniso",
        name="名创优品",
        env_names=("CHECKIN_MINISO",),
        default_url=(
            "https://api-saas.miniso.com/task-manage-platform"
            "/api/activity/signInTask/award/receive"
        ),
        default_method="POST",
        success_keywords=COMMON_SUCCESS_KEYWORDS,
        fail_keywords=COMMON_FAIL_KEYWORDS,
        cron="30 8 * * *",
        note="抓的是「领取奖励」接口，前置的签到动作若单独存在需另行补抓",
    ),
    "jtc": SiteConfig(
        key="jtc",
        name="捷停车签到",
        env_names=("CHECKIN_JTC",),
        default_url="https://sytgate.jslife.com.cn/base-gateway/integral/v2/task/receive",
        default_method="POST",
        success_keywords=COMMON_SUCCESS_KEYWORDS,
        fail_keywords=COMMON_FAIL_KEYWORDS,
        cron="6 8 * * *",
    ),
    "syed": SiteConfig(
        key="syed",
        name="深业签到",
        env_names=("CHECKIN_SYED", "SHENYE_COOKIE"),
        default_url="https://molli2.sycommercial.com/restful/mall/3867/checkInRecord",
        default_method="POST",
        success_keywords=COMMON_SUCCESS_KEYWORDS,
        fail_keywords=COMMON_FAIL_KEYWORDS,
        cron="8 8 * * *",
        note="与 shenye/ 下的旧脚本等效，兼容其 SHENYE_COOKIE 变量名",
    ),
    "blug": SiteConfig(
        key="blug",
        name="百晟广场签到",
        env_names=("CHECKIN_BLUG",),
        # 原抓包 URL 带 loginStatus / stamp / timeStamp / sign 四个参数，
        # 其中 timeStamp 与 sign 大概率参与服务端签名校验，属于一次性参数。
        default_url="https://mini-jlbaisheng.cs26.com/mini/sign/sign",
        default_method="GET",
        success_keywords=COMMON_SUCCESS_KEYWORDS,
        # 不能放裸 "sign"：响应里通常带 sign 字段，会误判成失败
        fail_keywords=COMMON_FAIL_KEYWORDS + ("签名错误", "签名失效", "签名校验失败"),
        cron="30 8 * * *",
        note="高风险：URL 带 timeStamp+sign 签名参数，重放很可能被服务端拒绝，需实测",
    ),
    "mixpark": SiteConfig(
        key="mixpark",
        name="钧濠自动签到",
        env_names=("CHECKIN_MIXPARK",),
        default_url="https://www.digitalflag.cn/gateway/for-c/checkin",
        default_method="POST",
        success_keywords=COMMON_SUCCESS_KEYWORDS,
        fail_keywords=COMMON_FAIL_KEYWORDS,
        cron="2 8 * * *",
    ),
}


def get_site(key: str) -> SiteConfig | None:
    """按标识取站点配置，兼容大小写"""
    return SITES.get(key.strip().lower())


def list_sites() -> list[SiteConfig]:
    """按配置顺序返回全部站点"""
    return list(SITES.values())
