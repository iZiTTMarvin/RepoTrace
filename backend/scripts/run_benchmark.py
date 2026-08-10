from __future__ import annotations

import json

from app.support.demo_benchmark import run_demo_benchmark


if __name__ == "__main__":
    print(json.dumps(run_demo_benchmark(), ensure_ascii=False, indent=2))
