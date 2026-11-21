"""Validated, scene-bound task contracts and dependency scheduling (no physics imports)."""
from __future__ import annotations

from copy import deepcopy
import math
from functools import cache
from typing import Any

Json = dict[str, Any]
SUPPORTED_SKILLS = {"pick_place"}


def vector(value: Any) -> bool:
    """Return whether a value is a finite, bounded SI world-space vector."""
    return isinstance(value, list) and len(value) == 3 and all(
        type(v) in (int, float) and math.isfinite(v) and abs(v) <= 100 for v in value
    )


def validate_plan(plan: Json, analysis: Json, manifest: Json, spec: Json) -> Json:
    """Validate references, DAG, physical bindings and conservative skill limits."""
    if not isinstance(plan, dict) or plan.get("version") != 1:
        raise ValueError("Runtime plan requires version 1")
    tasks = plan.get("tasks")
    if not isinstance(tasks, list) or not 1 <= len(tasks) <= 100:
        raise ValueError("Runtime plan requires 1–100 tasks")
    steps = {s["id"] for s in analysis["steps"]}
    objects = {o["id"]: o for o in spec["objects"]}
    instances = {o["id"]: o for o in manifest["instances"]}
    robot = plan.get("robot_id")
    if robot is not None and (not isinstance(robot, str) or robot not in instances or robot not in objects):
        raise ValueError("Unknown runtime robot binding")
    if robot is not None and (objects[robot]["kind"] != "proposal" or any(instances[robot]["rotation"])):
        raise ValueError("Robot adapter requires an unrotated proposed robot instance")
    initial = plan.get("initial_positions", {})
    if not isinstance(initial, dict) or any(i not in instances or not vector(p) for i, p in initial.items()):
        raise ValueError("Invalid runtime initial positions")
    ids: set[str] = set()
    covered: set[str] = set()
    for task in tasks:
        if not isinstance(task, dict):
            raise ValueError("Task must be an object")
        tid = task.get("id")
        if not isinstance(tid, str) or not tid or tid in ids:
            raise ValueError("Duplicate or invalid runtime task ID")
        ids.add(tid)
        if not isinstance(task.get("step_id"), str) or task["step_id"] not in steps:
            raise ValueError("Runtime task references unknown observed step")
        covered.add(task["step_id"])
        if any(not isinstance(task.get(k), str) or not task[k].strip() for k in ("title", "skill", "scope")):
            raise ValueError("Task needs title, skill and explicit verification scope")
        if not isinstance(task.get("depends_on"), list) or any(not isinstance(d, str) for d in task["depends_on"]):
            raise ValueError("Task dependencies must be IDs")
        if task["skill"] not in SUPPORTED_SKILLS:
            if not isinstance(task.get("reason"), str) or not task["reason"].strip():
                raise ValueError("Unsupported task requires a reason")
            continue
        oid = task.get("object_id")
        if not robot or plan.get("robot_profile") != "parallel_gripper_v1":
            raise ValueError("pick_place requires the parallel_gripper_v1 robot profile")
        if not isinstance(oid, str) or oid == robot or oid not in instances or oid not in objects:
            raise ValueError("Unknown pick_place object binding")
        obj = objects[oid]
        # The existing top-down gripper only has a validated controller for small
        # unrotated boxes. A binding is not permission to pretend other tools exist.
        parts = obj.get("parts", [])
        if obj["kind"] != "proposal" or len(parts) != 1 or parts[0].get("shape") != "box":
            raise ValueError("pick_place supports single-box proposed workpieces only")
        size = parts[0].get("size")
        if not vector(size) or not (.008 <= size[0] <= .07 and .015 <= size[1] <= .035 and .02 <= size[2] <= .15):
            raise ValueError("Workpiece dimensions exceed parallel_gripper_v1 capability")
        if any(parts[0]["rotation"]) or any(instances[oid]["rotation"]):
            raise ValueError("pick_place currently requires unrotated workpieces")
        target = task.get("target")
        if not isinstance(target, dict) or not isinstance(target.get("id"), str) or not target["id"] or not vector(target.get("position")):
            raise ValueError("Task requires an explicit target ID and position")
        # Targets are free-body origin positions, not gripper or mesh centers.
        for key, default, upper in (("position_tolerance_m", .025, .025), ("speed_tolerance", .05, .05)):
            value = task.get(key, default)
            if type(value) not in (int, float) or not math.isfinite(value) or not 0 < value <= upper:
                raise ValueError(f"Invalid verification criterion: {key}")
    movable = {t["object_id"] for t in tasks if t["skill"] in SUPPORTED_SKILLS}
    if not set(initial).issubset(movable):
        raise ValueError("Initial position overrides must bind supported movable workpieces")
    if covered != steps:
        raise ValueError("Every observed step needs an executable or explicitly unsupported task")
    task_by_id = {t["id"]: t for t in tasks}
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(tid: str) -> None:
        """Reject missing references and dependency cycles before dispatch."""
        if tid in visiting:
            raise ValueError("Cyclic runtime task graph")
        if tid in visited:
            return
        visiting.add(tid)
        for dependency in task_by_id[tid]["depends_on"]:
            if dependency not in ids:
                raise ValueError("Unknown runtime dependency")
            visit(dependency)
        visiting.remove(tid)
        visited.add(tid)

    for tid in ids:
        visit(tid)
    # Preserve evidence-level dependencies: all tasks for a prerequisite observed
    # step must be ancestors, including unsupported operations in that step.
    @cache
    def ancestors(tid: str) -> set[str]:
        """Return transitive prerequisite task IDs for an acyclic graph."""
        result: set[str] = set()
        for dep in task_by_id[tid]["depends_on"]:
            result.add(dep)
            result.update(ancestors(dep))
        return result

    for task in tasks:
        observed = next(s for s in analysis["steps"] if s["id"] == task["step_id"])
        required = {t["id"] for t in tasks if t["step_id"] in observed.get("depends_on", [])}
        if not required.issubset(ancestors(task["id"])):
            raise ValueError("Runtime graph drops an observed step dependency")
    return deepcopy(plan)


class TaskGraph:
    """Sequential resource dispatch over a DAG; only verified results unlock work."""

    def __init__(self, plan: Json) -> None:
        """Initialize independent task state from an already validated plan."""
        self.tasks = deepcopy(plan["tasks"])
        self.states: dict[str, Json] = {
            t["id"]: {"status": "pending" if t["skill"] in SUPPORTED_SKILLS else "unsupported",
                       "reason": "" if t["skill"] in SUPPORTED_SKILLS else t["reason"]}
            for t in self.tasks
        }
        self.active: str | None = None

    def next_task(self) -> Json | None:
        """Reserve one ready task, propagating failures without blocking other branches."""
        if self.active:
            return None
        changed = True
        while changed:
            changed = False
            for task in self.tasks:
                state = self.states[task["id"]]
                if state["status"] == "pending" and any(
                    self.states[d]["status"] in {"failed", "unsupported", "blocked"} for d in task["depends_on"]
                ):
                    state.update(status="blocked", reason="A prerequisite failed or has no supported skill")
                    changed = True
        for task in self.tasks:
            if self.states[task["id"]]["status"] == "pending" and all(
                self.states[d]["status"] == "succeeded" for d in task["depends_on"]
            ):
                self.active = task["id"]
                self.states[self.active]["status"] = "running"
                return task
        return None

    def finish(self, result: Json) -> None:
        """Record measured success or failure for the reserved task."""
        if self.active is None:
            raise ValueError("No task is running")
        self.states[self.active].update(
            status="succeeded" if result.get("passed") is True else "failed", result=deepcopy(result)
        )
        self.active = None

    def snapshot(self) -> list[Json]:
        """Expose task definitions alongside independent execution outcomes."""
        return [{**deepcopy(t), **deepcopy(self.states[t["id"]])} for t in self.tasks]
