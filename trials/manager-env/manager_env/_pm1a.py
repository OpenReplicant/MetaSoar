"""Puts trials/manager-eval/pm1a on sys.path and imports its modules. They stay the single source: nothing is copied.

pm1a's own modules import each other by flat names (`import drivers`, `import score`), so the folder itself is what has to
be on the path. Set MANAGER_PM1A_DIR to use another copy.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PM1A_DIR = os.path.abspath(os.environ.get("MANAGER_PM1A_DIR") or os.path.join(HERE, "..", "..", "manager-eval", "pm1a"))
if PM1A_DIR not in sys.path:
    sys.path.insert(0, PM1A_DIR)

import drivers  # noqa: E402,F401
import gepa  # noqa: E402,F401
import replay  # noqa: E402,F401
import score  # noqa: E402,F401
import stub_pm  # noqa: E402,F401
