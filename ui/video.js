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
  if (jump) seek(step.start_s);
  document.querySelectorAll('.step').forEach(el=>el.classList.toggle('selected',el.dataset.step===id));
  const objects=(current?.scene_spec?.objects || []).filter(obj=>obj.step_ids.includes(id));
  viewer?.highlight(objects.map(obj=>obj.id));
  document.querySelectorAll('.object').forEach(el=>el.classList.toggle('selected',objects.some(obj=>obj.id===el.dataset.object)));
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
  viewer?.dispose(); viewer=null;
  $('analysis').innerHTML='<div class="placeholder"><h2>Reconstructing the demonstration…</h2><p>Gemini receives video frames and timestamps. Reference annotations are withheld.</p></div>';
  $('viewport').innerHTML='<div class="placeholder"><span>⌘</span><h2>Waiting for the scene agent.</h2><p>The workcell is generated after video analysis. No prebuilt scene is substituted.</p></div>';
  $('equipment').replaceChildren();$('scene-summary').replaceChildren();$('comparison').replaceChildren();$('evidence').replaceChildren();
  $('step-count').textContent='WAITING';$('download').hidden=true;$('reset-view').hidden=true;$('render-caption').hidden=true;
}

async function render(data, runId) {
  current=data;
  const phase=data.status?.phase;
  $('progress').textContent=data.status?.message || 'Loading…';
  $('phase-analysis').className=`phase ${data.analysis?'done':['sampling','analyzing'].includes(phase)?'current working':''}`;
  $('phase-scene').className=`phase ${phase==='ready'?'done':['designing','compiling'].includes(phase)?'current working':''}`;
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
  const assumptions=[...(data.analysis?.uncertainties || []),...(data.scene_spec?.assumptions || []),...(data.validation?.warnings || [])];
  if(assumptions.length)$('assumptions').innerHTML='<ul>'+assumptions.map(text=>`<li>${esc(text)}</li>`).join('')+'</ul>';
  if(data.validation?.native_manifest_valid && loadedScene!==runId) {
    loadedScene=runId;
    try {
      const manifest=await api(`/api/video-runs/${runId}/scene`);
      if(selected!==runId)return;
      viewer?.dispose();
      viewer=mountScene($('viewport'),manifest,chooseObject);
      const stats=viewer.stats();
      window.workcellEvidence={runId,renderer:'OpenIndustries createWorld',stats};
      $('reset-view').hidden=false;$('render-caption').hidden=false;
      $('render-caption').textContent='Drag to orbit · scroll to zoom · click equipment';
      $('scene-summary').innerHTML=`<h2>${esc(data.scene_spec.title)}</h2><p>${esc(data.scene_spec.rationale)}</p><p><strong>${data.validation.dataset_instances} original dataset sets</strong> · ${data.validation.proposed_instances} proposed equipment objects</p><p class="small">Native scene schema and geometry references checked. Proposed layout only: no collision, reach, force, or physical-execution verification.</p>`;
      $('equipment').innerHTML=data.scene_spec.objects.map(obj=>`<button class="object" data-kind="${esc(obj.kind)}" data-object="${esc(obj.id)}" title="${esc(obj.rationale)}">${obj.kind==='dataset'?'◈':'◇'} ${esc(obj.name)}</button>`).join('');
      $('download').href=`/api/video-runs/${runId}/scene`;$('download').hidden=false;
      $('renderer-status').textContent=`OpenIndustries · ${stats.instances} instances · ${stats.meshes} meshes · proposed layout`;
      if(selectedStep)chooseStep(selectedStep,false);
    } catch(err) {
      loadedScene=null;
      $('viewport').innerHTML='<div class="placeholder"><h2>Renderer could not load.</h2><p>'+esc(err.message)+'</p></div>';
      error(err.message);
    }
  }
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
$('video').addEventListener('timeupdate',()=>{
  if($('video').paused)return;
  const time=$('video').currentTime;
  const step=current?.analysis?.steps.find(s=>s.start_s<=time && s.end_s>=time);
  if(step && step.id!==selectedStep)chooseStep(step.id,false);
});
async function poll(){await refresh();setTimeout(poll,2500);}
poll();
