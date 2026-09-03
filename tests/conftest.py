import os
import sys

# 讓tests/ 底下的測試可以直接`import tracker`、`import database`等，
# 因為src/ 內部模組彼此是用相對於src/ 的方式互相import(例如tracker.py裡的
# `import config as cfg`)，所以這裡加的是src/ 本身，而不是專案根目錄。
SRC_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src")
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)
