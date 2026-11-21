/** Validate stateful storyboards and compile each subtask to a native OI timeline. */
import fs from 'node:fs';
import path from 'node:path';
import {spawnSync} from 'node:child_process';
import {readManifest} from '../.deps/OpenIndustries/src/lib/workspace';

const [directory,geometryPath]=process.argv.slice(2);
const read=(name:string)=>JSON.parse(fs.readFileSync(path.join(directory,name),'utf8'));
const source=read('scene-spec.json'), analysis=read('analysis.json'), spec=read('segments-spec.json');
const requireThat=(condition:any,message:string)=>{if(!condition)throw new Error(message);};
const vector=(v:any)=>Array.isArray(v)&&v.length===3&&v.every(n=>typeof n==='number'&&Number.isFinite(n)&&Math.abs(n)<=100);
const pose=(p:any)=>p&&vector(p.position)&&vector(p.rotation)&&typeof p.visible==='boolean';
const same=(a:any,b:any)=>a.visible===b.visible&&['position','rotation'].every(k=>a[k].every((v:number,i:number)=>Math.abs(v-b[k][i])<1e-5));
requireThat(Array.isArray(spec.new_objects)&&spec.new_objects.length>0&&spec.new_objects.length+source.objects.length<=30,'Invalid new object count');
requireThat(Array.isArray(spec.assumptions)&&spec.assumptions.every((s:any)=>typeof s==='string'),'Missing storyboard assumptions');
const existingIds=new Set(source.objects.map((o:any)=>o.id));
const movingIds=new Set<string>();
for(const object of spec.new_objects){
  requireThat(object.kind==='proposal'&&!existingIds.has(object.id)&&!movingIds.has(object.id),'New moving workpieces must be unique proposed objects');
  movingIds.add(object.id);
}
const allIds=new Set([...existingIds,...movingIds]);
requireThat(spec.initial_states&&Object.keys(spec.initial_states).length===movingIds.size,'Initial states must cover every proxy');
for(const id of Object.keys(spec.initial_states))requireThat(movingIds.has(id)&&pose(spec.initial_states[id]),`Invalid initial pose: ${id}`);
requireThat(Array.isArray(spec.segments)&&spec.segments.length===analysis.steps.length,'Exactly one scene segment is required per video step');
const merged={...source,objects:[...source.objects,...spec.new_objects]};
fs.writeFileSync(path.join(directory,'segmented-scene-spec.json'),JSON.stringify(merged,null,2));
const staging=path.join(directory,'segmented-workcell.pending.json');
const compiled=spawnSync(process.execPath,[path.join(import.meta.dirname,'compile-scene.mjs'),path.join(directory,'segmented-scene-spec.json'),geometryPath,staging],{encoding:'utf8'});
requireThat(compiled.status===0,compiled.stderr);
const manifest=JSON.parse(fs.readFileSync(staging,'utf8'));
const state=new Map<string,any>(manifest.instances.map((item:any)=>[item.id,{position:item.position,rotation:item.rotation,visible:true}]));
for(const [id,value]of Object.entries(spec.initial_states))state.set(id,structuredClone(value));
const segments=[];
for(let i=0;i<analysis.steps.length;i++){
  const step=analysis.steps[i], segment=spec.segments[i],duration=step.end_s-step.start_s;
  requireThat(segment.step_id===step.id,`Segment ${i+1} must map to ${step.id} in video order`);
  requireThat(duration>=.5&&duration<=120,'Segment duration must fit the native OI 0.5–120s timeline');
  for(const field of ['before','action','after'])requireThat(typeof segment[field]==='string'&&segment[field].length>0,`Missing ${field} state`);
  requireThat(Array.isArray(segment.differences)&&segment.differences.length>0&&segment.differences.every((v:any)=>typeof v==='string'),'Explicit differences required');
  requireThat(Array.isArray(segment.active_object_ids)&&segment.active_object_ids.length>0&&segment.active_object_ids.every((id:any)=>allIds.has(id)),'Invalid active objects');
  requireThat(Array.isArray(segment.object_mapping)&&segment.object_mapping.length>0,'Observed-to-scene mapping required');
  for(const mapping of segment.object_mapping)requireThat(typeof mapping.observed==='string'&&typeof mapping.representation==='string'&&Array.isArray(mapping.scene_object_ids)&&mapping.scene_object_ids.length>0&&mapping.scene_object_ids.every((id:any)=>allIds.has(id)),'Invalid object correspondence');
  requireThat(Array.isArray(segment.tracks)&&segment.tracks.length>0,'Each segment must have a visible state change');
  const instances=manifest.instances.map((item:any)=>({...item,...structuredClone(state.get(item.id))}));
  const tracked=new Set();
  let changed=0;
  const tracks=segment.tracks.map((track:any)=>{
    const id=track.object_id;
    requireThat(movingIds.has(id)&&!tracked.has(id),`Only unique schematic workpieces can move: ${id}`);
    tracked.add(id);
    requireThat(segment.active_object_ids.includes(id),'Moving object must be active in this segment');
    requireThat(Array.isArray(track.keys)&&track.keys.length>=2&&track.keys.length<=8,'Expected 2–8 keyframes');
    requireThat(track.keys[0].progress===0&&track.keys.at(-1).progress===1,'Keyframes must cover the whole segment');
    let previous=-1;
    for(const key of track.keys){
      requireThat(pose(key)&&typeof key.progress==='number'&&Number.isFinite(key.progress)&&key.progress>previous&&key.progress<=1,'Invalid pose or keyframe ordering');
      previous=key.progress;
    }
    requireThat(same(track.keys[0],state.get(id)),`State discontinuity for ${id} at ${step.id}`);
    if(track.keys.some((k:any)=>!same(k,track.keys[0])))changed++;
    const last=track.keys.at(-1);state.set(id,{position:last.position,rotation:last.rotation,visible:last.visible});
    return {id:`${id}:instance`,instanceId:id,keys:track.keys.map((key:any,index:number)=>({id:`${step.id}-${id}-${index}`,time:key.progress*duration,position:key.position,rotation:key.rotation,visible:key.visible}))};
  });
  requireThat(changed>0,'Segment contains no actual pose or visibility change');
  const animation={duration,loop:false,tracks};
  readManifest({...manifest,instances,animation});
  const first=instances.filter((item:any)=>movingIds.has(item.id));
  const after=first.map((item:any)=>({...item,...structuredClone(state.get(item.id))}));
  segments.push({step_id:step.id,title:step.title,start_s:step.start_s,end_s:step.end_s,duration_s:duration,
    before:segment.before,action:segment.action,after:segment.after,differences:segment.differences,
    active_object_ids:segment.active_object_ids,object_mapping:segment.object_mapping,
    instances,animation,before_poses:first,after_poses:after,
    structural_checks:{native_timeline_valid:true,continuous_from_previous:true,moving_objects:changed},
    physical_execution_verified:false});
}
const result={version:1,scope:'Schematic workpiece replay, not robot IK/contact execution',assumptions:spec.assumptions,
  segments,checks:{coverage_complete:true,native_timelines_valid:true,state_continuity:true,segment_count:segments.length}};
fs.renameSync(staging,path.join(directory,'segmented-workcell.oi.json'));
fs.writeFileSync(path.join(directory,'segments.json.tmp'),JSON.stringify(result,null,2));
fs.renameSync(path.join(directory,'segments.json.tmp'),path.join(directory,'segments.json'));
console.log(JSON.stringify(result.checks));
