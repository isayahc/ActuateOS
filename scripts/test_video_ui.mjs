/** Browser integration check against a completed real run; makes no paid API calls.
 * Start Chromium with --remote-debugging-port=9225 and the app on :5187 first.
 */
import {mkdirSync,writeFileSync} from 'node:fs';
const app=process.env.APP_URL || 'http://127.0.0.1:5187';
const debug=process.env.CHROME_DEBUG_URL || 'http://127.0.0.1:9225';
const page=await(await fetch(`${debug}/json/new?about:blank`,{method:'PUT'})).json();
const ws=new WebSocket(page.webSocketDebuggerUrl);
await new Promise(resolve=>ws.addEventListener('open',resolve,{once:true}));
let next=0;
const pending=new Map(),errors=[];
ws.addEventListener('message',event=>{
  const message=JSON.parse(event.data);
  if(message.id){const [resolve,reject]=pending.get(message.id);pending.delete(message.id);message.error?reject(new Error(JSON.stringify(message.error))):resolve(message.result);}
  if(message.method==='Runtime.exceptionThrown')errors.push(message.params.exceptionDetails);
});
const call=(method,params={})=>new Promise((resolve,reject)=>{const id=++next;pending.set(id,[resolve,reject]);ws.send(JSON.stringify({id,method,params}));});
const evaluate=async expression=>{
  const result=await call('Runtime.evaluate',{expression,returnByValue:true,awaitPromise:true,userGesture:true});
  if(result.exceptionDetails)throw new Error(JSON.stringify(result.exceptionDetails));
  return result.result.value;
};
const wait=async(expression,timeout=60000)=>{
  const deadline=Date.now()+timeout;
  while(Date.now()<deadline){if(await evaluate(expression))return;await new Promise(r=>setTimeout(r,500));}
  throw new Error(`Timeout: ${expression}; UI: ${await evaluate("document.querySelector('#error')?.textContent")}`);
};
try{
  await call('Runtime.enable');await call('Page.enable');
  await call('Emulation.setDeviceMetricsOverride',{width:1600,height:1200,deviceScaleFactor:1,mobile:false});
  await call('Page.navigate',{url:app});
  await wait('window.workcellEvidence?.stats.instances > 0');
  await wait("document.querySelector('#video').readyState >= 2");
  await wait("window.workcellEvidence.playback().engine==='MuJoCo' && window.workcellEvidence.playback().physics!==null");
  await evaluate("document.querySelector('#motion-source').value='storyboard';document.querySelector('#motion-source').dispatchEvent(new Event('change'))");
  const info=await evaluate(`({render:window.workcellEvidence,steps:document.querySelectorAll('.step').length,objects:document.querySelectorAll('.object').length,sourceObjects:document.querySelectorAll('.object[data-kind=dataset]').length,duration:document.querySelector('#video').duration})`);
  if(info.sourceObjects!==4 || info.steps<1 || Math.abs(info.duration-275.4)>.2)throw new Error(JSON.stringify(info));
  await evaluate("document.querySelectorAll('.step')[2].click()");
  await wait("document.querySelector('#video').currentTime > 60 && !document.querySelector('#video').seeking");
  if(!await evaluate("document.querySelectorAll('.object.selected').length>0"))throw new Error('Step did not highlight linked equipment');
  await evaluate("document.querySelector('.object[data-kind=dataset]').click()");
  if(!await evaluate("document.querySelector('#render-caption').textContent.includes('original dataset geometry')"))throw new Error('Object selection failed');
  await evaluate("document.querySelector('#reference').open=true");
  if(await evaluate("document.querySelectorAll('.reference-row').length")!==9)throw new Error('Reference annotations missing');
  const manifest=await evaluate("fetch(document.querySelector('#download').href).then(r=>r.json()).then(m=>({format:m.format,assets:m.bundledAssets.length,vertices:m.bundledAssets.flatMap(a=>a.parts).reduce((n,p)=>n+p.vertices.length/3,0)}))");
  if(manifest.format!=='astra.scene' || manifest.vertices<200000)throw new Error('Native dataset geometry absent');
  const segmentCount=await evaluate("document.querySelectorAll('[data-segment]').length");
  if(segmentCount){
    if(segmentCount!==info.steps)throw new Error('Missing corresponding scene segments');
    for(let index=0;index<segmentCount;index++){
      await evaluate(`document.querySelectorAll('[data-segment]')[${index}].click()`);
      await wait("!document.querySelector('#video').seeking");
      await wait("window.workcellEvidence.playback().time_s < .05 && document.querySelector('#scene-stage').textContent==='BEFORE'");
      const before=await evaluate('window.workcellEvidence.playback()');
      await evaluate("document.querySelector('#segment-scrub').value=1000;document.querySelector('#segment-scrub').dispatchEvent(new Event('input'))");
      await wait("!document.querySelector('#video').seeking && document.querySelector('#scene-stage').textContent==='AFTER'");
      const after=await evaluate('window.workcellEvidence.playback()');
      if(before.step_id!==after.step_id || JSON.stringify(before.objects)===JSON.stringify(after.objects))throw new Error('Scene segment did not change: '+JSON.stringify({index,before,after}));
      const exported=await evaluate("fetch(document.querySelector('#download-segment').href).then(r=>r.json())");
      if(!exported.animation.tracks.length || Math.abs(after.time_s-exported.animation.duration)>.1)throw new Error('Segment clock/export mismatch');
    }
    await evaluate("document.querySelectorAll('[data-segment]')[0].click();document.querySelector('#segment-scrub').value=995;document.querySelector('#segment-scrub').dispatchEvent(new Event('input'))");
    await wait("!document.querySelector('#video').seeking");
    await evaluate("document.querySelector('#play-segment').click()");
    await wait("document.querySelector('#video').paused && document.querySelector('#scene-stage').textContent==='AFTER'");
    await evaluate("document.querySelector('#loop-segment').checked=true;document.querySelector('#segment-scrub').value=995;document.querySelector('#segment-scrub').dispatchEvent(new Event('input'))");
    await wait("!document.querySelector('#video').seeking");
    await evaluate("document.querySelector('#play-segment').click()");
    await wait("!document.querySelector('#video').paused && window.workcellEvidence.playback().time_s<2");
    await evaluate("document.querySelector('#video').pause();document.querySelector('#loop-segment').checked=false");
    const review=await evaluate("fetch('/api/video-runs/'+window.workcellEvidence.runId).then(r=>r.json()).then(r=>r.segment_comparison)");
    if(review){
      if(review.segments.length!==segmentCount)throw new Error('Visual comparison coverage incomplete');
      await evaluate("document.querySelectorAll('#segment-review img').forEach(image=>image.loading='eager')");
      await wait("document.querySelectorAll('#segment-review img').length===4 && [...document.querySelectorAll('#segment-review img')].every(image=>image.complete && image.naturalWidth>0)");
    }
  }
  await evaluate("document.querySelector('#reference').open=false;document.querySelector('#reset-view').click();document.querySelector('#video').currentTime=152.24");
  await wait("!document.querySelector('#video').seeking");
  await evaluate("document.querySelectorAll('[data-segment]')[0].click();document.querySelector('#motion-source').value='mujoco';document.querySelector('#motion-source').dispatchEvent(new Event('change'))");
  await wait("window.workcellEvidence.playback().engine==='MuJoCo' && window.workcellEvidence.playback().physics!==null");
  await evaluate("document.querySelector('#play-segment').click()");
  await wait("window.workcellEvidence.playback().physics.steps>=200 && document.querySelector('#runtime-status').textContent.includes('running')");
  await evaluate("document.querySelector('#video').pause()");
  await wait("Math.abs(window.workcellEvidence.playback().time_s-document.querySelector('#video').currentTime)<.02");
  const physics=await evaluate('window.workcellEvidence.playback()');
  if(physics.engine!=='MuJoCo' || physics.physics.steps<200)throw new Error('No real MuJoCo state reached OI');
  await evaluate("document.querySelector('#segment-scrub').value=0;document.querySelector('#segment-scrub').dispatchEvent(new Event('input'))");
  await wait("window.workcellEvidence.playback().physics.steps===0");
  await evaluate("document.querySelectorAll('[data-segment]')[4].click();document.querySelector('#segment-scrub').value=500;document.querySelector('#segment-scrub').dispatchEvent(new Event('input'))");
  await wait("window.workcellEvidence.playback().step_id==='step_5' && window.workcellEvidence.playback().physics?.steps>1000");
  mkdirSync('artifacts/ui-evidence',{recursive:true});
  let image=await call('Page.captureScreenshot',{format:'png'});
  writeFileSync('artifacts/ui-evidence/video-workcell-desktop.png',Buffer.from(image.data,'base64'));
  await call('Emulation.setDeviceMetricsOverride',{width:390,height:844,deviceScaleFactor:1,mobile:true});
  await evaluate('new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)))');
  if(!await evaluate('document.documentElement.scrollWidth <= 390'))throw new Error('Mobile page overflow');
  image=await call('Page.captureScreenshot',{format:'png'});
  writeFileSync('artifacts/ui-evidence/video-workcell-mobile.png',Buffer.from(image.data,'base64'));
  if(errors.length)throw new Error(JSON.stringify(errors));
  writeFileSync('artifacts/ui-evidence/browser-checks.json',JSON.stringify({passed:true,...info,manifest,physics,errors},null,2));
  console.log('PASS: live MuJoCo poses/step counters/play/pause/rewind/segment switching, storyboard segments, exports, stop/loop, comparison images and mobile layout.');
}finally{ws.close();await fetch(`${debug}/json/close/${page.id}`);}
