"""Self-contained task execution tests; no dataset downloads or provider API calls."""
from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import sys
import tempfile
import time
import unittest
import threading
from unittest.mock import patch
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "ui"))
from task_graph import TaskGraph, validate_plan
from task_runtime import TaskExecution


def fixture(folder: Path) -> dict[str, Any]:
    """Write a tiny scene with deliberately non-demo IDs and two dependent transfers."""
    definitions = [
        ("surface_x", [1.5, .8, 1.], [0, 0, 0]),
        ("arm_z", [.1, .1, .1], [0, 0, -.8]),
        ("part_42", [.015, .024, .1], [0, .8, -.1]),
    ]
    objects, instances, assets = [], [], []
    for oid, size, position in definitions:
        w, h, d = size
        vertices = [coordinate for x in [-w/2, w/2] for y in [0, h] for z in [-d/2, d/2] for coordinate in [x, y, z]]
        indices = [0, 1, 3, 0, 3, 2, 4, 6, 7, 4, 7, 5, 0, 4, 5, 0, 5, 1,
                   2, 3, 7, 2, 7, 6, 0, 2, 6, 0, 6, 4, 1, 5, 7, 1, 7, 3]
        objects.append({"id": oid, "kind": "proposal", "position": position, "rotation": [0, 0, 0],
                        "parts": [{"shape": "box", "size": size, "rotation": [0, 0, 0]}]})
        instances.append({"id": oid, "assetId": oid, "position": position, "rotation": [0, 0, 0], "visible": True})
        assets.append({"id": oid, "parts": [{"vertices": vertices, "indices": indices, "color": [.5, .5, .5]}]})
    tasks = [{"id": "transfer_1", "step_id": "observed_alpha", "title": "Stage component", "skill": "pick_place",
              "object_id": "part_42", "target": {"id": "destination_a", "position": [.12, .8, -.1]},
              "scope": "Simulated component placement only", "depends_on": []},
             {"id": "transfer_2", "step_id": "observed_beta", "title": "Move staged component", "skill": "pick_place",
              "object_id": "part_42", "target": {"id": "destination_b", "position": [-.10, .8, -.1]},
              "scope": "Second simulated placement only", "depends_on": ["transfer_1"]}]
    values = {
        "analysis.json": {"steps": [{"id": "observed_alpha", "depends_on": []}, {"id": "observed_beta", "depends_on": ["observed_alpha"]}]},
        "segmented-scene-spec.json": {"objects": objects},
        "segmented-workcell.oi.json": {"instances": instances, "bundledAssets": assets},
        "runtime-plan.json": {"version": 1, "robot_id": "arm_z", "robot_profile": "parallel_gripper_v1", "tasks": tasks},
    }
    for name, value in values.items():
        (folder / name).write_text(json.dumps(value))
    return values


class ContractTests(unittest.TestCase):
    """Validate graph semantics separately from robot control."""

    def setUp(self) -> None:
        """Prepare an isolated scene for each mutation test."""
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.values = fixture(Path(self.temp.name))

    def validate(self, plan: dict[str, Any]) -> dict[str, Any]:
        """Validate a plan against the fixture's evidence and geometry."""
        return validate_plan(plan, self.values["analysis.json"], self.values["segmented-workcell.oi.json"], self.values["segmented-scene-spec.json"])

    def test_reference_cycle_and_evidence_dependency_validation(self) -> None:
        """Unknown IDs, cycles and silently removed evidence edges cannot execute."""
        plan = self.values["runtime-plan.json"]
        self.validate(plan)
        for field, value in [("object_id", "missing"), ("depends_on", ["transfer_2"]), ("target", {"id": "x", "position": [float("nan"), 0, 0]})]:
            bad = deepcopy(plan)
            bad["tasks"][0][field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                self.validate(bad)
        bad = deepcopy(plan)
        bad["tasks"][1]["depends_on"] = []
        with self.assertRaisesRegex(ValueError, "observed step dependency"):
            self.validate(bad)

    def test_failure_blocks_descendants_and_independent_work_can_continue(self) -> None:
        """Only measured success unlocks dependencies; independent branches remain ready."""
        plan = self.values["runtime-plan.json"]
        independent = {**deepcopy(plan["tasks"][0]), "id": "independent"}
        plan["tasks"].append(independent)
        # Additional task belongs to the prerequisite observed step, so beta must wait for both.
        plan["tasks"][1]["depends_on"].append("independent")
        graph = TaskGraph(self.validate(plan))
        self.assertEqual(graph.next_task()["id"], "transfer_1")
        graph.finish({"passed": False, "reason": "No contact"})
        self.assertEqual(graph.next_task()["id"], "independent")
        self.assertEqual(graph.states["transfer_2"]["status"], "blocked")
        graph.finish({"passed": True})
        self.assertIsNone(graph.next_task())

    def test_unsupported_is_not_success(self) -> None:
        """An animated fastening operation does not become executable."""
        plan = self.values["runtime-plan.json"]
        plan["tasks"][0].update(skill="fasten", reason="No fastening controller")
        graph = TaskGraph(self.validate(plan))
        self.assertIsNone(graph.next_task())
        self.assertEqual(graph.states["transfer_1"]["status"], "unsupported")
        self.assertEqual(graph.states["transfer_2"]["status"], "blocked")


class ExecutionTests(unittest.TestCase):
    """Exercise real MuJoCo, state retention, lifecycle and the independent clock."""

    def setUp(self) -> None:
        """Create a minimal world without the demo's saved artifacts."""
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)
        fixture(self.folder)

    def execution(self) -> TaskExecution:
        """Create an execution and guarantee worker cleanup after assertion failures."""
        execution = TaskExecution(self.folder)
        self.addCleanup(execution.close)
        return execution

    def test_two_tasks_use_live_state_in_same_world(self) -> None:
        """Two arbitrary IDs execute sequentially without resetting the workpiece."""
        execution = self.execution()
        simulation = execution.simulation
        self.assertEqual(simulation.model.nmocap, 0)
        self.assertEqual(simulation.model.neq, 0)
        execution.start()
        for _ in range(1200):
            state = execution.tick(.2)
            if not state["running"]:
                break
        self.assertEqual(state["phase"], "completed", state["tasks"])
        self.assertTrue(all(t["status"] == "succeeded" for t in state["tasks"]))
        self.assertIs(execution.simulation, simulation)
        starts = [e for e in state["events"] if e["event"] == "task_started"]
        self.assertEqual([e["task_id"] for e in starts], ["transfer_1", "transfer_2"])
        self.assertLess(abs(simulation.data.xpos[simulation.object_body][0] + .10), .025)

    def test_agent_review_finishes_before_next_task_binding(self) -> None:
        """Provider-loop completion gates dispatch even after physical success."""
        execution = self.execution()
        execution.evidence_dir = self.folder / "agent-evidence"
        execution.evidence_dir.mkdir()
        release = threading.Event()
        calls: list[str] = []
        threads: list[threading.Thread] = []

        def fake_agent(sim: Any, sid: str, key: str) -> threading.Thread:
            """Stand in for remote inference while retaining real contact execution."""
            calls.append(sim.task["id"])
            sim.agent_status = "executing"
            sim.command({"action": "pick_place", "object_id": sim.object_id,
                         "target_id": sim.task["target"]["id"], "reason": "Test inference"})
            def review() -> None:
                """Hold the first task review open until the assertion releases it."""
                release.wait(timeout=10)
                with sim.lock:
                    sim.agent_status = "verified by agent"
            worker = threading.Thread(target=review, daemon=True)
            threads.append(worker)
            worker.start()
            return worker

        with patch("robot_agent.start_agent", fake_agent):
            try:
                execution.start(agent_key="offline-test-key")
                for _ in range(650):
                    state = execution.tick(.2)
                    if state["phase"] == "awaiting_agent" and state["result"]:
                        break
                self.assertTrue(state["result"]["passed"])
                self.assertEqual(calls, ["transfer_1"])
                self.assertEqual(state["tasks"][0]["status"], "running")
                self.assertEqual(state["tasks"][1]["status"], "pending")
                release.set()
                threads[0].join(timeout=2)
                execution.tick(.2)
                self.assertEqual(execution.graph.states["transfer_1"]["status"], "succeeded")
                self.assertNotIn("offline-test-key", json.dumps(execution.snapshot()))
            finally:
                release.set()
                for worker in threads:
                    worker.join(timeout=2)

    def test_distinct_workpieces_share_the_world(self) -> None:
        """Different object bindings select different free bodies without rebuilding."""
        spec = json.loads((self.folder / "segmented-scene-spec.json").read_text())
        manifest = json.loads((self.folder / "segmented-workcell.oi.json").read_text())
        plan = json.loads((self.folder / "runtime-plan.json").read_text())
        obj = deepcopy(spec["objects"][-1])
        obj.update(id="another_part", position=[.24, .8, -.1])
        spec["objects"].append(obj)
        instance = deepcopy(manifest["instances"][-1])
        instance.update(id="another_part", position=obj["position"])
        manifest["instances"].append(instance)
        plan["tasks"][1]["object_id"] = "another_part"
        for name, value in (("segmented-scene-spec.json", spec), ("segmented-workcell.oi.json", manifest), ("runtime-plan.json", plan)):
            (self.folder / name).write_text(json.dumps(value))
        execution = self.execution()
        self.assertEqual(len(execution.simulation.workpiece_joints), 2)
        execution.start()
        for _ in range(1200):
            state = execution.tick(.2)
            if not state["running"]:
                break
        self.assertEqual(state["phase"], "completed", state["tasks"])
        poses = {o["id"]: o["position"] for o in state["objects"]}
        self.assertAlmostEqual(poses["part_42"][0], .12, delta=.025)
        self.assertAlmostEqual(poses["another_part"][0], -.10, delta=.025)

    def test_entirely_unsupported_plan_has_no_fake_physics(self) -> None:
        """An unsupported-only plan reports blocked without constructing a robot."""
        plan = json.loads((self.folder / "runtime-plan.json").read_text())
        plan["robot_id"] = None
        for task in plan["tasks"]:
            task.update(skill="assemble", reason="No assembly controller")
        (self.folder / "runtime-plan.json").write_text(json.dumps(plan))
        execution = self.execution()
        self.assertIsNone(execution.simulation)
        execution.start()
        state = execution.tick()
        self.assertEqual(state["phase"], "blocked")
        self.assertEqual(state["steps"], 0)
        self.assertTrue(all(t["status"] == "unsupported" for t in state["tasks"]))

    def test_lost_grip_blocks_following_task(self) -> None:
        """A failed contact grasp must never release its dependency."""
        execution = self.execution()
        execution.simulation.model.actuator_forcerange[6:] = 0
        execution.start()
        for _ in range(600):
            state = execution.tick(.2)
            if not state["running"]:
                break
        self.assertEqual([t["status"] for t in state["tasks"]], ["failed", "blocked"])
        self.assertNotEqual(state["phase"], "completed")

    def test_background_clock_pause_close_and_persistence(self) -> None:
        """Work advances with no viewer; reading state does not drive time."""
        execution = self.execution()
        execution.attach(self.folder / "evidence")
        execution.start()
        deadline = time.monotonic() + 10
        while execution.snapshot()["steps"] < 40 and time.monotonic() < deadline:
            time.sleep(.05)
        self.assertGreater(execution.snapshot()["steps"], 0)
        execution.pause(True)
        before = execution.snapshot()["time_s"]
        time.sleep(.2)
        for _ in range(20):
            self.assertEqual(execution.snapshot()["time_s"], before)
        execution.start()
        deadline = time.monotonic() + 5
        while execution.snapshot()["time_s"] == before and time.monotonic() < deadline:
            time.sleep(.05)
        self.assertGreater(execution.snapshot()["time_s"], before)
        execution.close()
        saved = json.loads((self.folder / "evidence/state.json").read_text())
        self.assertTrue(saved["closed"])
        self.assertFalse(execution._worker.is_alive())
        self.assertEqual(saved["tasks"][0]["status"], "failed")

    def test_missing_plan_never_falls_back_to_animation(self) -> None:
        """Older artifacts require an explicit migration, not inferred execution."""
        (self.folder / "runtime-plan.json").unlink()
        with self.assertRaisesRegex(ValueError, "no runtime-plan"):
            self.execution()


if __name__ == "__main__":
    unittest.main()
