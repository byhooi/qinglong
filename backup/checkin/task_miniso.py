"""
名创优品签到
name: 名创优品签到
cron: 30 8 * * *
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from replay import run_site  # noqa: E402
from sites import get_site  # noqa: E402

if __name__ == "__main__":
    sys.exit(run_site(get_site("miniso")))
