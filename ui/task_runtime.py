"""Server-clock task execution with persistent physics and inspectable outcomes."""
from __future__ import annotations

import json
from pathlib import Path
import threading
import time
from typing import Any

from task_graph import TaskGraph, validate_plan


class TaskExecution:
    """Dispatch a scene-bound DAG into one robot world; never consume animation tracks."""

    def __init__(self, folder: Path) -> None:
        """Load and validate a run's explicit plan before constructing physics."""
        def read(name: str) -> dict[str, Any]:
            """Read a required, run-local JSON artifact."""
            return json.loads((folder / name).read_text())

        if not (folder / "runtime-plan.json").exists():
            raise ValueError("This run has no runtime-plan.json. Generate a runtime plan; storyboard tracks are not executable tasks.")
        self.folder = folder
        self.plan = validate_plan(read("runtime-plan.json"), read("analysis.json"),
                                  read("segmented-workcell.oi.json"), read("segmented-scene-spec.json"))
        self.graph = TaskGraph(self.plan)
        self.lock = threading.RLock()
        self.touched = time.monotonic()
        self.closed = False
        self.running = False
        self.started = False
        self.phase = "idle"
        self.error: str | None = None
        self.events: list[dict[str, Any]] = []
        self.evidence_dir: Path | None = None
        self.simulation: Any = None
        first = next((t for t in self.plan["tasks"] if t["skill"] == "pick_place"), None)
        if first:
            from robot_runtime import RobotSimulation
            self.simulation = RobotSimulation(folder, first, self.plan)
        self._agent_key: str | None = None
        self._agent_thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._worker: threading.Thread | None = None

    def attach(self, directory: Path) -> None:
        """Persist the exact task plan and initial world before launching the clock."""
        with self.lock:
            self.evidence_dir = directory
            directory.mkdir(parents=True, exist_ok=True)
            (directory / "runtime-plan.json").write_text(json.dumps(self.plan, indent=2))
            if self.simulation:
                self.simulation.evidence_dir = directory
                (directory / "model.xml").write_text(self.simulation.xml)
                (directory / "initial-state.json").write_text(json.dumps({
                    "qpos": self.simulation.data.qpos.tolist(), "qvel": self.simulation.data.qvel.tolist(),
                    "ctrl": self.simulation.data.ctrl.tolist(), "source_video_run": self.folder.name,
                }))
            self._persist()
            self._worker = threading.Thread(target=self._loop, daemon=True)
            self._worker.start()

    def _persist(self) -> None:
        """Atomically publish the latest state; process restarts never auto-resume it."""
        if self.evidence_dir:
            path = self.evidence_dir / "state.json"
            temporary = path.with_suffix(".tmp")
            temporary.write_text(json.dumps(self.snapshot(), allow_nan=False))
            temporary.replace(path)

    def _loop(self) -> None:
        """Advance on a server-owned clock independently of browser polls."""
        try:
            while not self._stop.wait(.08):
                with self.lock:
                    if self.closed:
                        return
                    if not self.running and time.monotonic() - self.touched > 300:
                        self.closed = True
                        self.phase = "expired"
                        self._persist()
                        return
                    self.tick(.08)
        except Exception as error:
            with self.lock:
                if self.graph.active:
                    self.graph.finish({"passed": False, "reason": str(error)})
                self.error = str(error)
                self.running = False
                self.phase = "failed"
                if self.simulation:
                    self.simulation.running = False
                self._persist()

    def start(self, *, agent_key: str | None = None) -> dict[str, Any]:
        """Start or resume dispatch; a terminal execution requires a new session."""
        with self.lock:
            if self.closed or self.phase in {"completed", "blocked", "failed"}:
                raise ValueError("Execution is terminal; create a new execution to retry")
            if agent_key is not None:
                if self.started:
                    raise ValueError("Choose agent control before starting a new execution")
                if self.evidence_dir is None:
                    raise ValueError("Agent control requires an attached evidence directory")
                self._agent_key = agent_key
            self.started = True
            self.running = True
            if self.graph.active and self.simulation and self.simulation.phase not in {"idle", "completed", "failed"}:
                self.simulation.running = True
            self._persist()
            return self.snapshot()

    def pause(self, paused: bool) -> dict[str, Any]:
        """Pause both scheduling and physics without resetting either."""
        with self.lock:
            if not paused:
                return self.start()
            self.running = False
            if self.simulation:
                self.simulation.running = False
            self._persist()
            return self.snapshot()

    def tick(self, seconds: float = .08) -> dict[str, Any]:
        """Dispatch and verify skills against live state, preserving all bodies."""
        with self.lock:
            if not self.running or self.closed:
                return self.snapshot()
            if self.graph.active is None:
                task = self.graph.next_task()
                if task is None:
                    states = [s["status"] for s in self.graph.states.values()]
                    self.phase = "completed" if all(s == "succeeded" for s in states) else "blocked"
                    self.running = False
                    self._persist()
                    return self.snapshot()
                self.simulation.bind_task(task)
                self.events.append({"event": "task_started", "task_id": task["id"]})
                if self._agent_key:
                    from robot_agent import start_agent
                    task_index = next(i for i, t in enumerate(self.graph.tasks) if t["id"] == task["id"])
                    self._agent_thread = start_agent(self.simulation, f"{self.evidence_dir.name}/task-{task_index:03d}", self._agent_key)
                else:
                    self.simulation.command({"action": "pick_place", "object_id": task["object_id"],
                                             "target_id": task["target"]["id"], "reason": "Dependencies satisfied; dispatch validated skill"})
            state = self.simulation.tick(seconds)
            self.phase = state["phase"]
            if self._agent_thread is not None:
                # Do not rebind the shared world while an agent is still observing,
                # retrying or writing its final evidence for the current task.
                if self._agent_thread.is_alive():
                    if not state["running"]:
                        self.phase = "awaiting_agent"
                    self._persist()
                    return self.snapshot()
                result = state["result"] if state["agent_status"] == "verified by agent" else {
                    "passed": False, "reason": state["agent_status"], "physics_result": state["result"]}
                self.phase = "completed" if result and result.get("passed") else "failed"
                self._agent_thread = None
            else:
                result = state["result"]
            if self.phase in {"completed", "failed"}:
                self.events.append({"event": "task_finished", "task_id": self.graph.active, "result": result})
                self.graph.finish(result or {"passed": False, "reason": "No verified result"})
                self.phase = "dispatching"
            self._persist()
            return self.snapshot()

    def snapshot(self) -> dict[str, Any]:
        """Return read-only task and physics state for any number of viewers."""
        with self.lock:
            state = self.simulation.snapshot() if self.simulation else {
                "mode": "robot", "engine": "MuJoCo", "step_id": None, "time_s": 0., "steps": 0,
                "contacts": 0, "objects": [], "robot_geoms": [], "joints": [], "actuators": 0,
                "result": None, "captured_images": [], "events": [], "physical_execution_verified": False,
            }
            return {**state, "execution": "task_graph", "phase": self.phase, "running": self.running,
                    "started": self.started, "closed": self.closed, "tasks": self.graph.snapshot(),
                    "active_task_id": self.graph.active, "error": self.error,
                    "events": [*self.events, *state["events"]][-60:],
                    "control": "managed_agent" if self._agent_key else "skill_dispatcher",
                    "agent_status": state.get("agent_status", "not requested") if self._agent_key else "task dispatcher", "evidence_id": self.evidence_dir.name if self.evidence_dir else None,
                    "scope": "Supported simulation skills only; unsupported observed tasks prevent full completion"}

    def close(self) -> None:
        """Stop the worker and persist cancellation without claiming task success."""
        self._stop.set()
        with self.lock:
            if self.graph.active:
                self.graph.finish({"passed": False, "reason": "Execution cancelled"})
            self.closed = True
            self.running = False
            if self.simulation:
                self.simulation.running = False
                self.simulation.closed = True
            if self.phase not in {"completed", "blocked", "failed", "expired"}:
                self.phase = "cancelled"
            self._persist()
        if self._worker and self._worker is not threading.current_thread():
            self._worker.join(timeout=2)
