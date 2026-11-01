# -*- coding: utf-8 -*-
"""
签到重放入口

青龙任务名与命令
    每个站点单独建一条任务，互不影响：
        python3 checkin/main.py mylink      定时 30 8 * * *
        python3 checkin/main.py sdl         定时 30 8 * * *
        python3 checkin/main.py honda       定时 30 8 * * *
        python3 checkin/main.py ninebot     定时 30 0 * * *
        python3 checkin/main.py zyh         定时 4 8 * * *
        python3 checkin/main.py miniso      定时 30 8 * * *
        python3 checkin/main.py jtc         定时 6 8 * * *
        python3 checkin/main.py syed        定时 8 8 * * *
        python3 checkin/main.py blug        定时 30 8 * * *
        python3 checkin/main.py mixpark     定时 2 8 * * *

    也可以只建一条任务跑全部：python3 checkin/main.py all

用法
    python main.py <站点>    跑单个站点
    python main.py all       跑全部启用站点
    python main.py --list    列出站点、环境变量与建议定时

退出码
    0 全部成功或无需执行；1 存在失败账号（青龙会标红，便于发现 token 过期）
"""

from __future__ import annotations

import sys
import unicodedata
from pathlib import Path

# 保证从任意工作目录运行都能找到同目录的 replay / sites
sys.path.insert(0, str(Path(__file__).resolve().parent))

from replay import run_site  # noqa: E402
from sites import SITES, get_site, list_sites  # noqa: E402


def _width(text: str) -> int:
    """按终端显示宽度计算，中文占两格"""
    return sum(2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1 for ch in text)


def _pad(text: str, width: int) -> str:
    """左对齐补空格，保证中文列对齐"""
    return text + " " * max(0, width - _width(text))


def print_sites() -> None:
    """打印站点清单"""
    print(f"{_pad('站点', 12)}{_pad('名称', 18)}{_pad('环境变量', 20)}定时")
    print("-" * 72)
    for site in list_sites():
        flag = "" if site.enabled else "（停用）"
        print(
            f"{_pad(site.key, 12)}{_pad(site.name + flag, 18)}"
            f"{_pad(site.env_names[0], 20)}{site.cron}"
        )
    print("-" * 72)
    print("环境变量值为 akino 抓包产出的 JSON 数组，详见 checkin/replay.py 顶部说明")


def main(argv: list[str]) -> int:
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__)
        return 0

    target = argv[0].strip().lower()

    if target in ("--list", "list", "-l"):
        print_sites()
        return 0

    if target == "all":
        results = {site.key: run_site(site) for site in list_sites()}
        failed = [key for key, code in results.items() if code != 0]
        print("=" * 50)
        if failed:
            print(f"存在失败的站点: {', '.join(failed)}")
            return 1
        print("全部站点执行完成，无失败")
        return 0

    site = get_site(target)
    if not site:
        print(f"未知站点: {target}")
        print(f"可用站点: {', '.join(SITES)}")
        return 2

    return run_site(site)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
