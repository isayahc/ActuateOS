import {mountScene} from '/scene-viewer.js';
const id=new URLSearchParams(location.search).get('run');
if(!/^[0-9a-f]{32}$/.test(id))throw new Error('Invalid run');
const data=await(await fetch(`/api/video-runs/${id}`)).json();
const manifest=await(await fetch(`/api/video-runs/${id}/scene`)).json();
const viewer=mountScene(document.getElementById('viewport'),manifest,()=>{});
window.captureSegment=async(stepId,progress)=>{
  const segment=data.segments.segments.find(item=>item.step_id===stepId);
  if(!segment)throw new Error('Unknown scene segment');
  viewer.setClock(null);viewer.setSegment(segment);viewer.setTime(progress*segment.duration_s);viewer.focusSegment();
  viewer.highlight(segment.active_object_ids);
  document.getElementById('label').textContent=`${stepId} · ${progress===0?'BEFORE':'AFTER'} · ${segment.title} — schematic, not physical execution`;
  await new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)));
  return viewer.snapshot();
};
window.captureReady=true;
