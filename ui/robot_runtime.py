"""Online joint-space planning and contact-only manipulation in the IndustReal cell.

No storyboard tracks, object pose controller, mocap bodies or grasp welds are used.
Tasks bind scene objects and targets explicitly; animation tracks are never executed.
"""
import hashlib
import json
import struct
import threading
import time
import xml.etree.ElementTree as ET
import zlib
from pathlib import Path
from typing import Any

import mujoco
import numpy as np

from mujoco_runtime import numbers, quaternion


class RobotSimulation:
    """Execute bounded scene-bound manipulation with live joints and contact checks."""
    def __init__(self, folder: Path, task: dict[str, Any], plan: dict[str, Any]) -> None:
        """Build one persistent scene with all bound workpieces as free bodies."""
        step_id = task["step_id"]
        self.task = task
        self.plan_spec = plan
        self.robot_id = plan["robot_id"]
        self.movable_ids = {t["object_id"] for t in plan["tasks"] if t["skill"] == "pick_place"}
        self.folder=folder;self.step_id=step_id
        self.video_reference=next(s for s in json.loads((folder/"analysis.json").read_text())["steps"] if s["id"]==step_id)
        manifest=json.loads((folder/"segmented-workcell.oi.json").read_text())
        spec=json.loads((folder/"segmented-scene-spec.json").read_text())
        initial=plan.get("initial_positions", {})
        self.instances=manifest["instances"];self.kinds={o["id"]:o["kind"] for o in spec["objects"]}
        definitions={o["id"]:o for o in spec["objects"]}
        self.object_id=task["object_id"]
        self.source=np.array(initial.get(self.object_id, next(i["position"] for i in manifest["instances"] if i["id"]==self.object_id)),float)
        self.goal=np.array(task["target"]["position"],float)
        self.assets={a["id"]:a for a in manifest["bundledAssets"]}
        root=ET.Element("mujoco",model="Scene-bound task execution")
        ET.SubElement(root,"compiler",angle="radian")
        ET.SubElement(root,"option",timestep=".002",gravity="0 -9.81 0",integrator="implicitfast",iterations="80",cone="elliptic")
        defaults=ET.SubElement(root,"default")
        ET.SubElement(defaults,"geom",friction="1 .01 .001",solref=".008 1",condim="4")
        asset=ET.SubElement(root,"asset");world=ET.SubElement(root,"worldbody");act=ET.SubElement(root,"actuator")
        ET.SubElement(world,"light",pos="0 3 0",dir="0 -1 0",diffuse=".8 .8 .8")
        eye=self.source+np.array([1.5,1.,1.8]);z=eye-self.source;z/=np.linalg.norm(z)
        x=np.cross([0,1,0],z);x/=np.linalg.norm(x);y=np.cross(z,x)
        ET.SubElement(world,"camera",name="observation",pos=numbers(eye),xyaxes=numbers([*x,*y]),fovy="45")
        ET.SubElement(world,"geom",name="floor",type="plane",size="5 5 .1",quat=".70710678 -.70710678 0 0",rgba=".15 .2 .17 1")
        self.names={};self.visible={};self.workpiece_joints={};self.workpiece_geoms={}
        for i,item in enumerate(self.instances):
            oid=item["id"];self.visible[oid]=oid!=self.robot_id
            if self.kinds[oid]=="dataset" or oid==self.robot_id:continue
            self.visible[oid]=True
            pos=initial.get(oid,item["position"])
            name=f"object_{i}";self.names[oid]=name
            body=ET.SubElement(world,"body",name=name,pos=numbers(pos),quat=numbers(quaternion(item["rotation"])))
            if oid in self.movable_ids:
                self.workpiece_joints[oid]=f"workpiece_{i}"
                self.workpiece_geoms[oid]=[]
                ET.SubElement(body,"freejoint",name=self.workpiece_joints[oid])
            for j,part in enumerate(self.assets[item["assetId"]]["parts"]):
                mesh=f"mesh_{i}_{j}";geom=f"geom_{i}_{j}"
                ET.SubElement(asset,"mesh",name=mesh,vertex=numbers(part["vertices"]),face=" ".join(map(str,part["indices"])))
                definition=definitions[oid]["parts"][j]
                if definition["shape"]=="box" and not any(definition["rotation"]):
                    vertices=np.array(part["vertices"]).reshape(-1,3);low=vertices.min(axis=0);high=vertices.max(axis=0)
                    ET.SubElement(body,"geom",name=geom,type="box",size=numbers((high-low)/2),pos=numbers((high+low)/2),density="500",rgba=numbers([*part["color"],1]))
                else:
                    ET.SubElement(body,"geom",name=geom,type="mesh",mesh=mesh,density="500",rgba=numbers([*part["color"],1]),
                                  contype="0" if oid==self.object_id else "1",conaffinity="0" if oid==self.object_id else "1")
                if oid in self.movable_ids:self.workpiece_geoms[oid].append(geom)
        base=next(o for o in self.instances if o["id"]==self.robot_id)["position"]
        pedestal=ET.SubElement(world,"body",name="robot_base",pos=numbers(base))
        ET.SubElement(pedestal,"geom",name="robot_pedestal",type="box",pos="0 .4 0",size=".11 .4 .11",rgba=".25 .28 .3 1")
        ET.SubElement(pedestal,"geom",name="robot_base_neck",type="box",pos="0 .925 0",size=".07 .125 .07",rgba=".35 .38 .4 1")
        self.robot_joint_names=[]
        def link(parent,name,pos,axis,limits,segment=None):
            body=ET.SubElement(parent,"body",name=name,pos=numbers(pos),gravcomp="1")
            ET.SubElement(body,"joint",name=name,type="hinge",axis=numbers(axis),range=numbers(limits),damping="8",armature=".05")
            ET.SubElement(body,"geom",name=f"robot_{name}_hub",type="sphere",size=".042",mass=".25",rgba=".9 .5 .15 1",contype="1",conaffinity="1")
            if segment:ET.SubElement(body,"geom",name=f"robot_{name}_link",type="capsule",fromto=numbers([0,0,0,*segment]),size=".026",mass=".6",rgba=".85 .88 .9 1")
            ET.SubElement(act,"position",name=name,joint=name,kp="700",kv="65",ctrlrange=numbers(limits),forcerange="-150 150")
            self.robot_joint_names.append(name)
            return body
        yaw=link(pedestal,"yaw",[0,1.05,0],[0,1,0],[-2.8,2.8])
        shoulder=link(yaw,"shoulder",[0,0,0],[1,0,0],[-2.4,2.4],[0,0,.65])
        elbow=link(shoulder,"elbow",[0,0,.65],[1,0,0],[-2.7,2.7],[0,0,.60])
        wrist=link(elbow,"wrist_pitch",[0,0,.60],[1,0,0],[-2.8,2.8])
        wrist=link(wrist,"wrist_roll",[0,0,0],[0,0,1],[-2.8,2.8])
        palm=link(wrist,"wrist_yaw",[0,0,0],[0,1,0],[-2.8,2.8])
        ET.SubElement(palm,"geom",name="robot_palm",type="box",pos="0 -.025 0",size=".065 .015 .025",mass=".2",rgba=".2 .25 .28 1")
        ET.SubElement(palm,"site",name="grasp",pos="0 -.075 0",size=".004")
        for sign,label in [(-1,"left"),(1,"right")]:
            finger=ET.SubElement(palm,"body",name=f"finger_{label}",pos=numbers([sign*.008,-.075,0]),gravcomp="1")
            ET.SubElement(finger,"joint",name=f"finger_{label}",type="slide",axis=numbers([sign,0,0]),range="0 .045",damping="2",armature=".002")
            ET.SubElement(finger,"geom",name=f"robot_finger_{label}",type="box",size=".006 .01 .022",mass=".06",rgba=".35 .4 .45 1",friction="2 .02 .002")
            ET.SubElement(act,"position",name=f"finger_{label}",joint=f"finger_{label}",kp="150",kv="5",ctrlrange="0 .045",forcerange="-12 12")
        # Co-located wrist axes belong to the same physical housing.
        contact=ET.SubElement(root,"contact")
        for a,b in [("robot_base","yaw"),("robot_base","shoulder"),("yaw","elbow"),("wrist_pitch","wrist_yaw"),("elbow","wrist_roll"),("elbow","wrist_yaw"),("wrist_pitch","finger_left"),("wrist_pitch","finger_right"),("wrist_roll","finger_left"),("wrist_roll","finger_right")]:
            ET.SubElement(contact,"exclude",body1=a,body2=b)
        self.xml=ET.tostring(root,encoding="unicode")
        self.model=mujoco.MjModel.from_xml_string(self.xml);self.data=mujoco.MjData(self.model)
        self.body_ids={oid:self.model.body(name).id for oid,name in self.names.items()}
        self.object_body=self.body_ids[self.object_id];self.site=self.model.site("grasp").id
        self.qadr=np.array([self.model.joint(n).qposadr[0] for n in self.robot_joint_names])
        self.dofs=np.array([self.model.joint(n).dofadr[0] for n in self.robot_joint_names])
        self.ranges=np.array([self.model.joint(n).range for n in self.robot_joint_names])
        self.robot_geom_ids=[i for i in range(self.model.ngeom) if (mujoco.mj_id2name(self.model,mujoco.mjtObj.mjOBJ_GEOM,i) or "").startswith("robot_")]
        self.object_geom_ids={self.model.geom(n).id for n in self.workpiece_geoms[self.object_id]}
        self.finger_geom_ids={self.model.geom(f"robot_finger_{s}").id for s in ("left","right")}
        self.lock=threading.RLock();self.touched=time.monotonic()
        self.phase="idle";self.running=False;self.steps=0;self.events=[];self.result=None;self.plan=None;self.attempts=0;self.agent_status="not requested";self.closed=False
        self.evidence_dir=None;self.captured_images=[]
        self.data.qpos[self.qadr]=[0,-1.2,2.0,-.8,0,0]
        self.data.qpos[[self.model.joint(f"finger_{s}").qposadr[0] for s in ("left","right")]]=.04
        self.data.ctrl[:6]=self.data.qpos[self.qadr];self.data.ctrl[6:]=.04
        self.seed=self.data.qpos[self.qadr].copy()
        mujoco.mj_forward(self.model,self.data)
        for _ in range(250):mujoco.mj_step(self.model,self.data)
        self.data.time=0;self.data.qvel[:]=0
        self.start_position=self.data.xpos[self.object_body].copy()
        self.bind_task(task)

    def bind_task(self, task: dict[str, Any]) -> None:
        """Select a new skill binding without resetting joints, workpieces or time."""
        self.task=task;self.step_id=task["step_id"];self.object_id=task["object_id"]
        self.video_reference=next(s for s in json.loads((self.folder/"analysis.json").read_text())["steps"] if s["id"]==self.step_id)
        self.object_body=self.body_ids[self.object_id]
        self.object_geom_ids={self.model.geom(n).id for n in self.workpiece_geoms[self.object_id]}
        vertices=np.array(self.assets[next(i["assetId"] for i in self.instances if i["id"]==self.object_id)]["parts"][0]["vertices"]).reshape(-1,3)
        self.object_size=vertices.max(axis=0)-vertices.min(axis=0)
        self.source=self.data.xpos[self.object_body].copy();self.start_position=self.source.copy()
        self.goal=np.array(task["target"]["position"],float)
        self.phase="idle";self.running=False;self.result=None;self.plan=None;self.attempts=0
        self.agent_status="not requested";self.captured_images=[]
        self.task_started=float(self.data.time)

    def observe(self):
        return {"source":"MuJoCo ground-truth poses, not visual pose estimation","step_id":self.step_id,
                "video_reference":self.video_reference,
                "task":self.task,
                "objects":[{"id":self.object_id,"position":self.data.xpos[self.object_body].tolist(),"size_m":self.object_size.tolist()}],
                "targets":[{"id":self.task["target"]["id"],"position":self.goal.tolist()}],
                "joints":self.data.qpos[self.qadr].tolist(),"phase":self.phase,"result":self.result,
                "allowed_actions":["pick_place","finish","report_failure"],"attempts":self.attempts}

    def perturb(self,dx,dz):
        with self.lock:
            if self.phase!="idle" or self.agent_status=="thinking":raise ValueError("Move the part before requesting a plan")
            if any(type(v) not in (int,float) or not np.isfinite(v) or abs(v)>.12 for v in (dx,dz)):raise ValueError("Part offsets must be within 12 cm")
            q=int(self.model.joint(self.workpiece_joints[self.object_id]).qposadr[0]);self.data.qpos[q]=self.source[0]+dx;self.data.qpos[q+2]=self.source[2]+dz
            mujoco.mj_forward(self.model,self.data)
            self.start_position=self.data.xpos[self.object_body].copy()
            self.events.append({"event":"operator_perturbation","position":self.start_position.tolist()})
            return self.snapshot()

    def ik(self,position,seed):
        scratch=mujoco.MjData(self.model);scratch.qpos[:]=self.data.qpos
        q=seed.copy();jp=np.zeros((3,self.model.nv));jr=jp.copy()
        for _ in range(140):
            scratch.qpos[self.qadr]=q;mujoco.mj_forward(self.model,scratch)
            rot=scratch.site_xmat[self.site].reshape(3,3)
            error_r=.5*sum((np.cross(rot[:,i],np.eye(3)[:,i]) for i in range(3)),np.zeros(3))
            error_p=np.array(position)-scratch.site_xpos[self.site]
            if np.linalg.norm(error_p)<.0015 and np.linalg.norm(error_r)<.015:return q
            mujoco.mj_jacSite(self.model,scratch,jp,jr,self.site)
            jac=np.vstack([jp[:,self.dofs],jr[:,self.dofs]*.4]);error=np.r_[error_p,error_r*.4]
            dq=jac.T@np.linalg.solve(jac@jac.T+np.eye(6)*.002,error)
            q=np.clip(q+np.clip(dq,-.12,.12),self.ranges[:,0]+.01,self.ranges[:,1]-.01)
        raise ValueError(f"IK could not reach target {np.round(position,3).tolist()}")

    def collision(self,q,allow_grasp=False):
        scratch=mujoco.MjData(self.model);scratch.qpos[:]=self.data.qpos;scratch.qpos[self.qadr]=q
        scratch.qpos[[self.model.joint(f"finger_{s}").qposadr[0] for s in ("left","right")]]=.04
        mujoco.mj_forward(self.model,scratch)
        if self.phase in ("lift","transfer","lower") and len(self.grasp_contacts())==2:
            # Predicted carried-object pose for collision checking only. Execution
            # never assigns this pose: friction contacts must actually carry it.
            current_rot=self.data.site_xmat[self.site].reshape(3,3)
            next_rot=scratch.site_xmat[self.site].reshape(3,3)
            relative=current_rot.T@(self.data.xpos[self.object_body]-self.data.site_xpos[self.site])
            qadr=int(self.model.joint(self.workpiece_joints[self.object_id]).qposadr[0])
            scratch.qpos[qadr:qadr+3]=scratch.site_xpos[self.site]+next_rot@relative
            rotation=next_rot@current_rot.T@self.data.xmat[self.object_body].reshape(3,3)
            mujoco.mju_mat2Quat(scratch.qpos[qadr+3:qadr+7],rotation.reshape(9))
            mujoco.mj_forward(self.model,scratch)
        for contact in scratch.contact:
            pair={int(contact.geom1),int(contact.geom2)}
            checked=set(self.robot_geom_ids)
            if self.phase in ("lift","transfer","lower"):checked.update(self.object_geom_ids)
            if not pair.intersection(checked) or contact.dist>=-.002:continue
            if allow_grasp and pair.intersection(self.object_geom_ids) and pair.intersection(self.finger_geom_ids):continue
            return True
        return False

    def plan_to(self,target,allow_grasp=False):
        # Plan fresh from measured joints; Cartesian samples are solved and collision
        # checked, then executed through actuators. No object keyframes are consulted.
        start=self.data.site_xpos[self.site].copy();q=self.data.qpos[self.qadr].copy();path=[q.copy()]
        for f in np.linspace(0,1,31)[1:]:
            q=self.ik(start*(1-f)+np.array(target)*f,q)
            if self.collision(q,allow_grasp):raise ValueError("Planned arm path intersects geometry")
            path.append(q.copy())
        self.plan=np.array(path);self.plan_started=self.data.time
        self.plan_duration=max(1.0,float(np.max(np.sum(np.abs(np.diff(self.plan,axis=0)),axis=0)))/.45)
        self.target=np.array(target)
        self.events.append({"event":"online_plan","phase":self.phase,"observed_part":self.data.xpos[self.object_body].tolist(),
                            "target":self.target.tolist(),"sha256":hashlib.sha256(self.plan.tobytes()).hexdigest(),"time_s":float(self.data.time)})

    def command(self,decision):
        with self.lock:
            action=decision.get("action")
            if action=="pick_place":
                if self.phase not in ("idle","failed") or self.attempts>=2:raise ValueError("Pick/place unavailable in current state")
                if decision.get("object_id")!=self.object_id or decision.get("target_id")!=self.task["target"]["id"]:raise ValueError("Unknown object/target")
                self.attempts+=1;self.result=None;self.start_position=self.data.xpos[self.object_body].copy()
                self.pick=self.start_position+np.array([0,self.object_size[1]/2,0]);self.lift_baseline=float(self.start_position[1])
                self.phase="approach";self.running=True;self.data.ctrl[6:]=.04
                try:self.plan_to(self.pick+[0,.18,0])
                except ValueError as error:self.fail(str(error))
            elif action=="finish":
                if not self.result or not self.result.get("passed"):raise ValueError("Completion requires measured placement success")
                self.agent_status="verified by agent"
            elif action=="report_failure":self.agent_status="agent reported failure";self.running=False
            else:raise ValueError("Unknown agent action")
            self.events.append({"event":"agent_decision","decision":decision})
            return self.snapshot()

    def fail(self,message):
        self.phase="failed";self.running=False;self.result={"passed":False,"reason":message}
        self.events.append({"event":"failure","reason":message,"time_s":float(self.data.time)})

    def grasp_contacts(self):
        return {int(c.geom1) if int(c.geom1) in self.finger_geom_ids else int(c.geom2) for c in self.data.contact
                if {int(c.geom1),int(c.geom2)}.intersection(self.object_geom_ids) and {int(c.geom1),int(c.geom2)}.intersection(self.finger_geom_ids)}

    def next_phase(self):
        if self.phase=="approach":
            # Reobserve immediately before descent, allowing a changed source pose.
            self.pick=self.data.xpos[self.object_body].copy()+[0,self.object_size[1]/2,0]
            self.phase="descend";self.plan_to(self.pick,True)
        elif self.phase=="descend":
            self.phase="close";self.plan=None;self.data.ctrl[6:]=0;self.phase_started=self.data.time
        elif self.phase=="lift":
            rise=float(self.data.xpos[self.object_body][1]-self.lift_baseline)
            if rise<.07 or len(self.grasp_contacts())<2:return self.fail("Grasp did not retain the part during lift")
            self.events.append({"event":"grasp_verified","rise_m":rise,"finger_contacts":2})
            self.phase="transfer";self.plan_to(self.goal+[0,.20,0],True)
        elif self.phase=="transfer":self.phase="lower";self.plan_to(self.goal+[0,self.object_size[1]/2+.003,0],True)
        elif self.phase=="lower":
            self.phase="release";self.plan=None;self.data.ctrl[6:]=.04;self.phase_started=self.data.time
        elif self.phase=="retreat":
            self.phase="settle";self.plan=None;self.phase_started=self.data.time

    def tick(self,seconds=.08):
        if type(seconds) not in (int,float) or not 0<seconds<=.2:raise ValueError("Invalid control tick")
        with self.lock:
            self.touched=time.monotonic()
            if not self.running:return self.snapshot()
            for _ in range(round(seconds/self.model.opt.timestep)):
                try:
                    if self.plan is not None:
                        f=np.clip((self.data.time-self.plan_started)/self.plan_duration,0,1);u=f*f*(3-2*f)*(len(self.plan)-1)
                        i=min(int(u),len(self.plan)-2);self.data.ctrl[:6]=self.plan[i]*(1-(u-i))+self.plan[i+1]*(u-i)
                        if f>=1 and np.linalg.norm(self.data.site_xpos[self.site]-self.target)<.008:self.next_phase()
                        elif self.data.time-self.plan_started>self.plan_duration+3:self.fail("Joint tracking did not reach planned target")
                    elif self.phase=="close" and self.data.time-self.phase_started>.8:
                        if len(self.grasp_contacts())<2:self.fail("No bilateral finger contact; grasp refused")
                        else:self.phase="lift";self.plan_to(self.pick+[0,.18,0],True)
                    elif self.phase=="release" and self.data.time-self.phase_started>.6:
                        self.phase="retreat";self.plan_to(self.goal+[0,.20,0],True)
                    elif self.phase=="settle" and self.data.time-self.phase_started>1:
                        position=self.data.xpos[self.object_body];error=float(np.linalg.norm(position-self.goal))
                        joint=self.model.joint(self.workpiece_joints[self.object_id]);speed=float(np.linalg.norm(self.data.qvel[joint.dofadr[0]:joint.dofadr[0]+6]))
                        self.result={"passed":error<self.task.get("position_tolerance_m",.025) and speed<self.task.get("speed_tolerance",.05) and not self.grasp_contacts(),"position_error_m":error,"speed":speed,
                                     "object_position":position.tolist(),"scope":"Simulated pick/place position, release and settling only; no assembly or hardware verification",
                                     "proposed_scope":self.task["scope"]}
                        self.phase="completed" if self.result["passed"] else "failed";self.running=False
                        self.events.append({"event":"placement_verification",**self.result})
                except ValueError as error:self.fail(str(error))
                if self.data.time-self.task_started>120:self.fail("Task exceeded 120 simulated seconds")
                if not self.running:break
                mujoco.mj_step(self.model,self.data);self.steps+=1
                if self.evidence_dir and self.steps%100==0:
                    with (self.evidence_dir/"trajectory.jsonl").open("a") as handle:
                        handle.write(json.dumps({"time_s":float(self.data.time),"phase":self.phase,"joints":self.data.qpos[self.qadr].tolist(),
                                                 "part":self.data.xpos[self.object_body].tolist(),"finger_contacts":len(self.grasp_contacts())})+"\n")
                if not np.isfinite(self.data.qpos).all() or any(w.number for w in self.data.warning):self.fail("MuJoCo dynamics warning");break
            mujoco.mj_forward(self.model,self.data)
            return self.snapshot()

    def capture(self,path):
        with self.lock:
            with mujoco.Renderer(self.model,height=480,width=640) as renderer:
                renderer.update_scene(self.data,camera="observation")
                rgb=renderer.render().copy()
            def chunk(tag,data):return struct.pack("!I",len(data))+tag+data+struct.pack("!I",zlib.crc32(tag+data)&0xffffffff)
            rows=b"".join(b"\0"+row.tobytes() for row in rgb)
            path.write_bytes(b"\x89PNG\r\n\x1a\n"+chunk(b"IHDR",struct.pack("!2I5B",640,480,8,2,0,0,0))+chunk(b"IDAT",zlib.compress(rows))+chunk(b"IEND",b""))
            self.captured_images.append(path.name)

    def snapshot(self):
        objects=[]
        for item in self.instances:
            oid=item["id"]
            if oid in self.body_ids:body=self.body_ids[oid];pos=self.data.xpos[body];quat=self.data.xquat[body]
            else:pos=item["position"];quat=quaternion(item["rotation"])
            objects.append({"id":oid,"position":list(pos),"quaternion":[quat[1],quat[2],quat[3],quat[0]],"visible":self.visible[oid]})
        geoms=[]
        for gid in self.robot_geom_ids:
            quat=np.zeros(4);mujoco.mju_mat2Quat(quat,self.data.geom_xmat[gid])
            geoms.append({"id":gid,"type":int(self.model.geom_type[gid]),"size":self.model.geom_size[gid].tolist(),"position":self.data.geom_xpos[gid].tolist(),
                          "quaternion":[quat[1],quat[2],quat[3],quat[0]],"color":self.model.geom_rgba[gid,:3].tolist()})
        return {"engine":"MuJoCo","mode":"robot","version":mujoco.__version__,"step_id":self.step_id,"time_s":float(self.data.time),"steps":self.steps,
                "contacts":self.data.ncon,"objects":objects,"robot_geoms":geoms,"joints":self.data.qpos[self.qadr].tolist(),"actuators":self.model.nu,
                "phase":self.phase,"running":self.running,"view_target":self.data.xpos[self.object_body].tolist(),"agent_status":self.agent_status,"result":self.result,"events":self.events[-30:],
                "observation":self.observe(),"evidence_id":self.evidence_dir.name if self.evidence_dir else None,"captured_images":self.captured_images,
                "max_tracking_error_m":float(np.linalg.norm(self.data.site_xpos[self.site]-self.target)) if hasattr(self,"target") else 0,
                "physical_execution_verified":False}
