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
  const result=await call('Runtime.evaluate',{expression,returnByValue:true,awaitPromise:true});
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
  await evaluate("document.querySelector('#reference').open=false;document.querySelector('#reset-view').click();document.querySelector('#video').currentTime=152.24");
  await wait("!document.querySelector('#video').seeking");
  mkdirSync('artifacts/ui-evidence',{recursive:true});
  let image=await call('Page.captureScreenshot',{format:'png'});
  writeFileSync('artifacts/ui-evidence/video-workcell-desktop.png',Buffer.from(image.data,'base64'));
  await call('Emulation.setDeviceMetricsOverride',{width:390,height:844,deviceScaleFactor:1,mobile:true});
  await evaluate('new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)))');
  if(!await evaluate('document.documentElement.scrollWidth <= 390'))throw new Error('Mobile page overflow');
  image=await call('Page.captureScreenshot',{format:'png'});
  writeFileSync('artifacts/ui-evidence/video-workcell-mobile.png',Buffer.from(image.data,'base64'));
  if(errors.length)throw new Error(JSON.stringify(errors));
  writeFileSync('artifacts/ui-evidence/browser-checks.json',JSON.stringify({passed:true,...info,manifest,errors},null,2));
  console.log('PASS: real source video, native OpenIndustries WebGL scene, original dataset geometry, step-to-video seeking, equipment highlighting, 9 withheld reference labels, portable export, mobile layout.');
}finally{ws.close();}
