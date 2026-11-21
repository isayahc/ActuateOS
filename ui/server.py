#!/usr/bin/env python3
"""Local dashboard for Video-to-Workcell. Run: python3 ui/server.py"""

import argparse
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import re
import shlex
import subprocess
import sys
import threading
from uuid import uuid4
from urllib.parse import urlparse


ROOT = Path(__file__).resolve().parents[1]
UI = Path(__file__).parent
ARTIFACTS = ROOT / "artifacts"
DATA = ROOT / "data" / "industreal"
KINDS = {"workcell-trials": "Workcell planning", "managed-agents": "Runtime smoke test"}
active = None
lock = threading.Lock()

os.environ.setdefault("MUJOCO_GL","egl")
os.environ.setdefault("EGL_PLATFORM","surfaceless")
try:
    from mujoco_runtime import runtime
except ImportError:
    runtime = None


def credentials():
    env = os.environ.copy()
    path = ROOT / ".env"
    if path.exists():
        for line in path.read_text().splitlines():
            line = line.strip().removeprefix("export ")
            key, separator, value = line.partition("=")
            if separator and key.strip() in {"GEMINI_API_KEY", "GOOGLE_API_KEY"}:
                values = shlex.split(value, comments=True)
                if values:
                    env.setdefault(key.strip(), values[0])
    return env


def load_json(path):
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return None


def display_response(value):
    """Opaque API signatures are replay metadata, not useful display content."""
    if isinstance(value, dict):
        return {key: display_response(item) for key, item in value.items() if key != "signature"}
    if isinstance(value, list):
        return [display_response(item) for item in value]
    return value


def run_detail(kind, run_id):
    if kind not in KINDS or not re.fullmatch(r"[0-9a-f]{32}", run_id):
        raise ValueError("Unknown run")
    folder = ARTIFACTS / kind / run_id
    if not folder.is_dir():
        raise ValueError("Unknown run")
    files = {name: load_json(folder / name) for name in (
        "task.json", "plan.json", "validation.json", "verified-result.json", "turn-1.json", "turn-2.json"
    )}
    report = files["validation.json"]
    verified = files["verified-result.json"]
    turns = [files[name] for name in ("turn-1.json", "turn-2.json") if files[name]]
    status = "incomplete"
    if report is not None:
        status = "passed" if report.get("passed") else "failed"
    elif verified is not None:
        status = "passed"
    elif any(t.get("status") in {"failed", "cancelled"} for t in turns):
        status = "failed"
    with lock:
        job = dict(active) if active and active.get("run_id") == run_id else None
        if job:
            job["logs"] = list(job["logs"])
    if job and job["running"]:
        status = "running"
    elif job and job.get("exit_code") != 0:
        status = "failed"
    return {
        "id": run_id, "kind": kind, "label": KINDS[kind], "status": status,
        "created": datetime.fromtimestamp(folder.stat().st_mtime, timezone.utc).isoformat(),
        "task": files["task.json"], "plan": files["plan.json"], "validation": report,
        "verified_result": verified, "turns": display_response(turns),
        "logs": job["logs"] if job else [],
        "artifact_path": str(folder.relative_to(ROOT)),
    }


def collect_runs():
    rows = []
    for kind in KINDS:
        for folder in (ARTIFACTS / kind).glob("*"):
            if folder.is_dir() and re.fullmatch(r"[0-9a-f]{32}", folder.name):
                item = run_detail(kind, folder.name)
                rows.append({k: item[k] for k in ("id", "kind", "label", "status", "created")})
    return sorted(rows, key=lambda r: r["created"], reverse=True)


def launch(video=False):
    global active
    with lock:
        if active and active["running"]:
            raise RuntimeError("A trial is already running.")
        env = credentials()
        if not (env.get("GEMINI_API_KEY") or env.get("GOOGLE_API_KEY")):
            raise ValueError("Add GEMINI_API_KEY to the repository .env file first.")
        run_id = uuid4().hex if video else None
        if video:
            if not (DATA / "provenance.json").exists() or not (DATA / "geometry.json").exists():
                raise ValueError("Run scripts/prepare_industreal.py and scripts/prepare_geometry.py first.")
            if not (UI / "dist" / "compile-scene.mjs").exists():
                raise ValueError("Run npm run setup:renderer and npm run build first.")
            folder = ARTIFACTS / "video-workcells" / run_id
            folder.mkdir(parents=True)
            (folder / "status.json").write_text(json.dumps({"id": run_id, "phase": "starting", "message": "Preparing video analysis…"}))
        command = [sys.executable, "-u", str(ROOT / "scripts" / "video_pipeline.py"), run_id] if video else [sys.executable, "-u", str(ROOT / "examples" / "workcell_trial.py")]
        process = subprocess.Popen(
            command,
            cwd=ROOT, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
        )
        active = {"running": True, "run_id": run_id, "kind": "video-workcells" if video else "workcell-trials", "logs": [], "exit_code": None}
        job = active

    def capture():
        for line in process.stdout:
            line = line.rstrip()
            for name in ("GEMINI_API_KEY", "GOOGLE_API_KEY"):
                if env.get(name):
                    line = line.replace(env[name], "[REDACTED]")
            with lock:
                job["logs"].append(line)
                if line.startswith("Artifacts: "):
                    job["run_id"] = Path(line.removeprefix("Artifacts: ")).name
        code = process.wait()
        with lock:
            job["running"] = False
            job["exit_code"] = code

    threading.Thread(target=capture, daemon=True).start()
    return run_id


class Handler(BaseHTTPRequestHandler):
    def file(self, path, mime):
        if not path.is_file():
            return self.respond(404, {"error": "File not available"})
        size = path.stat().st_size
        start, end = 0, size - 1
        header = self.headers.get("Range")
        if header:
            match = re.fullmatch(r"bytes=(\d*)-(\d*)", header)
            if not match or not any(match.groups()):
                return self.respond(416, {"error": "Invalid byte range"})
            if match[1]:
                start = int(match[1]); end = min(end, int(match[2])) if match[2] else end
            else:
                start = max(0, size-int(match[2]))
            if start > end or start >= size:
                return self.respond(416, {"error": "Byte range outside file"})
        self.send_response(206 if header else 200)
        self.send_header("Content-Type", mime)
        self.send_header("Content-Length", str(end-start+1))
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Cache-Control", "no-cache")
        if header:
            self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        self.end_headers()
        try:
            with path.open("rb") as handle:
                handle.seek(start)
                remaining = end-start+1
                while remaining:
                    chunk = handle.read(min(256*1024, remaining))
                    if not chunk: break
                    self.wfile.write(chunk); remaining -= len(chunk)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def respond(self, status, body, content_type="application/json"):
        data = json.dumps(body).encode() if content_type == "application/json" else body
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        path = urlparse(self.path).path
        match=re.fullmatch(r"/media/robot/([0-9a-f]{32})/(before\.png|after-[12]\.png|final\.json|initial-state\.json|model\.xml|trajectory\.jsonl)",path)
        if match:
            return self.file(ARTIFACTS/"robot-executions"/match[1]/match[2],"image/png" if match[2].endswith("png") else "application/xml" if match[2].endswith("xml") else "application/json")
        if path == "/api/runtime":
            return self.respond(200,{"available":runtime is not None,"engine":"MuJoCo",
                "message":"Ready" if runtime else "Start the server with .venv-mujoco/bin/python ui/server.py"})
        if path == "/api/benchmark":
            return self.respond(200, {"provenance": load_json(DATA / "provenance.json"),
                "catalog": load_json(DATA / "geometry-catalog.json"),
                "video_url": "/media/industreal.mp4", "recording": "03_assy_0_1",
                "duration_s": 275.4, "sample_count": 48})
        if path == "/api/video-runs":
            rows=[]
            for folder in (ARTIFACTS / "video-workcells").glob("*"):
                if folder.is_dir() and re.fullmatch(r"[0-9a-f]{32}", folder.name):
                    item=load_json(folder / "status.json")
                    if item:
                        item["created"]=folder.stat().st_ctime
                        rows.append(item)
            return self.respond(200, {"runs": sorted(rows,key=lambda r:r["created"],reverse=True)})
        match=re.fullmatch(r"/api/video-runs/([0-9a-f]{32})(/scene)?",path)
        if match:
            folder=ARTIFACTS / "video-workcells" / match[1]
            if not folder.is_dir():return self.respond(404,{"error":"Unknown run"})
            segmented=(folder / "segments.json").exists()
            if match[2]:return self.file(folder / ("segmented-workcell.oi.json" if segmented else "workcell.oi.json"),"application/json")
            response={name:load_json(folder / filename) for name,filename in {
                "status":"status.json","analysis":"analysis.json","scene_spec":"segmented-scene-spec.json" if segmented else "scene-spec.json",
                "validation":"validation.json","comparison":"comparison.json","frames":"frames.json",
                "segments":"segments.json","segments_status":"segments-status.json","segment_comparison":"segment-comparison.json",
                "comparison_status":"comparison-status.json","segment_evidence":"segment-evidence.json"}.items()}
            return self.respond(200,response)
        match=re.fullmatch(r"/api/video-runs/([0-9a-f]{32})/segments/([a-zA-Z0-9_-]+)/scene",path)
        if match:
            folder=ARTIFACTS / "video-workcells" / match[1]
            segments=load_json(folder / "segments.json")
            segment=next((s for s in (segments or {}).get("segments",[]) if s["step_id"]==match[2]),None)
            if not segment:return self.respond(404,{"error":"Unknown scene segment"})
            manifest=load_json(folder / "segmented-workcell.oi.json")
            return self.respond(200,{**manifest,"instances":segment["instances"],"animation":segment["animation"]})
        match=re.fullmatch(r"/media/segment-evidence/([0-9a-f]{32})/([a-zA-Z0-9_-]+\.(?:jpg|png))",path)
        if match:
            return self.file(ARTIFACTS / "video-workcells" / match[1] / "segment-evidence" / match[2],"image/png" if match[2].endswith(".png") else "image/jpeg")
        if path == "/media/industreal.mp4":
            return self.file(DATA / "03_assy_0_1.browser.mp4", "video/mp4")
        match=re.fullmatch(r"/media/frames/([0-9a-f]{32})/(frame-\d{2}\.jpg)",path)
        if match:
            return self.file(ARTIFACTS / "video-workcells" / match[1] / match[2], "image/jpeg")
        if path == "/scene-viewer.js":
            return self.file(UI / "dist" / "scene-viewer.js", "text/javascript")
        if path == "/api/runs":
            with lock:
                job = dict(active) if active else None
                if job:
                    job["logs"] = list(job["logs"])
            return self.respond(200, {"runs": collect_runs(), "active": job})
        if path.startswith("/api/runs/"):
            parts = path.split("/")
            try:
                if len(parts) != 5:
                    raise ValueError("Unknown run")
                return self.respond(200, run_detail(parts[3], parts[4]))
            except ValueError as error:
                return self.respond(404, {"error": str(error)})
        assets = {"/": ("video.html", "text/html; charset=utf-8"),
                  "/runs": ("index.html", "text/html; charset=utf-8"),
                  "/video.js": ("video.js", "text/javascript; charset=utf-8"),
                  "/video.css": ("video.css", "text/css; charset=utf-8"),
                  "/scene-capture": ("capture.html", "text/html; charset=utf-8"),
                  "/capture.js": ("capture.js", "text/javascript; charset=utf-8"),
                  "/app.js": ("app.js", "text/javascript; charset=utf-8"),
                  "/style.css": ("style.css", "text/css; charset=utf-8")}
        if path in assets:
            name, mime = assets[path]
            return self.respond(200, (UI / name).read_bytes(), mime)
        self.respond(404, {"error": "Not found"})

    def do_POST(self):
        # Only the local dashboard can initiate paid API runs.
        expected_origin = f"http://{self.headers.get('Host')}"
        if self.headers.get("Origin") != expected_origin or self.headers.get("Content-Type") != "application/json":
            return self.respond(403, {"error": "Use the local dashboard to start a run."})
        if self.path.startswith("/api/runtime/"):
            if runtime is None:return self.respond(503,{"error":"MuJoCo unavailable. Use .venv-mujoco/bin/python ui/server.py"})
            try:
                length=int(self.headers.get("Content-Length","0"))
                if not 0<length<=4096:raise ValueError("Invalid runtime request size")
                data=json.loads(self.rfile.read(length))
                if not isinstance(data,dict):raise ValueError("Expected JSON object")
                if self.path=="/api/runtime/connect":
                    run_id=data.get("run_id","");step_id=data.get("step_id","")
                    if not isinstance(run_id,str) or not re.fullmatch(r"[0-9a-f]{32}",run_id):raise ValueError("Invalid run")
                    if not isinstance(step_id,str):raise ValueError("Invalid step")
                    return self.respond(200,runtime.create(ARTIFACTS/"video-workcells"/run_id,step_id,data.get("mode","mujoco")))
                sid=data.get("session_id")
                if not isinstance(sid,str):raise ValueError("Invalid session")
                if self.path=="/api/runtime/close":
                    runtime.close(sid);return self.respond(200,{"closed":True})
                if self.path=="/api/runtime/advance":
                    simulation=runtime.get(sid)
                    if not hasattr(simulation,"advance"):raise ValueError("Robot uses its own execution clock, not video seeking")
                    return self.respond(200,simulation.advance(data.get("time_s")))
                if self.path in ("/api/runtime/robot-tick","/api/runtime/robot-agent","/api/runtime/robot-pause","/api/runtime/robot-perturb"):
                    simulation=runtime.get(sid)
                    if not hasattr(simulation,"observe"):raise ValueError("Connect the live robot runtime first")
                    if self.path.endswith("robot-tick"):return self.respond(200,simulation.tick())
                    if self.path.endswith("robot-perturb"):return self.respond(200,simulation.perturb(data.get("dx"),data.get("dz")))
                    if self.path.endswith("robot-pause"):
                        if type(data.get("paused")) is not bool:raise ValueError("Expected paused boolean")
                        with simulation.lock:
                            if simulation.phase not in ("idle","completed","failed"):simulation.running=not data["paused"]
                            return self.respond(200,simulation.snapshot())
                    from robot_agent import start_agent
                    env=credentials();key=env.get("GEMINI_API_KEY") or env.get("GOOGLE_API_KEY")
                    if not key:raise ValueError("Set GEMINI_API_KEY to request live agent decisions")
                    start_agent(simulation,sid,key)
                    return self.respond(202,simulation.snapshot())
                return self.respond(404,{"error":"Unknown runtime action"})
            except (ValueError,RuntimeError,OSError,KeyError) as error:
                return self.respond(409,{"error":str(error)})
        if self.path not in {"/api/run", "/api/video-run"}:
            return self.respond(404, {"error": "Not found"})
        try:
            run_id = launch(video=self.path == "/api/video-run")
            self.respond(202, {"started": True, "id": run_id})
        except (RuntimeError, ValueError, OSError) as error:
            self.respond(409, {"error": str(error)})

    def log_message(self, *_):
        pass


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=5187)
    args = parser.parse_args()
    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    print(f"Video-to-Workcell dashboard: http://127.0.0.1:{args.port}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.server_close()
