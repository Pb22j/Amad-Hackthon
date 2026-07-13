from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path


def mutation_score(results: str) -> tuple[int, int, float]:
    lines = [line.strip() for line in results.splitlines() if ":" in line]
    survived = sum(line.endswith(": survived") for line in lines)
    total = len(lines)
    killed = total - survived
    score = killed / total if total else 0.0
    return killed, total, score


def main() -> None:
    parser = argparse.ArgumentParser(description="Enforce the critical-module mutation score")
    parser.add_argument("--minimum", type=float, default=0.70)
    args = parser.parse_args()
    executable = shutil.which("mutmut") or str(Path(sys.executable).with_name("mutmut"))
    output = subprocess.check_output([executable, "results", "--all", "true"], text=True)
    killed, total, score = mutation_score(output)
    print(f"mutation_score={score:.2%} killed={killed} total={total}")
    if score < args.minimum:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
