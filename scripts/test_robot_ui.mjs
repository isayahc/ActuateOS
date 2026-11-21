/** Offline native OI + HTTP + real MuJoCo task execution; no provider calls. */
import assert from 'node:assert/strict';
import {spawn, execFileSync} from 'node:child_process';
import {randomUUID} from 'node:crypto';
import {mkdtempSync, rmSync, readFileSync} from 'node:fs';
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
  await call('Page.navigate',{url:`${app}/?run=${run}`});
  await until(async()=>(await snapshot())?.physics?.mode==='robot');
  assert((await snapshot()).physics.robot_meshes>10);
  await evaluate("document.querySelector('#robot-run').click()");
  await until(async()=>(await snapshot())?.physics?.steps>50);
  await evaluate("document.querySelector('#robot-pause').click()");
  await until(async()=>(await snapshot())?.physics?.running===false);
  const paused=await snapshot();await sleep(250);
  assert.equal((await snapshot()).time_s,paused.time_s);
  await evaluate("document.querySelector('[data-segment=observed_beta]').click()");
  await sleep(200);assert.equal((await snapshot()).time_s,paused.time_s,'Selecting a reference task must not reset physics');
  await evaluate("document.querySelector('#robot-pause').click()");
  await until(async()=>(await snapshot())?.time_s>paused.time_s);
  evidenceId=await evaluate("document.querySelector('#robot-review a').href.split('/').at(-2)");
  const before=await snapshot();
  await call('Page.navigate',{url:'about:blank'});await sleep(500);
  await call('Page.navigate',{url:`${app}/?run=${run}`});
  await until(async()=>(await snapshot())?.physics?.steps>before.physics.steps);
  assert.equal(await evaluate("document.querySelector('#robot-review a').href.split('/').at(-2)"),evidenceId,'Reconnect must retain the same execution');
  await until(async()=>(await snapshot())?.physics?.phase==='completed',90000);
  const saved=JSON.parse(readFileSync(path.resolve('artifacts/robot-executions',evidenceId,'state.json'),'utf8'));
  assert.deepEqual(saved.tasks.map(t=>t.status),['succeeded','succeeded']);
  assert.equal((await snapshot()).physics.result.passed,true);
  await call('Emulation.setDeviceMetricsOverride',{width:390,height:844,deviceScaleFactor:1,mobile:true});
  await sleep(200);assert(await evaluate('document.documentElement.scrollWidth<=390'),'Mobile overflow');
  assert.deepEqual(errors,[]);
  console.log('PASS: native OI renderer, two runtime tasks, pause/resume, task selection, background execution, reconnect, measured results, mobile layout.');
}finally{
  ws?.close();chrome?.kill();server?.kill('SIGINT');
  await sleep(500);
  rmSync(folder,{recursive:true,force:true});
  if(evidenceId)rmSync(path.resolve('artifacts/robot-executions',evidenceId),{recursive:true,force:true});
  rmSync(profile,{recursive:true,force:true});
}
