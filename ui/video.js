import {mountScene} from '/scene-viewer.js';

const $ = id => document.getElementById(id);
const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const clock = value => `${Math.floor(value/60)}:${String(Math.floor(value%60)).padStart(2,'0')}`;
let selected = null;
let current = null;
let viewer = null;
let loadedScene = null;
let renderedAnalysis = null;
let renderedComparison = null;
let renderedFrames = null;
let launching = false;
let selectedStep = null;
let reviewSignature = '';
let inUnsegmentedGap = false;
const activeSegment = () => current?.segments?.segments.find(segment=>segment.step_id===selectedStep);

async function api(url, options) {
  const response = await fetch(url,options);
  if (!response.ok) {
    const data = await response.json().catch(()=>({}));
    throw new Error(data.error || `Request failed (${response.status})`);
  }
  return response.json();
}
function error(message) { $('error').hidden=false; $('error').textContent=message; }
function seek(time) {
  if (Number.isFinite(Number(time))) $('video').currentTime=Number(time);
}
function chooseStep(id, jump=true) {
  const step=current?.analysis?.steps.find(item=>item.id===id);
  if (!step) return;
  selectedStep=id;
  inUnsegmentedGap=false;
  if(jump)$('video').pause();
  if (jump) seek(step.start_s);
  document.querySelectorAll('.step').forEach(el=>el.classList.toggle('selected',el.dataset.step===id));
  const segment=activeSegment();
  const ids=segment?.active_object_ids || (current?.scene_spec?.objects || []).filter(obj=>obj.step_ids.includes(id)).map(obj=>obj.id);
  viewer?.highlight(ids);
  document.querySelectorAll('.object').forEach(el=>el.classList.toggle('selected',ids.includes(el.dataset.object)));
  if(segment){
    viewer?.setSegment(segment);
    viewer?.setClock(()=>Math.max(0,Math.min(segment.duration_s,$('video').currentTime-segment.start_s)));
    viewer?.focusSegment();
    $('segment-controls').hidden=false;
    $('segment-title').textContent=`${step.title} · ${clock(step.start_s)}–${clock(step.end_s)}`;
    document.querySelectorAll('[data-segment]').forEach(el=>el.classList.toggle('selected',el.dataset.segment===id));
    $('scene-states').innerHTML=['before','action','after'].map(key=>`<div class="scene-state"><b>${key.toUpperCase()}</b> ${esc(segment[key])}</div>`).join('');
    $('render-caption').textContent=`${id} · synchronized schematic workpiece replay`;
    $('download-segment').hidden=false;$('download-segment').href=`/api/video-runs/${selected}/segments/${encodeURIComponent(id)}/scene`;
    renderSegmentReview();
  }
}

function renderSegmentReview(){
  const segment=activeSegment();if(!segment)return;
  const review=current.segment_comparison?.segments.find(item=>item.step_id===segment.step_id);
  const evidence=review?.evidence || current.segment_evidence?.find(item=>item.step_id===segment.step_id);
  const signature=JSON.stringify([selected,segment.step_id,review,evidence,current.comparison_status]);
  if(signature===reviewSignature)return;reviewSignature=signature;
  $('segment-review').hidden=false;
  const images=kind=>evidence?`<div class="endpoint-pair">${['before','after'].map(phase=>{
    const image=evidence.images.find(item=>item.kind===kind && item.phase===phase);
    return image?`<figure><img loading="lazy" src="/media/segment-evidence/${selected}/${esc(image.file)}" alt="${kind} ${phase} for ${esc(segment.title)}"><figcaption>${phase.toUpperCase()} · ${clock(phase==='before'?segment.start_s:segment.end_s)}</figcaption></figure>`:'';
  }).join('')}</div>`:'<p class="small">Endpoint images will appear when captured.</p>';
  const list=items=>`<ul>${items.map(item=>`<li>${esc(item)}</li>`).join('')}</ul>`;
  const step=current.analysis.steps.find(item=>item.id===segment.step_id);
  const refs=evidence?.reference_labels || current.comparison?.rows.filter(row=>row.time_s>=segment.start_s&&row.time_s<=segment.end_s) || [];
  $('segment-review').innerHTML=`<div class="review-heading"><div><p class="eyebrow">COMPARISON FOR THIS SUBTASK</p><h2>${esc(segment.title)}</h2></div><span class="verdict">${review?esc(review.verdict.replaceAll('_',' ')):'Visual review pending'}</span></div>
    <p class="review-note">${review?'Gemini reviewed actual video and actual OI endpoint renders. This is model judgment, not a benchmark score or physical verification.':esc(current.comparison_status?.message || 'Scene-author intent is shown below; it has not yet been visually compared.')}</p>
    <div class="review-grid"><div class="review-side"><h3>HUMAN VIDEO · ${clock(segment.start_s)}–${clock(segment.end_s)}</h3>${images('video')}<p>${esc(review?.observed_change || step.evidence)}</p></div><div class="review-side"><h3>OPENINDUSTRIES · SAME SUBTASK</h3>${images('scene')}<p>${esc(review?.rendered_change || segment.before+' → '+segment.after)}</p></div></div>
    <div class="review-findings"><div><h3>${review?'Visible correspondences':'Authored object correspondence'}</h3>${list(review?.matched_aspects || segment.object_mapping.map(m=>`${m.observed} → ${m.scene_object_ids.join(', ')} (${m.representation})`))}</div><div><h3>Differences / missing actions</h3>${list(review?.differences || segment.differences)}</div><div><h3>Not established</h3>${list(review?.not_verifiable || [step.uncertainty,'No visual reviewer result yet.','Robot reach, contact forces, fastening torque and successful execution remain unverified.'])}</div></div>
    <p class="reference-match"><strong>Dataset completion labels within this interval:</strong> ${refs.length?refs.map(ref=>`${clock(ref.time_s)} ${esc(ref.label)}`).join(' · '):'None. This is not an automatic mismatch: labels annotate completion, not every visible action.'}</p>
    <p class="review-note">Structural checks: native OI timeline valid · endpoint continuity checked · ${segment.structural_checks.moving_objects} changing workpiece objects. The animation duration is synchronized to the human clip, not a robot-cycle-time estimate.</p>`;
}
function chooseObject(id) {
  const object=current?.scene_spec?.objects.find(obj=>obj.id===id);
  if(!object)return;
  if(object.step_ids.length)chooseStep(object.step_ids[0]);
  viewer?.highlight([id]);
  document.querySelectorAll('.object').forEach(el=>el.classList.toggle('selected',el.dataset.object===id));
  $('render-caption').textContent=`${object.name} · ${object.kind==='dataset'?'original dataset geometry':'Gemini-proposed equipment'}`;
}
function clearRun() {
  current=null; renderedAnalysis=null;renderedComparison=null;renderedFrames=null;loadedScene=null;selectedStep=null;
  reviewSignature='';inUnsegmentedGap=false;$('video').pause();
  viewer?.dispose(); viewer=null;
  $('analysis').innerHTML='<div class="placeholder"><h2>Reconstructing the demonstration…</h2><p>Gemini receives video frames and timestamps. Reference annotations are withheld.</p></div>';
  $('viewport').innerHTML='<div class="placeholder"><span>⌘</span><h2>Waiting for the scene agent.</h2><p>The workcell is generated after video analysis. No prebuilt scene is substituted.</p></div>';
  $('equipment').replaceChildren();$('scene-summary').replaceChildren();$('comparison').replaceChildren();$('evidence').replaceChildren();
  $('step-count').textContent='WAITING';$('download').hidden=true;$('reset-view').hidden=true;$('render-caption').hidden=true;
  $('segment-controls').hidden=true;$('segment-review').hidden=true;$('download-segment').hidden=true;$('scene-states').replaceChildren();
}

async function render(data, runId) {
  current=data;
  const phase=data.status?.phase;
  $('progress').textContent=data.status?.message || 'Loading…';
  if(data.segments_status && !['ready','failed'].includes(data.segments_status.phase))$('progress').textContent=data.segments_status.message;
  if(data.comparison_status && data.comparison_status.phase!=='ready')$('progress').textContent=data.comparison_status.message;
  $('phase-analysis').className=`phase ${data.analysis?'done':['sampling','analyzing'].includes(phase)?'current working':''}`;
  $('phase-scene').className=`phase ${phase==='ready'?'done':['designing','compiling','segmenting','comparing'].includes(phase)?'current working':''}`;
  if (phase==='failed')error(data.status.message);
  if (data.analysis && renderedAnalysis!==runId) {
    renderedAnalysis=runId;
    $('step-count').textContent=`${data.analysis.steps.length} STEPS`;
    $('analysis').innerHTML=`<p class="analysis-summary">${esc(data.analysis.summary)}</p>`+data.analysis.steps.map((step,index)=>`
      <button class="step" data-step="${esc(step.id)}"><div class="step-head"><h3>${String(index+1).padStart(2,'0')} · ${esc(step.title)}</h3><time>${clock(step.start_s)}–${clock(step.end_s)}</time></div><p>${esc(step.evidence)}</p><small>${esc(step.objects.join(' · '))}</small>${step.uncertainty?`<p class="uncertain">Uncertain: ${esc(step.uncertainty)}</p>`:''}</button>`).join('');
  }
  if (data.frames && renderedFrames!==runId) {
    renderedFrames=runId;
    $('evidence').innerHTML=data.frames.filter((_,i)=>i%4===0).map(frame=>`<button data-time="${frame.time_s}" title="Sampled video evidence at ${clock(frame.time_s)}"><img loading="lazy" src="/media/frames/${runId}/${frame.file}" alt="Source frame at ${clock(frame.time_s)}"><span>${clock(frame.time_s)}</span></button>`).join('');
  }
  if (data.comparison && renderedComparison!==runId) {
    renderedComparison=runId;
    $('comparison').innerHTML=`<p>${esc(data.comparison.method)} The ${data.comparison.rows.length} reference completion labels below were not provided to either agent.</p>`+data.comparison.rows.map(row=>`<div class="reference-row"><button data-time="${row.time_s}">${clock(row.time_s)}</button><div><strong>${esc(row.label)}</strong><small>Nearest predicted completion: ${esc(row.predicted_title)} (${row.end_time_delta_s>=0?'+':''}${row.end_time_delta_s}s). Temporal proximity does not establish a correct semantic match.</small></div></div>`).join('');
  }
  const assumptions=[...(data.analysis?.uncertainties || []),...(data.scene_spec?.assumptions || []),...(data.validation?.warnings || []),...(data.segments?.assumptions || [])];
  if(assumptions.length)$('assumptions').innerHTML='<ul>'+assumptions.map(text=>`<li>${esc(text)}</li>`).join('')+'</ul>';
  const sceneKey=`${runId}:${data.segments?'segmented':'static'}`;
  if(data.validation?.native_manifest_valid && loadedScene!==sceneKey) {
    loadedScene=sceneKey;
    try {
      const manifest=await api(`/api/video-runs/${runId}/scene`);
      if(selected!==runId)return;
      viewer?.dispose();
      viewer=mountScene($('viewport'),manifest,chooseObject);
      const stats=viewer.stats();
      window.workcellEvidence={runId,renderer:'OpenIndustries createWorld',stats,playback:()=>viewer?.snapshot()};
      $('reset-view').hidden=false;$('render-caption').hidden=false;
      $('render-caption').textContent='Drag to orbit · scroll to zoom · click equipment';
      $('scene-summary').innerHTML=`<h2>${esc(data.scene_spec.title)}</h2><p>${data.segments?`${data.segments.segments.length} scene segments. Workpiece proxies change between states; original dataset print sets remain reference inventory.`:esc(data.scene_spec.rationale)}</p><p><strong>${data.validation.dataset_instances} original dataset sets</strong> · ${stats.instances-data.validation.dataset_instances} proposed equipment / schematic workpiece objects</p><p class="small">Native scene schema and geometry references checked. No collision, robot IK, force, or physical-execution verification.</p>`;
      $('equipment').innerHTML=data.scene_spec.objects.map(obj=>`<button class="object" data-kind="${esc(obj.kind)}" data-object="${esc(obj.id)}" title="${esc(obj.rationale)}">${obj.kind==='dataset'?'◈':'◇'} ${esc(obj.name)}</button>`).join('');
      $('download').href=`/api/video-runs/${runId}/scene`;$('download').hidden=false;
      $('renderer-status').textContent=`OpenIndustries · ${stats.instances} instances · ${stats.meshes} meshes · proposed layout`;
      if(data.segments){
        $('segment-chips').innerHTML=data.segments.segments.map((segment,index)=>`<button data-segment="${esc(segment.step_id)}" title="${esc(segment.title)}">${String(index+1).padStart(2,'0')}</button>`).join('');
        chooseStep(selectedStep || data.segments.segments[0].step_id,!!selectedStep);
      }else if(selectedStep)chooseStep(selectedStep,false);
    } catch(err) {
      loadedScene=null;
      $('viewport').innerHTML='<div class="placeholder"><h2>Renderer could not load.</h2><p>'+esc(err.message)+'</p></div>';
      error(err.message);
    }
  }
  if(activeSegment())renderSegmentReview();
}

async function refresh() {
  try {
    const {runs}=await api('/api/video-runs');
    const running=runs.some(run=>!['ready','failed'].includes(run.phase));
    $('generate').disabled=launching || running;
    $('generate').textContent=running?'Gemini is working…':'Analyze video & build workcell ↗';
    const options=runs.map(run=>`<option value="${run.id}">${new Date(run.created*1000).toLocaleTimeString()} · ${esc(run.phase)}</option>`).join('');
    if($('history').innerHTML!==options)$('history').innerHTML=options || '<option>No analysis yet</option>';
    if(!selected && runs.length)selected=runs[0].id;
    if(selected){$('history').value=selected; const id=selected;const data=await api(`/api/video-runs/${id}`);if(id===selected)await render(data,id);}
    else $('progress').textContent='Ready: real IndustReal recording loaded. Start with “Analyze video & build workcell.”';
  } catch(err) {error(err.message);}
}
$('generate').addEventListener('click',async()=>{
  launching=true;$('generate').disabled=true;$('error').hidden=true;
  try{const result=await api('/api/video-run',{method:'POST',headers:{'Content-Type':'application/json'},body:'{}'});selected=result.id;clearRun();await refresh();}
  catch(err){error(err.message);}
  finally{launching=false;}
});
$('history').addEventListener('change',()=>{selected=$('history').value;$('error').hidden=true;clearRun();refresh();});
$('analysis').addEventListener('click',event=>{const step=event.target.closest('[data-step]');if(step)chooseStep(step.dataset.step);});
$('equipment').addEventListener('click',event=>{const obj=event.target.closest('[data-object]');if(obj)chooseObject(obj.dataset.object);});
for(const id of ['comparison','evidence'])$(id).addEventListener('click',event=>{const target=event.target.closest('[data-time]');if(target)seek(target.dataset.time);});
$('reset-view').addEventListener('click',()=>viewer?.home());
$('segment-chips').addEventListener('click',event=>{const chip=event.target.closest('[data-segment]');if(chip)chooseStep(chip.dataset.segment);});
for(const [button,delta]of [['previous-segment',-1],['next-segment',1]])$(button).addEventListener('click',()=>{
  const segments=current?.segments?.segments || [],index=segments.findIndex(item=>item.step_id===selectedStep);
  const next=segments[index+delta];if(next)chooseStep(next.step_id);
});
$('play-segment').addEventListener('click',async()=>{
  const segment=activeSegment();if(!segment)return;
  if(!$('video').paused){$('video').pause();return;}
  if($('video').currentTime<segment.start_s || $('video').currentTime>=segment.end_s-.05)seek(segment.start_s);
  try{await $('video').play();}catch(err){error(err.message);}
});
$('segment-scrub').addEventListener('input',()=>{const segment=activeSegment();if(segment){$('video').pause();seek(segment.start_s+segment.duration_s*Number($('segment-scrub').value)/1000);}});
$('video').addEventListener('seeking',()=>{
  const time=$('video').currentTime;
  const active=activeSegment();
  if(active && time>=active.start_s-.01 && time<=active.end_s+.01){inUnsegmentedGap=false;return;}
  const step=current?.analysis?.steps.find(s=>s.start_s-.01<=time && s.end_s+.01>=time);
  inUnsegmentedGap=!step;
  if(step && step.id!==selectedStep)chooseStep(step.id,false);
});
function playbackTick(){
  const segment=activeSegment(), video=$('video');
  if(segment){
    if(!video.paused && !video.seeking && !inUnsegmentedGap && video.currentTime>=segment.end_s-.015){
      if($('loop-segment').checked)seek(segment.start_s);
      else{video.pause();seek(segment.end_s);}
    }
    const time=Math.max(0,Math.min(segment.duration_s,video.currentTime-segment.start_s)),progress=time/segment.duration_s;
    $('segment-scrub').value=String(Math.round(progress*1000));
    $('segment-time').textContent=`${clock(video.currentTime)} / ${clock(segment.end_s)}`;
    $('play-segment').textContent=video.paused?'▶ Play segment':'Ⅱ Pause segment';
    $('scene-stage').textContent=inUnsegmentedGap?'NO SEGMENT AT THIS TIME':progress<.02?'BEFORE':progress>.98?'AFTER':'ACTION';
    const index=current.segments.segments.findIndex(item=>item.step_id===selectedStep);
    $('previous-segment').disabled=index<=0;$('next-segment').disabled=index>=current.segments.segments.length-1;
  }
  requestAnimationFrame(playbackTick);
}
playbackTick();
async function poll(){await refresh();setTimeout(poll,2500);}
poll();
