#!/usr/bin/env python3
"""Run the real managed-agent robot milestone headlessly, saving live evidence."""
import argparse
import os
import re
from pathlib import Path
import sys
import time
from uuid import uuid4

os.environ.setdefault("MUJOCO_GL","egl")
os.environ.setdefault("EGL_PLATFORM","surfaceless")
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"ui"))
from robot_runtime import RobotSimulation
from robot_agent import start_agent

parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument("run_id");parser.add_argument("--dx",type=float,default=0);parser.add_argument("--dz",type=float,default=0)
args=parser.parse_args()
if not re.fullmatch(r"[0-9a-f]{32}",args.run_id):parser.error("Invalid run ID")
key=os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
if not key:parser.error("Set GEMINI_API_KEY")
simulation=RobotSimulation(ROOT/"artifacts/video-workcells"/args.run_id,"step_1")
simulation.perturb(args.dx,args.dz)
sid=uuid4().hex;print(f"Robot evidence: artifacts/robot-executions/{sid}",flush=True)
start_agent(simulation,sid,key)
last=None;deadline=time.monotonic()+1800
while time.monotonic()<deadline:
    state=simulation.tick(.08)
    status=(state["agent_status"],state["phase"])
    if status!=last:print(status,state["result"],flush=True);last=status
    if state["agent_status"] in ("verified by agent","agent reported failure","agent error","decision budget exhausted"):
        # Let the agent thread finish writing its final artifact.
        time.sleep(.3)
        if state["agent_status"]!="verified by agent":raise SystemExit(1)
        break
    time.sleep(.08 if state["running"] else .2)
else:raise SystemExit("Timed out; interaction evidence retained")
