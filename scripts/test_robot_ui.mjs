/** Offline native OI + HTTP + real MuJoCo task execution; no provider calls. */
import assert from 'node:assert/strict';
import {spawn, execFileSync} from 'node:child_process';
import {randomUUID} from 'node:crypto';
import {mkdtempSync, rmSync, readFileSync, writeFileSync} from 'node:fs';
import {tmpdir} from 'node:os';
import path from 'node:path';

const python=path.resolve('.venv-mujoco/bin/python');
const freePort=()=>Number(execFileSync(python,['-c','import socket; s=socket.socket(); s.bind(("127.0.0.1",0)); print(s.getsockname()[1]); s.close()'],{encoding:'utf8'}).trim());
const port=freePort(), debugPort=freePort(), app=`http://127.0.0.1:${port}`, debug=`http://127.0.0.1:${debugPort}`;
const run=randomUUID().replaceAll('-',''), folder=path.resolve('artifacts/video-workcells',run), profile=mkdtempSync(path.join(tmpdir(),'workcell-browser-'));
let server,chrome,ws,evidenceId,startupError;
let startupLogs="";
function monitor(child, name){child.stderr?.on("data",data=>{startupLogs=(startupLogs+String(data)).slice(-3000);});child.on("error",error=>{startupError=`${name}: ${error.message}`;});child.on("exit",code=>{startupError=`${name} exited (${code}): ${startupLogs}`;});}
const errors=[],pending=new Map();let sequence=0;
const evidenceIds=new Set();
const sleep=ms=>new Promise(resolve=>setTimeout(resolve,ms));
async function until(fn, timeout=30000){const deadline=Date.now()+timeout;while(Date.now()<deadline){if(startupError)throw new Error(startupError);if(await fn())return;await sleep(100);}throw new Error('Timed out waiting for browser/runtime');}
const call=(method,params={})=>new Promise((resolve,reject)=>{const id=++sequence;pending.set(id,{resolve,reject});ws.send(JSON.stringify({id,method,params}));});
async function evaluate(expression){const r=await call('Runtime.evaluate',{expression,returnByValue:true,awaitPromise:true});if(r.exceptionDetails)throw new Error(JSON.stringify(r.exceptionDetails));return r.result.value;}
const snapshot=()=>evaluate('window.workcellEvidence?.playback()');
try{
  execFileSync(python,['scripts/prepare_test_workcell.py',folder]);
  server=spawn(python,['ui/server.py','--port',String(port)],{stdio:['ignore','pipe','pipe']});monitor(server,'HTTP server');
  chrome=spawn(process.env.CHROMIUM_BIN||'chromium',['--headless','--no-sandbox','--disable-dev-shm-usage','--use-angle=swiftshader','--enable-unsafe-swiftshader',`--remote-debugging-port=${debugPort}`,`--user-data-dir=${profile}`],{stdio:['ignore','ignore','pipe']});monitor(chrome,'Chromium');
  await until(async()=>{try{return (await fetch(`${app}/api/runtime`)).ok&&(await fetch(`${debug}/json/version`)).ok;}catch{return false;}});
  const tab=await(await fetch(`${debug}/json/new?about:blank`,{method:'PUT'})).json();
  ws=new WebSocket(tab.webSocketDebuggerUrl);
  await new Promise(resolve=>ws.addEventListener('open',resolve,{once:true}));
  ws.addEventListener('message',event=>{const m=JSON.parse(event.data);if(m.id){const p=pending.get(m.id);pending.delete(m.id);if(p)m.error?p.reject(new Error(JSON.stringify(m.error))):p.resolve(m.result);}if(m.method==='Runtime.exceptionThrown')errors.push(m.params);});
  await call('Runtime.enable');await call('Page.enable');
  // Stub only the provider boundary: the UI must request Gemini by default,
  // but the offline test dispatches the same real physics tasks without a key.
  await call('Page.addScriptToEvaluateOnNewDocument',{source:`
    const originalFetch=window.fetch.bind(window);
    window.fetch=(url,options)=>{
      if(url==='/api/runtime/robot-agent'){
        sessionStorage.setItem('agentRequests',String(Number(sessionStorage.getItem('agentRequests')||0)+1));
        return originalFetch('/api/runtime/robot-start',options);
      }
      return originalFetch(url,options);
    };`});
  await call('Page.navigate',{url:`${app}/?run=${run}`});
  await until(async()=>(await snapshot())?.physics?.mode==='robot');
  assert((await snapshot()).physics.robot_meshes>10);
  assert.equal(await evaluate("document.querySelector('#advanced-inspection').open"),false);
  await until(()=>evaluate("document.querySelector('#play-segment').textContent.includes('Play segment') && !document.querySelector('#play-segment').disabled"));
  await evaluate("document.querySelector('#play-segment').click();document.querySelector('#play-segment').click()");
  await until(async()=>(await snapshot())?.physics?.steps>50);
  assert.equal(await evaluate("sessionStorage.getItem('agentRequests')"),'1');
  assert(await evaluate("document.querySelector('#video').paused && document.querySelector('#error').hidden"));
  await evaluate("document.querySelector('#play-segment').click()");
  await until(async()=>(await snapshot())?.physics?.running===false);
  const paused=await snapshot();await sleep(250);
  assert.equal((await snapshot()).time_s,paused.time_s);
  await evaluate("document.querySelector('[data-segment=observed_beta]').click()");
  await sleep(200);assert.equal((await snapshot()).time_s,paused.time_s,'Selecting a reference task must not reset physics');
  await evaluate("document.querySelector('#play-segment').click()");
  await until(async()=>(await snapshot())?.time_s>paused.time_s);
  evidenceId=await evaluate("document.querySelector('#robot-review a').href.split('/').at(-2)");
  evidenceIds.add(evidenceId);
  const before=await snapshot();
  await call('Page.navigate',{url:'about:blank'});await sleep(500);
  await call('Page.navigate',{url:`${app}/?run=${run}`});
  await until(async()=>(await snapshot())?.physics?.steps>before.physics.steps);
  assert.equal(await evaluate("document.querySelector('#robot-review a').href.split('/').at(-2)"),evidenceId,'Reconnect must retain the same execution');
  await until(async()=>(await snapshot())?.physics?.phase==='completed',90000);
  const saved=JSON.parse(readFileSync(path.resolve('artifacts/robot-executions',evidenceId,'state.json'),'utf8'));
  assert.deepEqual(saved.tasks.map(t=>t.status),['succeeded','succeeded']);
  assert.equal((await snapshot()).physics.result.passed,true);
  await until(()=>evaluate("document.querySelector('#play-segment').textContent.includes('Run again')"));
  await evaluate("document.querySelector('#play-segment').click()");
  await until(async()=>{
    const id=await evaluate("document.querySelector('#robot-review a')?.href.split('/').at(-2)");
    if(id && id!==evidenceId){evidenceIds.add(id);return (await snapshot())?.physics?.steps>0;}
    return false;
  });
  assert.equal(await evaluate("sessionStorage.getItem('agentRequests')"),'2','Run again must replace the terminal execution exactly once');
  await evaluate("document.querySelector('#play-segment').click()");
  await until(async()=>(await snapshot())?.physics?.running===false);
  const planPath=path.join(folder,'runtime-plan.json'),plan=JSON.parse(readFileSync(planPath,'utf8'));
  plan.initial_positions={};plan.tasks.forEach(task=>{task.skill='unsupported';task.reason='No assembly controller in offline fixture';});
  writeFileSync(planPath,JSON.stringify(plan));
  await evaluate("document.querySelector('#advanced-inspection').open=true;document.querySelector('#reconnect-runtime').click()");
  await until(()=>evaluate("document.querySelector('#play-segment').disabled && document.querySelector('#play-segment').textContent.includes('not implemented')"));
  evidenceIds.add(await evaluate("document.querySelector('#robot-review a').href.split('/').at(-2)"));
  assert.equal(await evaluate("sessionStorage.getItem('agentRequests')"),'2','Unsupported tasks must not trigger a provider request');
  await call('Emulation.setDeviceMetricsOverride',{width:390,height:844,deviceScaleFactor:1,mobile:true});
  await sleep(200);assert(await evaluate('document.documentElement.scrollWidth<=390'),'Mobile overflow');
  assert.deepEqual(errors,[]);
  console.log('PASS: primary Play/provider routing, duplicate-click guard, two real physics tasks, same-button pause/resume, persistent selection/reconnect, rerun, unsupported guard and mobile layout (provider stubbed).');
}finally{
  ws?.close();chrome?.kill();server?.kill('SIGINT');
  await sleep(500);
  rmSync(folder,{recursive:true,force:true});
  for(const id of evidenceIds)rmSync(path.resolve('artifacts/robot-executions',id),{recursive:true,force:true});
  rmSync(profile,{recursive:true,force:true});
}
