#!/usr/bin/env python3
"""Have Gemini author a native OI animation segment for every reconstructed video step."""
import argparse
import json
import os
from pathlib import Path
import re
import subprocess

from video_pipeline import ROOT, DATA, write, download_json
from managed_agent_smoke import DEFAULT_AGENT, interact, read_snapshot_json


def generate_segments(output, key):
    analysis=json.loads((output/"analysis.json").read_text())
    scene=json.loads((output/"scene-spec.json").read_text())
    prompt="""You are a workcell motion storyboard author. The current workcell only displays static equipment. Generate one different, temporally aligned scene segment for EACH observed video subtask. Write segments-spec.json by executing code. Do not simply highlight the same robot or move inventory trays. Visibly show the workpiece assembling over the successive subtasks, with BEFORE, ACTION, AFTER states.

Use clearly labeled SCHEMATIC PROXY parts for the workpiece (white chassis beams, gray axles/pins, pink fasteners, black wheels); do not claim these are original dataset geometry. The real four dataset print-set meshes remain stationary inventory. Equipment can remain stationary; the replay illustrates proposed part transfers and joining, NOT robot inverse kinematics or contact physics. Do not translate the whole robot pedestal to imply robot execution. Use 10–18 additional composite objects maximum; total scene object count must remain <=30. The workpiece should build progressively near the existing fixture. Dimensions must fit the fixture and table; a consistent illustrative enlargement is acceptable if explicitly declared. Proxies should be clearly visible in a close view.

Return this structure:
{"assumptions":["..."], "new_objects":[
 {"id":"proxy_beam_left","name":"Schematic left chassis beam","kind":"proposal","position":[x,y,z],"rotation":[0,0,0],"rationale":"schematic moving workpiece, not source CAD","step_ids":["step_1"],"parts":[{"name":"beam","shape":"box","size":[width,height,depth],"position":[0,height/2,0],"rotation":[0,0,0],"color":[0.8,0.8,0.8]}]}
], "initial_states":{"proxy_beam_left":{"position":[x,y,z],"rotation":[0,0,0],"visible":false}},
"segments":[{"step_id":"step_1","active_object_ids":["assembly_fixture","proxy_beam_left"],"before":"specific proposed initial assembly state","action":"specific proposed transfer/joining movement","after":"specific proposed resulting assembly state","differences":["what this schematic does not reproduce from the human video"],"object_mapping":[{"observed":"white beam","scene_object_ids":["proxy_beam_left"],"representation":"schematic proxy"}],"tracks":[{"object_id":"proxy_beam_left","keys":[{"progress":0,"position":[x,y,z],"rotation":[0,0,0],"visible":false},{"progress":0.05,"position":[x,y,z],"rotation":[0,0,0],"visible":true},{"progress":1,"position":[target_x,target_y,target_z],"rotation":[0,0,0],"visible":true}]}]}]}

Rules: each analysis step appears exactly once, same order. Every segment must contain at least one visibly changing workpiece track. Absolute world poses, Y up, meters, Euler degrees. Object positions refer to bottom center after geometry normalization; primitive positions are local centers. Cylinder size=[diameter,height,diameter] with Y axis; rotate a horizontal wheel axle appropriately. Provide initial_states for ALL new objects. Only new workpiece proxies may have tracks, not existing equipment or source inventory. Key progress strictly increases from 0 to 1, max 8 keys per track, all keys explicitly include visible (boolean), position and rotation. The first key of every track MUST equal that object's state carried forward from the preceding segment (or its initial_states in the first segment); use Python to compute this and avoid discontinuities. Untracked objects hold state. Do not hide completed subassemblies between steps. In later steps, move joined subassembly members together preserving relative transforms. Every segment needs evidence-to-scene object_mapping and explicit differences. Compare observed human actions with the PROPOSED state sequence, not with claimed execution success. Do not invent benchmark scores. The scene's before/action/after text and proxy states must agree.

Observed analysis (reference annotations not supplied):\n"""+json.dumps(analysis)+"\nExisting scene (keep its objects unchanged):\n"+json.dumps(scene)
    write(output/"segments-status.json",{"phase":"generating","message":"Gemini is authoring one changing workpiece scene per video subtask."})
    (output/"segments-prompt.txt").write_text(prompt)
    result=interact(key,DEFAULT_AGENT,prompt,output,"segments")
    spec=download_json(key,result,"segments-spec.json",output,"segments")
    compile_segments(output,spec)


def compile_segments(output,spec):
    write(output/"segments-spec.json",spec)
    write(output/"segments-status.json",{"phase":"compiling","message":"Checking segment coverage, time bounds, object mappings and cross-segment pose continuity."})
    command=["node",str(ROOT/"ui/dist/compile-segments.mjs"),str(output),str(DATA/"geometry.json")]
    result=subprocess.run(command,text=True,capture_output=True,timeout=180)
    if result.returncode:raise ValueError(result.stderr[-4000:])
    write(output/"segments-status.json",{"phase":"ready","message":"All video steps have native OpenIndustries scene segments.","checks":json.loads(result.stdout)})
    print(result.stdout,flush=True)


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run_id")
    parser.add_argument("--from-snapshot",action="store_true",help="Resume compilation from the already-downloaded agent artifact; no API call")
    args=parser.parse_args()
    if not re.fullmatch(r"[0-9a-f]{32}",args.run_id):parser.error("Invalid run ID")
    output=ROOT/"artifacts/video-workcells"/args.run_id
    key=os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if not key and not args.from_snapshot:parser.error("Set GEMINI_API_KEY")
    try:
        if args.from_snapshot:
            compile_segments(output,read_snapshot_json((output/"segments-snapshot.tar").read_bytes(),"segments-spec.json",max_bytes=1024*1024))
        else:generate_segments(output,key)
    except Exception as error:
        write(output/"segments-status.json",{"phase":"failed","message":str(error).replace(key,"[REDACTED]") if key else str(error)})
        raise
