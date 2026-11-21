"""Verify explicit model selection survives the managed-agent transport."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "examples"))
from managed_agent_smoke import DEFAULT_AGENT, OBSERVATION_MODEL, PLANNING_MODEL, interact


class ModelRoutingTests(unittest.TestCase):
    def test_both_models_are_sent_and_persisted(self):
        for model in (OBSERVATION_MODEL, PLANNING_MODEL):
            with self.subTest(model=model), tempfile.TemporaryDirectory() as directory:
                output = Path(directory)
                response = {"id": "interaction", "environment_id": "sandbox", "status": "completed"}
                with patch("managed_agent_smoke.request", return_value=json.dumps(response).encode()) as request:
                    result = interact("secret", DEFAULT_AGENT, "observe", output, 2,
                                      previous={"id": "previous", "environment_id": "sandbox"}, model=model)
                payload = request.call_args.args[2]
                self.assertEqual(payload["agent_config"], {"type": "antigravity", "model": model})
                self.assertEqual(payload["previous_interaction_id"], "previous")
                self.assertEqual(payload["environment"], "sandbox")
                self.assertEqual(result, response)
                evidence = json.loads((output / "model-2.json").read_text())
                self.assertEqual(evidence["requested_model"], model)
                self.assertEqual(evidence["status"], "completed")
                self.assertNotIn("secret", (output / "model-2.json").read_text())

    def test_no_silent_fallback(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch("managed_agent_smoke.request", side_effect=RuntimeError("model unavailable")) as request:
                with self.assertRaisesRegex(RuntimeError, "model unavailable"):
                    interact("secret", DEFAULT_AGENT, "plan", Path(directory), 1, model=PLANNING_MODEL)
                self.assertEqual(request.call_count, 1)


if __name__ == "__main__":
    unittest.main()
