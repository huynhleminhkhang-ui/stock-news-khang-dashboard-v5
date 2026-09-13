import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from background_news import run_update

if __name__ == "__main__":
    count = run_update()
    print(f"Background news update completed: {count} records")
