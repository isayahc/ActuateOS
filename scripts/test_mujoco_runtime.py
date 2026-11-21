"""Exercise real mj_step dynamics, not a mocked or keyframed runtime."""
import json
from pathlib import Path
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"ui"))
import mujoco
import numpy as np
from mujoco_runtime import Simulation, Runtime

FOLDER=ROOT/"artifacts/video-workcells/7ab1900b51ad4600ba9305d9d345a111"


@unittest.skipUnless((FOLDER / "segments.json").exists(), "Requires saved IndustReal segments; task runtime tests use self-contained fixtures")
class PhysicsTests(unittest.TestCase):
    def test_all_segments_contact_and_rewind(self):
        segments=json.loads((FOLDER/"segments.json").read_text())["segments"]
        for segment in segments:
            with self.subTest(step=segment["step_id"]):
                sim=Simulation(FOLDER,segment["step_id"])
                result=sim.advance(segment["duration_s"])
                self.assertGreater(result["steps"],0)
                self.assertGreater(result["contacts"],0)
                self.assertAlmostEqual(result["time_s"],segment["duration_s"],delta=.003)
                self.assertGreater(result["max_tracking_error_m"],.00001)
                self.assertTrue(np.isfinite(sim.data.qpos).all())
                original=sim.advance(.5)["objects"]
                sim.advance(0)
                repeated=sim.advance(.5)["objects"]
                self.assertEqual(original,repeated)
                before=sim.data.qpos.copy();steps=sim.steps
                sim.advance(.5)
                np.testing.assert_array_equal(before,sim.data.qpos)
                self.assertEqual(steps,sim.steps)

    def test_gravity_is_physics_not_target_assignment(self):
        sim=Simulation(FOLDER,"step_1")
        oid=next(iter(sim.moving));body=sim.bodies[oid]
        joint=sim.model.body_jntadr[body];q=sim.model.jnt_qposadr[joint]
        sim.data.eq_active[:]=0
        sim.data.qpos[q:q+3]=[0,2,0]
        sim.data.qvel[:]=0
        for name in sim.geom_names[oid]:
            gid=sim.model.geom(name).id
            sim.model.geom_contype[gid]=1;sim.model.geom_conaffinity[gid]=1
        for _ in range(20):mujoco.mj_step(sim.model,sim.data)
        # 100 ms of freefall should drop about 5 cm, without assigning poses.
        self.assertAlmostEqual(sim.data.qpos[q+1],2-.5*9.81*.1**2,delta=.004)

    def test_sessions_and_invalid_commands(self):
        runtime=Runtime()
        a=runtime.create(FOLDER,"step_1");b=runtime.create(FOLDER,"step_2")
        runtime.get(a["session_id"]).advance(1)
        self.assertEqual(runtime.get(b["session_id"]).data.time,0)
        for value in (-1,float("nan"),float("inf"),True,"1",999):
            with self.assertRaises(ValueError):runtime.get(a["session_id"]).advance(value)
        runtime.close(a["session_id"])
        with self.assertRaises(ValueError):runtime.get(a["session_id"])
        with self.assertRaises(ValueError):Simulation(FOLDER,"missing")


if __name__=="__main__":unittest.main()
