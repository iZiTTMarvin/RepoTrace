from __future__ import annotations

import argparse
import json

from app.support.github_benchmark import run_github_benchmark


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the frozen real GitHub Issue -> merged PR benchmark")
    parser.add_argument("--scope", choices=("repo", "global"), default="repo")
    args = parser.parse_args()
    print(json.dumps(run_github_benchmark(scope=args.scope), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
