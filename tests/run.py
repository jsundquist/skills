"""Run both test suites. Each skill ships its own `lib.py`, so they cannot share one Python process.

    python tests/run.py
"""
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SUITES = {
    "check": ROOT / "skills" / "repo-supply-chain-check" / "scripts",
    "bootstrap": ROOT / "skills" / "repo-supply-chain-bootstrap" / "scripts",
}

failed = 0
for name, scripts in SUITES.items():
    print(f"== {name}", flush=True)
    env = {**os.environ, "PYTHONPATH": str(scripts)}
    result = subprocess.run([sys.executable, "-m", "unittest", "discover", "-s", str(ROOT / "tests" / name), "-t", str(ROOT / "tests" / name)],
                            env=env)
    failed += result.returncode != 0
sys.exit(1 if failed else 0)
