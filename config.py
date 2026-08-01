import os
import sys
from pathlib import Path

BASE_DIR = Path(__file__).parent

if getattr(sys, "frozen", False):
    # Running inside a PyInstaller bundle — use a user-writable location
    # so the database survives upgrades and uninstalls.
    DATA_DIR = Path(os.environ["APPDATA"]) / "FinancialStrategyTracker" / "data"
else:
    # Development — keep data/ next to the source tree
    DATA_DIR = BASE_DIR / "data"

DATA_DIR.mkdir(parents=True, exist_ok=True)
DB_NAME = DATA_DIR / "tracker.db"
