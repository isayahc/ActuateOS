"""Offline controller regressions using scene-bound, self-contained geometry."""
from __future__ import annotations

import io
import json
from pathlib import Path
import sys
import tarfile
import tempfile
import unittest
from typing import Any

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "ui"))
sys.path.insert(0, str(ROOT / "examples"))
from robot_runtime import RobotSimulation
from managed_agent_smoke import read_snapshot_json
from test_task_runtime import fixture


def execute(sim: RobotSimulation) -> dict[str, Any]:
    """Run the bound skill until its verifier produces a terminal result."""
    sim.command({"action": "pick_place", "object_id": sim.object_id,
                 "target_id": sim.task["target"]["id"], "reason": "Offline controller test"})
    for _ in range(650):
        state = sim.tick(.2)
        if not state["running"]:
            return state
    raise AssertionError("Skill exceeded execution budget")


class RobotTests(unittest.TestCase):
    """Check replanning, failure reporting and command validation in real physics."""

    def setUp(self) -> None:
        """Use fresh geometry for every test, without downloaded run artifacts."""
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)
        self.plan = fixture(self.folder)["runtime-plan.json"]

    def simulation(self) -> RobotSimulation:
        """Construct the bound robot adapter."""
        return RobotSimulation(self.folder, self.plan["tasks"][0], self.plan)

    def test_contact_grasp_and_changed_pose_replans(self) -> None:
        """Observed source offsets change trajectories while preserving contact grasp."""
        hashes = []
        for dx, dz in [(0, 0), (.04, -.03), (-.04, -.03)]:
            with self.subTest(offset=(dx, dz)):
                sim = self.simulation()
                sim.perturb(dx, dz)
                result = execute(sim)
                self.assertTrue(result["result"]["passed"], result["result"])
                self.assertTrue(any(e["event"] == "grasp_verified" and e["finger_contacts"] == 2 for e in sim.events))
                hashes.append(next(e["sha256"] for e in sim.events if e["event"] == "online_plan"))
        self.assertEqual(len(set(hashes)), 3)

    def test_offset_geometry_uses_mesh_center_for_grasp(self) -> None:
        """Equivalent geometry with a different body origin must still transfer."""
        from task_graph import validate_plan
        for offset in ([.06, 0, 0], [0, -.012, 0], [0, 0, .06]):
            with self.subTest(offset=offset):
                values = fixture(self.folder)
                manifest = values["segmented-workcell.oi.json"]
                spec = values["segmented-scene-spec.json"]
                shift = np.array(offset)
                vertices = np.array(manifest["bundledAssets"][-1]["parts"][0]["vertices"]).reshape(-1, 3)
                manifest["bundledAssets"][-1]["parts"][0]["vertices"] = (vertices + shift).reshape(-1).tolist()
                for item in (manifest["instances"][-1], spec["objects"][-1]):
                    item["position"] = (np.array(item["position"]) - shift).tolist()
                spec["objects"][-1]["parts"][0]["position"] = (np.array([0, .012, 0]) + shift).tolist()
                plan = values["runtime-plan.json"]
                for task in plan["tasks"]:
                    task["target"]["position"] = (np.array(task["target"]["position"]) - shift).tolist()
                validate_plan(plan, values["analysis.json"], manifest, spec)
                for name, value in values.items():
                    (self.folder / name).write_text(json.dumps(value))
                sim = RobotSimulation(self.folder, plan["tasks"][0], plan)
                for task in plan["tasks"]:
                    sim.bind_task(task)
                    result = execute(sim)
                    self.assertTrue(result["result"]["passed"], result["result"])
                    self.assertTrue(any(e["event"] == "grasp_verified" for e in sim.events))

    def test_obstacle_and_unreachable_target_fail(self) -> None:
        """The controller rejects impossible targets instead of replaying a path."""
        sim = self.simulation()
        sim.goal = np.array([10., .8, 0])
        result = execute(sim)
        self.assertFalse(result["result"]["passed"])
        self.assertIn("IK", result["result"]["reason"])
        sim = self.simulation()
        # A target inside the solid support must fail collision planning/placement.
        sim.goal = np.array([.12, .4, -.1])
        result = execute(sim)
        self.assertFalse(result["result"]["passed"])

    def test_input_boundaries_and_measured_finish(self) -> None:
        """Unknown bindings, invalid perturbations and unverified finish are rejected."""
        sim = self.simulation()
        for decision in ({"action": "finish"}, {"action": "pick_place", "object_id": "other", "target_id": "destination_a"}):
            with self.assertRaises(ValueError):
                sim.command(decision)
        with self.assertRaises(ValueError):
            sim.perturb(float("nan"), 0)
        self.assertTrue(execute(sim)["result"]["passed"])
        sim.command({"action": "finish"})
        self.assertEqual(sim.agent_status, "verified by agent")

    def test_duplicate_agent_artifacts(self) -> None:
        """Permit identical sandbox duplicate paths, but never conflicting decisions."""
        def archive(contents: list[tuple[str, dict[str, Any]]]) -> bytes:
            """Build a sandbox snapshot in memory."""
            output = io.BytesIO()
            with tarfile.open(fileobj=output, mode="w") as tar:
                for name, value in contents:
                    raw = json.dumps(value).encode()
                    info = tarfile.TarInfo(name)
                    info.size = len(raw)
                    tar.addfile(info, io.BytesIO(raw))
            return output.getvalue()
        value = {"action": "finish"}
        same = archive([("decision.json", value), ("workspace/decision.json", value)])
        self.assertEqual(read_snapshot_json(same, "decision.json", allow_identical_duplicates=True), value)
        with self.assertRaises(RuntimeError):
            read_snapshot_json(same, "decision.json")
        with self.assertRaises(RuntimeError):
            read_snapshot_json(archive([("decision.json", value), ("workspace/decision.json", {})]), "decision.json", allow_identical_duplicates=True)


if __name__ == "__main__":
    unittest.main()
