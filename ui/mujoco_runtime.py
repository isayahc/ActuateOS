"""Live MuJoCo adapter for compiled OI workcells (Y-up throughout).

Free workpiece bodies follow compliant mocap weld guides. Contacts/gravity are
solved by mj_step; this is guided assembly, not an articulated robot controller.
Original print sets stay visual-only in OI; proposed meshes are convex colliders.
"""
import json
import math
import threading
import time
import xml.etree.ElementTree as ET
from uuid import uuid4
from pathlib import Path
from typing import Any

import mujoco
import numpy as np


def numbers(values):
    return " ".join(str(float(v)) for v in values)


def quaternion(degrees):
    # Matches THREE.Euler XYZ (intrinsic), not MJCF's default Euler convention.
    x,y,z=np.radians(degrees)/2
    c1,c2,c3=np.cos([x,y,z]);s1,s2,s3=np.sin([x,y,z])
    return np.array([c1*c2*c3-s1*s2*s3,s1*c2*c3+c1*s2*s3,c1*s2*c3-s1*c2*s3,c1*c2*s3+s1*s2*c3])


class Simulation:
    def __init__(self, folder, step_id):
        manifest=json.loads((folder/"segmented-workcell.oi.json").read_text())
        segments=json.loads((folder/"segments.json").read_text())["segments"]
        self.segment=next((s for s in segments if s["step_id"]==step_id),None)
        if self.segment is None:raise ValueError("Unknown segment")
        spec=json.loads((folder/"segmented-scene-spec.json").read_text())
        self.source_kind={o["id"]:o["kind"] for o in spec["objects"]}
        self.moving={p["id"] for p in self.segment["before_poses"]}
        self.instances=self.segment["instances"]
        self.tracks={t["instanceId"]:t["keys"] for t in self.segment["animation"]["tracks"]}
        assets={a["id"]:a for a in manifest["bundledAssets"]}
        root=ET.Element("mujoco",model="OI guided assembly")
        ET.SubElement(root,"compiler",angle="radian")
        ET.SubElement(root,"option",timestep="0.005",gravity="0 -9.81 0",integrator="implicitfast",iterations="40")
        asset=ET.SubElement(root,"asset");world=ET.SubElement(root,"worldbody");eq=ET.SubElement(root,"equality")
        ET.SubElement(world,"geom",name="ground",type="plane",size="10 10 .1",quat=".70710678 -.70710678 0 0",friction=".7 .01 .001")
        self.names={};self.geom_names={}
        for i,item in enumerate(self.instances):
            oid=item["id"];name=f"object_{i}";self.names[oid]=name
            if self.source_kind[oid]=="dataset":continue
            pos=item["position"] if item["visible"] else [i*.3,-10,0]
            quat=quaternion(item["rotation"])
            body=ET.SubElement(world,"body",name=name,pos=numbers(pos),quat=numbers(quat))
            if oid in self.moving:
                ET.SubElement(body,"freejoint",name=f"joint_{i}")
                ET.SubElement(world,"body",name=f"guide_{i}",mocap="true",pos=numbers(pos),quat=numbers(quat))
                ET.SubElement(eq,"weld",name=f"weld_{i}",body1=f"guide_{i}",body2=name,solref=".03 1")
            self.geom_names[oid]=[]
            for j,part in enumerate(assets[item["assetId"]]["parts"]):
                mesh=f"mesh_{i}_{j}";geom=f"geom_{i}_{j}"
                ET.SubElement(asset,"mesh",name=mesh,vertex=numbers(part["vertices"]),face=" ".join(map(str,part["indices"])))
                ET.SubElement(body,"geom",name=geom,type="mesh",mesh=mesh,density="500",friction=".6 .01 .001",rgba=numbers([*part["color"],1]))
                self.geom_names[oid].append(geom)
        self.xml=ET.tostring(root,encoding="unicode")
        self.model=mujoco.MjModel.from_xml_string(self.xml)
        self.data=mujoco.MjData(self.model)
        self.bodies={oid:self.model.body(name).id for oid,name in self.names.items() if self.source_kind[oid]!="dataset"}
        self.guides={oid:int(self.model.body(f"guide_{i}").mocapid[0]) for i,item in enumerate(self.instances) if (oid:=item["id"]) in self.moving}
        self.visible={};self.steps=0;self.resets=0;self.lock=threading.Lock();self.touched=time.monotonic()
        self.reset()

    def target(self,item,t):
        keys=self.tracks.get(item["id"])
        if not keys:return item
        before=keys[0];after=keys[-1]
        for key in keys[1:]:
            if key["time"]>t:after=key;break
            before=key
        f=max(0,min(1,(t-before["time"])/max(1e-9,after["time"]-before["time"])))
        return {"position":np.array(before["position"])*(1-f)+np.array(after["position"])*f,
                "rotation":np.array(before["rotation"])*(1-f)+np.array(after["rotation"])*f,"visible":before["visible"]}

    def guide(self,t):
        for i,item in enumerate(self.instances):
            oid=item["id"]
            if oid not in self.moving:continue
            target=self.target(item,t);visible=target["visible"]
            pos=target["position"] if visible else [i*.3,-10,0]
            quat=quaternion(target["rotation"]);mid=self.guides[oid]
            self.data.mocap_pos[mid]=pos;self.data.mocap_quat[mid]=quat
            # Only visibility transitions initialize a body. All subsequent movement
            # is dynamics integration, never assigned reference positions.
            if self.visible.get(oid)!=visible:
                body=self.bodies[oid];joint=self.model.body_jntadr[body]
                q=self.model.jnt_qposadr[joint];v=self.model.jnt_dofadr[joint]
                self.data.qpos[q:q+3]=pos;self.data.qpos[q+3:q+7]=quat;self.data.qvel[v:v+6]=0
                for name in self.geom_names[oid]:
                    gid=self.model.geom(name).id
                    self.model.geom_contype[gid]=int(visible);self.model.geom_conaffinity[gid]=int(visible)
            self.visible[oid]=visible

    def reset(self):
        mujoco.mj_resetData(self.model,self.data)
        self.visible={};self.steps=0;self.resets+=1
        self.guide(0);mujoco.mj_forward(self.model,self.data)

    def advance(self,target_s):
        if type(target_s) not in (int,float) or not math.isfinite(target_s) or not 0<=target_s<=self.segment["duration_s"]+.001:
            raise ValueError("Simulation time outside selected segment")
        with self.lock:
            self.touched=time.monotonic()
            desired=int(round(target_s/self.model.opt.timestep))
            if desired<self.steps:self.reset()
            while self.steps<desired:
                self.guide((self.steps+1)*self.model.opt.timestep)
                mujoco.mj_step(self.model,self.data);self.steps+=1
            mujoco.mj_forward(self.model,self.data)
            if not np.isfinite(self.data.qpos).all() or any(w.number for w in self.data.warning):
                raise RuntimeError("MuJoCo reported unstable dynamics; inspect model and controller")
            return self.snapshot()

    def snapshot(self):
        objects=[];errors=[]
        for item in self.instances:
            oid=item["id"]
            if oid in self.bodies:
                body=self.bodies[oid];pos=self.data.xpos[body];quat=self.data.xquat[body]
            else:pos=item["position"];quat=quaternion(item["rotation"])
            objects.append({"id":oid,"position":list(pos),"quaternion":[quat[1],quat[2],quat[3],quat[0]],"visible":self.visible.get(oid,item["visible"])})
            if oid in self.moving and self.visible[oid]:errors.append(float(np.linalg.norm(pos-self.target(item,self.data.time)["position"])))
        return {"engine":"MuJoCo","version":mujoco.__version__,"step_id":self.segment["step_id"],"time_s":float(self.data.time),
                "steps":self.steps,"resets":self.resets,"contacts":self.data.ncon,"max_tracking_error_m":max(errors,default=0),
                "objects":objects,"control":"compliant mocap weld guides; no articulated robot controller",
                "collision_geometry":"convex hull per proposed OI mesh part; dataset print sets visual-only",
                "physical_execution_verified":False}


class Runtime:
    """Own live execution sessions separately from reference playback sessions."""

    def __init__(self) -> None:
        """Initialize the session registry and creation lock."""
        self.sessions: dict[str, Any] = {}
        self.lock = threading.Lock()

    def create(self, folder: Path, step_id: str, mode: str = "mujoco") -> dict[str, Any]:
        """Reconnect to a run's task execution, or initialize legacy guided playback."""
        with self.lock:
            for sid, existing in self.sessions.items():
                if mode == "robot" and hasattr(existing, "graph") and existing.folder == folder and not existing.closed:
                    existing.touched = time.monotonic()
                    return {"session_id": sid, **existing.snapshot()}
            expired = [sid for sid, value in self.sessions.items()
                       if getattr(value, "closed", False) or (not getattr(value, "running", False) and time.monotonic()-value.touched > 300)]
            for sid in expired:
                value = self.sessions.pop(sid)
                if hasattr(value, "close"): value.close()
            if len(self.sessions) >= 12:
                raise ValueError("Too many runtime sessions; close an unused execution")
            if mode == "robot":
                from task_runtime import TaskExecution
                simulation = TaskExecution(folder)
            elif mode == "mujoco":
                simulation = Simulation(folder, step_id)
            else:
                raise ValueError("Unknown runtime mode")
            sid = uuid4().hex
            if mode == "robot":
                simulation.attach(folder.parents[1] / "robot-executions" / sid)
            self.sessions[sid] = simulation
            return {"session_id": sid, **simulation.snapshot()}

    def get(self, sid: str) -> Any:
        """Retrieve a session and update viewer activity, never its simulation clock."""
        with self.lock:
            if sid not in self.sessions or getattr(self.sessions[sid], "closed", False):
                raise ValueError("Runtime session expired; reconnect")
            simulation = self.sessions[sid]
            simulation.touched = time.monotonic()
            return simulation

    def close(self, sid: str) -> None:
        """Cancel an execution and release its worker."""
        with self.lock:
            simulation = self.sessions.pop(sid, None)
        if simulation is not None:
            if hasattr(simulation, "close"): simulation.close()
            else: simulation.closed = True

    def shutdown(self) -> None:
        """Stop every task worker when the HTTP server shuts down."""
        for sid in list(self.sessions):
            self.close(sid)


runtime=Runtime()
