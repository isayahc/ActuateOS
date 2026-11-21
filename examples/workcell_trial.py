#!/usr/bin/env python3
"""Generate and independently validate one symbolic workcell plan with a managed agent."""

import argparse
import json
import math
import os
from pathlib import Path
import sys
import tarfile
from urllib.error import URLError
from urllib.parse import quote
from uuid import uuid4

from managed_agent_smoke import DEFAULT_AGENT, interact, read_snapshot_json, request


FIXTURE = Path(__file__).parent / "fixtures" / "cap_assembly.json"


def validate(plan, task):
    """Validate against trusted task semantics, never agent-supplied effects."""
    errors = []
    operations = {op["id"]: op for op in task["operations"]}
    equipment = {item["id"]: item for item in task["equipment"]}
    if not isinstance(plan, dict) or plan.get("task_id") != task["task_id"]:
        return {"passed": False, "errors": ["Wrong or missing task_id"]}
    steps = plan.get("steps")
    if not isinstance(steps, list) or any(not isinstance(s, dict) for s in steps):
        return {"passed": False, "errors": ["steps must be an array of objects"]}
    ids = [s.get("operation") for s in steps]
    if any(not isinstance(i, str) for i in ids) or sorted(ids) != sorted(operations):
        return {"passed": False, "errors": ["Every operation must appear exactly once"]}
    by_id = {s["operation"]: s for s in steps}
    for step in steps:
        op = operations[step["operation"]]
        machine_id = step.get("machine")
        machine = equipment.get(machine_id) if isinstance(machine_id, str) else None
        if machine is None or op["capability"] not in machine["capabilities"]:
            errors.append(f"Unsupported machine for {op['id']}")
        if step.get("fixture") not in task["fixtures"]:
            errors.append(f"Unknown fixture for {op['id']}")
        for field in ("start_s", "duration_s"):
            value = step.get(field)
            if type(value) not in (int, float) or not math.isfinite(value) or value < 0:
                errors.append(f"Invalid {field} for {op['id']}")
        if step.get("duration_s") != op["duration_s"]:
            errors.append(f"Incorrect duration for {op['id']}")
        deps = step.get("depends_on")
        if not isinstance(deps, list) or any(not isinstance(d, str) for d in deps):
            errors.append(f"Invalid dependencies for {op['id']}")
        elif len(set(deps)) != len(deps) or any(d not in operations or d == op["id"] for d in deps):
            errors.append(f"Unknown, duplicate, or self dependency for {op['id']}")
    if errors:
        return {"passed": False, "errors": errors}

    # These required edges are evaluator-owned, derived from the procedure.
    required = {"seat_cap": {"load_base", "load_cap"}, "inspect": {"seat_cap"}}
    for op_id, deps in required.items():
        if not deps.issubset(by_id[op_id]["depends_on"]):
            errors.append(f"Missing prerequisite edges for {op_id}")
    for step in steps:
        for dependency in step["depends_on"]:
            parent = by_id[dependency]
            if parent["start_s"] + parent["duration_s"] > step["start_s"]:
                errors.append(f"Dependency timing violation for {step['operation']}")
    # All operations have positive durations, so dependency timing also excludes cycles.
    for index, first in enumerate(steps):
        for second in steps[index + 1:]:
            overlap = max(first["start_s"], second["start_s"]) < min(
                first["start_s"] + first["duration_s"],
                second["start_s"] + second["duration_s"],
            )
            if overlap and (first["machine"] == second["machine"] or first["fixture"] == second["fixture"]):
                errors.append(f"Resource overlap: {first['operation']} / {second['operation']}")
    if errors:
        return {"passed": False, "errors": errors}

    state = dict(task["initial_state"])
    trace = []
    for step in sorted(steps, key=lambda s: s["start_s"]):
        op = operations[step["operation"]]
        if any(state.get(k) != v for k, v in op["requires"].items()):
            errors.append(f"Unsatisfied precondition for {op['id']}")
            break
        state.update(op["effects"])
        trace.append({"operation": op["id"], "state": dict(state)})
    if any(state.get(k) != v for k, v in task["goal_state"].items()):
        errors.append("Symbolic final state does not meet the goal")
    return {
        "passed": not errors, "errors": errors, "final_state": state, "trace": trace,
        "makespan_s": max(s["start_s"] + s["duration_s"] for s in steps),
        "verification_scope": "declared symbolic model only; no physical execution",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--agent", default=DEFAULT_AGENT)
    args = parser.parse_args()
    key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if not key:
        parser.error("Set GEMINI_API_KEY or GOOGLE_API_KEY.")
    task = json.loads(FIXTURE.read_text())
    run_id = uuid4().hex
    output = Path(__file__).resolve().parents[1] / "artifacts" / "workcell-trials" / run_id
    output.mkdir(parents=True)
    filename = f"plan-{run_id}.json"
    prompt = (
        "You are a workcell process planner. Reconstruct dependencies from the procedure "
        "and assign operations to supported machines. Produce a feasible sequential schedule. "
        "Use code to write a JSON file named " + filename + " in your working directory. "
        "The JSON must have task_id and steps. Each step must contain operation (an operation ID), "
        "machine (equipment ID), fixture (fixture ID), depends_on (array of predecessor operation IDs), "
        "start_s (nonnegative number), duration_s (specified duration). Include all mandatory direct "
        "prerequisites. Every operation appears exactly once. Do not overlap shared resources. "
        "Use only supplied equipment. Do not claim physical execution. Task:\n" + json.dumps(task)
    )
    (output / "task.json").write_text(json.dumps(task, indent=2) + "\n")
    (output / "prompt.txt").write_text(prompt)
    print(f"Artifacts: {output}", flush=True)
    result = interact(key, args.agent, prompt, output, 1)
    environment = quote(result["environment_id"], safe="")
    snapshot = request(key, f"/files/environment-{environment}:download?alt=media")
    (output / "snapshot.tar").write_bytes(snapshot)
    plan = read_snapshot_json(snapshot, filename)
    (output / "plan.json").write_text(json.dumps(plan, indent=2) + "\n")
    report = validate(plan, task)
    report.update({"run_id": run_id, "agent": args.agent, "interaction_id": result["id"]})
    (output / "validation.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))
    if not report["passed"]:
        raise RuntimeError("Generated plan failed independent validation.")
    print("PASS: live agent produced a valid symbolic task graph and workcell schedule.")


if __name__ == "__main__":
    try:
        main()
    except (RuntimeError, URLError, OSError, ValueError, KeyError, tarfile.TarError) as error:
        print(f"FAIL: {error}", file=sys.stderr)
        sys.exit(1)
