"""No API calls: live articulated dynamics, replanning and failure checks."""
import io
import json
from pathlib import Path
import sys
import tarfile
import tempfile
import unittest

import numpy as np

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"ui"));sys.path.insert(0,str(ROOT/"examples"))
from robot_runtime import RobotSimulation
from managed_agent_smoke import read_snapshot_json

FOLDER=ROOT/"artifacts/video-workcells/7ab1900b51ad4600ba9305d9d345a111"
DECISION={"action":"pick_place","object_id":"proxy_beam_left","target_id":"fixture_staging","reason":"Test-supplied skill request, not an agent decision"}


def execute(sim):
    sim.command(DECISION)
    for _ in range(300):
        state=sim.tick(.2)
        if not state["running"]:return state
    raise AssertionError("Robot did not terminate within 60 simulated seconds")


class RobotTests(unittest.TestCase):
    def test_contact_grasp_and_changed_pose_replans(self):
        plans=[]
        for dx,dz in [(0,0),(.08,-.04),(-.06,-.04)]:
            with self.subTest(offset=(dx,dz)):
                sim=RobotSimulation(FOLDER,"step_1");sim.perturb(dx,dz)
                self.assertEqual(sim.model.nmocap,0);self.assertEqual(sim.model.neq,0);self.assertEqual(sim.model.nu,8)
                start=sim.data.qpos[sim.qadr].copy();result=execute(sim)
                self.assertTrue(result["result"]["passed"],result["result"])
                self.assertLess(result["result"]["position_error_m"],.005)
                self.assertGreater(np.linalg.norm(start-sim.data.qpos[sim.qadr]),.1)
                contacts=[e for e in sim.events if e["event"]=="grasp_verified"]
                self.assertEqual(contacts[0]["finger_contacts"],2);self.assertGreater(contacts[0]["rise_m"],.07)
                plans.append(next(e["sha256"] for e in sim.events if e["event"]=="online_plan"))
                sim.command({"action":"finish"});self.assertEqual(sim.agent_status,"verified by agent")
        self.assertEqual(len(set(plans)),3,"Perturbations must produce distinct paths")

    def test_no_gripper_force_means_no_fake_pickup(self):
        sim=RobotSimulation(FOLDER,"step_1")
        sim.model.actuator_forcerange[6:]=0
        result=execute(sim)
        self.assertFalse(result["result"]["passed"])
        self.assertIn("contact",result["result"]["reason"])
        self.assertLess(np.linalg.norm(sim.data.xpos[sim.object_body]-sim.start_position),.01)
        with self.assertRaises(ValueError):sim.command({"action":"finish"})

    def test_obstacle_and_unreachable_goal_fail(self):
        # Compile the real fixture in the approach corridor (including BVH bounds).
        with tempfile.TemporaryDirectory(dir="/tmp/opencode") as temporary:
            folder=Path(temporary)
            for name in ("segmented-workcell.oi.json","segmented-scene-spec.json","segments-spec.json","analysis.json"):
                value=json.loads((FOLDER/name).read_text())
                if name=="segmented-workcell.oi.json":
                    next(i for i in value["instances"] if i["id"]=="assembly_fixture")["position"]=[-.45,.95,.25]
                (folder/name).write_text(json.dumps(value))
            sim=RobotSimulation(folder,"step_1");result=execute(sim)
            self.assertFalse(result["result"]["passed"])
            self.assertIn("intersects",result["result"]["reason"])
        sim=RobotSimulation(FOLDER,"step_1");sim.goal=np.array([10,.8,0])
        result=execute(sim)
        self.assertFalse(result["result"]["passed"])
        self.assertIn("IK",result["result"]["reason"])

    def test_pause_and_input_boundaries(self):
        sim=RobotSimulation(FOLDER,"step_1")
        sim.command(DECISION);sim.tick(.2);sim.running=False
        before=sim.data.qpos.copy();clock=sim.data.time
        sim.tick(.2);np.testing.assert_array_equal(before,sim.data.qpos);self.assertEqual(sim.data.time,clock)
        with self.assertRaises(ValueError):sim.perturb(0,0)
        with self.assertRaises(ValueError):sim.command({"action":"finish"})
        with self.assertRaises(ValueError):RobotSimulation(FOLDER,"step_2")
        with self.assertRaises(ValueError):RobotSimulation(FOLDER,"step_1").perturb(float("nan"),0)

    def test_duplicate_agent_artifacts(self):
        def archive(contents):
            output=io.BytesIO()
            with tarfile.open(fileobj=output,mode="w") as tar:
                for name,value in contents:
                    raw=json.dumps(value).encode();info=tarfile.TarInfo(name);info.size=len(raw);tar.addfile(info,io.BytesIO(raw))
            return output.getvalue()
        value={"action":"finish"}
        same=archive([("decision.json",value),("workspace/decision.json",value)])
        self.assertEqual(read_snapshot_json(same,"decision.json",allow_identical_duplicates=True),value)
        with self.assertRaises(RuntimeError):read_snapshot_json(same,"decision.json")
        with self.assertRaises(RuntimeError):read_snapshot_json(archive([("decision.json",value),("workspace/decision.json",{})]),"decision.json",allow_identical_duplicates=True)


if __name__=="__main__":unittest.main()
