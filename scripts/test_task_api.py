"""HTTP integration coverage for task control and server-owned execution."""
from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
import threading
import time
import unittest
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "ui"))
import server
from mujoco_runtime import Runtime
from test_task_runtime import fixture


class RuntimeApiTests(unittest.TestCase):
    """Exercise the actual HTTP handlers, worker and physics without Gemini."""

    def test_reconnect_read_only_poll_pause_and_cancellation(self) -> None:
        """Read requests never own the clock and reference changes retain the session."""
        with tempfile.TemporaryDirectory() as temporary:
            artifacts = Path(temporary)
            run_id = "a" * 32
            folder = artifacts / "video-workcells" / run_id
            folder.mkdir(parents=True)
            fixture(folder)
            runtime = Runtime()
            with patch.object(server, "ARTIFACTS", artifacts), patch.object(server, "runtime", runtime):
                http = server.ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
                worker = threading.Thread(target=http.serve_forever, daemon=True)
                worker.start()
                origin = f"http://127.0.0.1:{http.server_port}"

                def post(action: str, body: dict) -> dict:
                    """Send a same-origin control request to the actual handler."""
                    request = Request(origin + "/api/runtime/" + action, data=json.dumps(body).encode(),
                                      headers={"Origin": origin, "Content-Type": "application/json"})
                    with urlopen(request, timeout=10) as response:
                        return json.load(response)

                try:
                    connection = post("connect", {"run_id": run_id, "step_id": "observed_alpha", "mode": "robot"})
                    sid = connection["session_id"]
                    body = {"session_id": sid}
                    post("robot-start", body)
                    # No requests while the server worker advances physics.
                    time.sleep(.35)
                    post("robot-pause", {**body, "paused": True})
                    state = post("state", body)
                    self.assertGreater(state["steps"], 0)
                    for _ in range(5):
                        self.assertEqual(post("robot-tick", body)["time_s"], state["time_s"])
                    again = post("connect", {"run_id": run_id, "step_id": "observed_beta", "mode": "robot"})
                    self.assertEqual(again["session_id"], sid)
                    self.assertEqual(again["time_s"], state["time_s"])
                    post("robot-pause", {**body, "paused": False})
                    time.sleep(.25)
                    self.assertGreater(post("state", body)["time_s"], state["time_s"])
                    post("close", body)
                    with self.assertRaises(HTTPError) as raised:
                        post("state", body)
                    self.assertEqual(raised.exception.code, 409)
                    with urlopen(origin + f"/media/robot/{sid}/state.json", timeout=5) as response:
                        saved = json.load(response)
                    self.assertEqual(saved["phase"], "cancelled")
                    self.assertEqual(saved["tasks"][0]["status"], "failed")
                finally:
                    runtime.shutdown()
                    http.shutdown()
                    http.server_close()
                    worker.join(timeout=2)


if __name__ == "__main__":
    unittest.main()
