#!/usr/bin/env python3
"""Execute an agent-authored task graph headlessly with the same server-owned clock."""
from __future__ import annotations

import argparse
from pathlib import Path
import re
import sys
import time
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "ui"))
from task_runtime import TaskExecution


def main() -> None:
    """Run a saved contract, retaining evidence even when work is blocked or fails."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run_id")
    args = parser.parse_args()
    if not re.fullmatch(r"[0-9a-f]{32}", args.run_id):
        parser.error("Invalid run ID")
    execution = TaskExecution(ROOT / "artifacts/video-workcells" / args.run_id)
    output = ROOT / "artifacts/robot-executions" / uuid4().hex
    execution.attach(output)
    print(f"Runtime evidence: {output}", flush=True)
    try:
        execution.start()
        deadline = time.monotonic() + 1800
        while time.monotonic() < deadline:
            state = execution.snapshot()
            if state["phase"] in {"completed", "blocked", "failed"}:
                print(state["phase"], flush=True)
                if state["phase"] != "completed":
                    raise SystemExit(1)
                return
            time.sleep(.2)
        raise SystemExit("Timed out; execution evidence retained")
    finally:
        execution.close()


if __name__ == "__main__":
    main()
