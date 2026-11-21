import {mountScene} from '/scene-viewer.js';

const $ = id => document.getElementById(id);
const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const clock = value => `${Math.floor(value/60)}:${String(Math.floor(value%60)).padStart(2,'0')}`;
const requestedRun=new URLSearchParams(location.search).get('run');
let selected = /^[0-9a-f]{32}$/.test(requestedRun || '')?requestedRun:null;
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
let runtimeSession=null, runtimeGeneration=0, runtimeBusy=false, lastRuntimeTime=-1, lastRobotState=null, robotReviewSignature='';
let transportBusy=false;
function robotTransport(){
  if(selectedStep!=='step_1')return {label:'Robot execution not implemented',disabled:true};
  if(transportBusy)return {label:'Please wait…',disabled:true};
  if(!runtimeSession)return {label:$('runtime-status').dataset.state==='error'?'Retry connection':'Connecting robot…',disabled:$('runtime-status').dataset.state!=='error',action:'connect'};
  const state=lastRobotState;
  if(!state)return {label:'Connecting robot…',disabled:true};
  if(state.agent_status==='thinking')return {label:state.phase==='idle'?'Planning…':'Verifying…',disabled:true};
  if(state.agent_status==='not requested')return {label:'▶ Play segment',action:'start'};
  if(['verified by agent','agent reported failure','agent error','decision budget exhausted'].includes(state.agent_status))return {label:state.result?.passed?'↻ Run again':'↻ Retry segment',action:'restart'};
  if(['completed','failed'].includes(state.phase))return {label:'Verifying…',disabled:true};
  return {label:state.running?'Ⅱ Pause segment':'▶ Resume segment',action:'pause',paused:!!state.running};
}
const robotEnabled=()=>$('motion-source').value==='robot';
const physicsEnabled=()=>$('motion-source').value!=='storyboard';
const runtimeRequest=(action,body)=>api(`/api/runtime/${action}`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
function closeRuntime(){
  runtimeGeneration++;lastRuntimeTime=-1;
  lastRobotState=null;robotReviewSignature='';
  const old=runtimeSession;runtimeSession=null;
  if(old)runtimeRequest('close',{session_id:old}).catch(()=>{});
}
async function connectRuntime(){
  closeRuntime();const generation=runtimeGeneration,segment=activeSegment();
  viewer?.setPhysicsMode(physicsEnabled());
  $('playback-heading').textContent=robotEnabled()?'LIVE ROBOT EXECUTION':'REFERENCE INSPECTION · ROBOT NOT EXECUTING';
  $('transport-help').textContent=robotEnabled()?'Play segment starts Gemini planning and the live robot. Pause/resume controls that same execution. The video below has its own reference playback controls.':'Reference playback only: the robot is not executing. Select Live robot in Advanced inspection to return to robot execution.';
  $('render-caption').textContent=robotEnabled()?'Live robot execution':'Reference animation · robot not executing';
  $('robot-controls').hidden=!robotEnabled();$('robot-review').hidden=true;$('robot-log').textContent='';
  $('robot-perturb').disabled=true;
  $('runtime-status').dataset.state='connecting';
  if(!physicsEnabled()){
    $('runtime-status').textContent='Authored storyboard · no physics';$('runtime-metrics').textContent='Reference animation used by the saved endpoint review.';
    $('renderer-status').textContent='OpenIndustries renderer · authored storyboard';return;
  }
  if(!segment)return;
  if(robotEnabled() && segment.step_id!=='step_1'){
    $('runtime-status').dataset.state='error';$('runtime-status').textContent='Live robot skill not implemented for this subtask';
    $('runtime-metrics').textContent='Select step 01 for live beam staging, or explicitly choose Authored storyboard to review this subtask’s proposal.';
    return;
  }
  $('runtime-status').textContent='MuJoCo · connecting…';
  try{
    const state=await runtimeRequest('connect',{run_id:selected,step_id:segment.step_id,mode:$('motion-source').value});
    if(generation!==runtimeGeneration){runtimeRequest('close',{session_id:state.session_id}).catch(()=>{});return;}
    runtimeSession=state.session_id;viewer?.setPhysicsState(state);showRuntime(state);
    if(robotEnabled())viewer?.focusRobot();
  }catch(err){if(generation===runtimeGeneration){$('video').pause();$('runtime-status').dataset.state='error';$('runtime-status').textContent=`MuJoCo disconnected · ${err.message}`;}}
}
function showRuntime(state){
  $('runtime-status').dataset.state='ready';
  if(state.mode==='robot'){
    lastRobotState=state;
    const stages={idle:'Ready',approach:'Moving to part',descend:'Approaching grasp',close:'Grasping',lift:'Lifting',transfer:'Moving part',lower:'Placing',release:'Releasing',retreat:'Retreating',settle:'Verifying',completed:'Complete',failed:'Failed'};
    $('runtime-status').textContent=state.agent_status==='thinking'?(state.phase==='idle'?'Planning…':'Verifying…'):state.agent_status==='executing'&&['completed','failed'].includes(state.phase)?'Verifying…':state.agent_status==='agent error'?'Agent failed — retry segment':`${stages[state.phase] || state.phase}${!state.running&&!['idle','completed','failed'].includes(state.phase)?' · paused':''}`;
    $('runtime-metrics').textContent=`Robot clock ${state.time_s.toFixed(2)}s · ${state.steps} solver steps · ${state.actuators} actuators · ${state.contacts} contacts · live joint positions ${state.joints.map(q=>q.toFixed(2)).join(', ')}`;
    $('renderer-status').textContent='OpenIndustries ← live articulated MuJoCo robot · online IK and contact grasp';
    $('robot-perturb').disabled=state.phase!=='idle'||state.agent_status==='thinking';
    $('robot-log').textContent=state.events.map(event=>event.event==='online_plan'?`${event.phase}: planned from observed state · path ${event.sha256.slice(0,10)}`:event.event==='agent_decision'?`Gemini: ${event.decision.action} — ${event.decision.reason}`:JSON.stringify(event)).join('\n');
    const signature=JSON.stringify([state.result,state.captured_images,state.evidence_id]);
    if(signature!==robotReviewSignature){
      robotReviewSignature=signature;$('robot-review').hidden=false;
      $('robot-review').innerHTML=`<p class="eyebrow">ACTUAL ROBOT EXECUTION · STEP 1 PREREQUISITE</p><h2>${state.result?(state.result.passed?'Beam staging verified in simulation':'Execution failed — inspect evidence'):'Observe → plan → grasp → place → verify'}</h2><p class="small">Human reference: initial beam selection / frame joining. Robot scope: stage one beam beside the fixture. This does not complete frame joining. Planner inputs use simulator poses, explicitly not vision-derived estimates.</p>${state.result?`<p>${esc(JSON.stringify(state.result))}</p>`:''}<div class="endpoint-pair">${(state.captured_images||[]).map(file=>`<figure><img src="/media/robot/${state.evidence_id}/${esc(file)}" alt="Actual MuJoCo ${esc(file)} observation"><figcaption>${esc(file)} · captured during this execution</figcaption></figure>`).join('')}</div>`;
    }
    return;
  }
  $('runtime-status').textContent=`MuJoCo ${state.version} · ${$('video').paused?'paused':'running'}`;
  $('runtime-metrics').textContent=`Simulation ${state.time_s.toFixed(2)}s · ${state.steps} physics steps · ${state.contacts} contacts · maximum guide error ${(state.max_tracking_error_m*1000).toFixed(1)} mm. Convex proposed-part colliders; original print sets are visual-only.`;
  $('renderer-status').textContent=`OpenIndustries renderer ← MuJoCo ${state.version} · ${state.steps} physics steps`;
}
async function runtimeTick(){
  const segment=activeSegment(),session=runtimeSession,generation=runtimeGeneration;
  if(physicsEnabled() && segment && session && !runtimeBusy){
    if(robotEnabled()){
      runtimeBusy=true;
      try{const state=await runtimeRequest('robot-tick',{session_id:session});if(generation===runtimeGeneration){viewer?.setPhysicsState(state);showRuntime(state);}}
      catch(err){if(generation===runtimeGeneration){closeRuntime();$('runtime-status').dataset.state='error';$('runtime-status').textContent=err.message;}}
      finally{runtimeBusy=false;setTimeout(runtimeTick,80);}
      return;
    }
    const target=Math.max(0,Math.min(segment.duration_s,$('video').currentTime-segment.start_s));
    if(Math.abs(target-lastRuntimeTime)>.004){
      runtimeBusy=true;
      try{
        const state=await runtimeRequest('advance',{session_id:session,time_s:target});
        if(generation===runtimeGeneration){lastRuntimeTime=target;viewer?.setPhysicsState(state);showRuntime(state);}
      }catch(err){if(generation===runtimeGeneration){$('video').pause();closeRuntime();$('runtime-status').dataset.state='error';$('runtime-status').textContent=`MuJoCo stopped · ${err.message}`;}}
      finally{runtimeBusy=false;}
    }else if($('runtime-status').dataset.state==='ready')$('runtime-status').textContent=$('runtime-status').textContent.replace(/running|paused/,$('video').paused?'paused':'running');
  }
  setTimeout(runtimeTick,80);
}
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
    connectRuntime();
    $('segment-controls').hidden=false;
    $('segment-title').textContent=`${step.title} · ${clock(step.start_s)}–${clock(step.end_s)}`;
    document.querySelectorAll('[data-segment]').forEach(el=>el.classList.toggle('selected',el.dataset.segment===id));
    $('scene-states').innerHTML='<p class="small">Authored plan — physics may deviate. Selecting a segment initializes its authored starting state.</p>'+['before','action','after'].map(key=>`<div class="scene-state"><b>${key.toUpperCase()}</b> ${esc(segment[key])}</div>`).join('');
    $('render-caption').textContent=`${id} · ${robotEnabled()?(id==='step_1'?'live robot execution':'authored initial layout · robot skill unavailable'):physicsEnabled()?'legacy guided workpieces':'authored storyboard'}`;
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
    <p class="review-note">${review?'Gemini reviewed video against the AUTHORED STORYBOARD endpoint renders below. This saved review does not assess the live MuJoCo trajectory. It is model judgment, not a benchmark score or physical verification.':esc(current.comparison_status?.message || 'Scene-author intent is shown below; it has not yet been visually compared.')}</p>
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
  closeRuntime();
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
    if(!selected && runs.length)selected=(runs.find(run=>run.phase==='ready') || runs[0]).id;
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
  if(robotEnabled()){
    const intent=robotTransport();if(intent.disabled)return;
    transportBusy=true;const generation=runtimeGeneration;
    try{
      if(['connect','restart'].includes(intent.action)){
        const expectedGeneration=runtimeGeneration+1;
        await connectRuntime();if(!runtimeSession || !robotEnabled() || runtimeGeneration!==expectedGeneration || selectedStep!==segment.step_id)return;
      }else if(generation!==runtimeGeneration)return;
      const activeGeneration=runtimeGeneration;
      const state=await runtimeRequest(intent.action==='pause'?'robot-pause':'robot-agent',
        {session_id:runtimeSession,...(intent.action==='pause'?{paused:intent.paused}:{})});
      if(activeGeneration===runtimeGeneration){viewer?.setPhysicsState(state);showRuntime(state);}
    }catch(err){error(err.message);}
    finally{transportBusy=false;}
    return;
  }
  if(physicsEnabled() && !robotEnabled() && !runtimeSession){await connectRuntime();if(!runtimeSession)return;}
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
  if(step && step.id!==selectedStep && !robotEnabled())chooseStep(step.id,false);
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
    const transport=robotEnabled()?robotTransport():{label:video.paused?'▶ Play reference':'Ⅱ Pause reference',disabled:false};
    $('play-segment').textContent=transport.label;$('play-segment').disabled=!!transport.disabled;
    $('segment-scrub').hidden=robotEnabled();$('segment-time').hidden=robotEnabled();$('loop-segment').parentElement.hidden=robotEnabled();
    $('scene-stage').textContent=robotEnabled()?(lastRobotState?.phase || 'CONNECTING'):inUnsegmentedGap?'NO SEGMENT AT THIS TIME':progress<.02?'BEFORE':progress>.98?'AFTER':'ACTION';
    const index=current.segments.segments.findIndex(item=>item.step_id===selectedStep);
    $('previous-segment').disabled=index<=0;$('next-segment').disabled=index>=current.segments.segments.length-1;
  }
  requestAnimationFrame(playbackTick);
}
playbackTick();
$('motion-source').addEventListener('change',()=>{$('video').pause();connectRuntime();});
$('reconnect-runtime').addEventListener('click',()=>{$('video').pause();connectRuntime();});
for(const [id,action,payload]of [
  ['robot-perturb','robot-perturb',()=>({dx:.08,dz:-.04})]
])$(id).addEventListener('click',async()=>{
  if(!runtimeSession)return;$(id).disabled=true;const generation=runtimeGeneration;
  try{const state=await runtimeRequest(action,{session_id:runtimeSession,...payload()});if(generation===runtimeGeneration){viewer?.setPhysicsState(state);showRuntime(state);}}
  catch(err){error(err.message);}
});
window.addEventListener('pagehide',()=>{
  if(runtimeSession)fetch('/api/runtime/close',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({session_id:runtimeSession}),keepalive:true}).catch(()=>{});
});
runtimeTick();
async function poll(){await refresh();setTimeout(poll,2500);}
poll();
