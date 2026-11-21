"""Offline negative controls for the independent plan validator."""

import copy
import json
import unittest

from workcell_trial import FIXTURE, validate


class ValidatorTests(unittest.TestCase):
    def setUp(self):
        self.task = json.loads(FIXTURE.read_text())
        self.plan = {"task_id": self.task["task_id"], "steps": [
            {"operation": "load_base", "machine": "robot_1", "fixture": "fixture_1", "depends_on": [], "start_s": 0, "duration_s": 2},
            {"operation": "load_cap", "machine": "robot_1", "fixture": "fixture_1", "depends_on": [], "start_s": 2, "duration_s": 2},
            {"operation": "seat_cap", "machine": "press_1", "fixture": "fixture_1", "depends_on": ["load_base", "load_cap"], "start_s": 4, "duration_s": 3},
            {"operation": "inspect", "machine": "camera_1", "fixture": "fixture_1", "depends_on": ["seat_cap"], "start_s": 7, "duration_s": 1},
        ]}

    def test_valid_orders(self):
        self.assertTrue(validate(self.plan, self.task)["passed"])
        self.plan["steps"][0]["start_s"] = 2
        self.plan["steps"][1]["start_s"] = 0
        self.assertTrue(validate(self.plan, self.task)["passed"])

    def test_reject_invalid_plans(self):
        mutations = [
            (0, "machine", "camera_1"),
            (1, "start_s", 0),
            (2, "depends_on", ["load_base"]),
            (3, "start_s", 4),
            (0, "duration_s", -1),
            (0, "start_s", float("nan")),
            (0, "depends_on", ["inspect"]),
            (0, "fixture", "invented_fixture"),
            (0, "machine", []),
        ]
        for index, field, value in mutations:
            with self.subTest(field=field, value=value):
                plan = copy.deepcopy(self.plan)
                plan["steps"][index][field] = value
                self.assertFalse(validate(plan, self.task)["passed"])

    def test_missing_operation(self):
        self.plan["steps"].pop()
        self.assertFalse(validate(self.plan, self.task)["passed"])

    def test_precondition_failure(self):
        self.task["initial_state"]["base"] = "missing"
        self.assertFalse(validate(self.plan, self.task)["passed"])

    def test_agent_cannot_override_effects(self):
        self.task["goal_state"]["assembly"] = "impossible"
        self.plan["steps"][-1]["effects"] = {"assembly": "impossible"}
        self.assertFalse(validate(self.plan, self.task)["passed"])


if __name__ == "__main__":
    unittest.main()
