"""Regenerate the 10 committed train days (seeds 0-9) into days/:  python3 gen_days.py [OUT_DIR]"""
import sys

from manager_env.day import DAYS_DIR, write_train_days

for p in write_train_days(sys.argv[1] if len(sys.argv) > 1 else DAYS_DIR):
    print(p)
