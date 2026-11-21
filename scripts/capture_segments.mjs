/** Capture the actual native OI before/after renders, rather than inferred scene descriptions. */
import {spawn} from 'node:child_process';
import {existsSync,mkdtempSync,readFileSync,writeFileSync,mkdirSync,rmSync} from 'node:fs';
import {tmpdir} from 'node:os';
import path from 'node:path';
const [runId]=process.argv.slice(2);
if(!/^[0-9a-f]{32}$/.test(runId))throw new Error('Invalid run ID');
const app=process.env.APP_URL||'http://127.0.0.1:5187';
const folder=path.resolve('artifacts/video-workcells',runId);
const segments=JSON.parse(readFileSync(path.join(folder,'segments.json'),'utf8')).segments;
const output=path.join(folder,'segment-evidence');mkdirSync(output,{recursive:true});
const profile=mkdtempSync(path.join(existsSync('/tmp/opencode')?'/tmp/opencode':tmpdir(),'oi-segments-'));
const browser=spawn(process.env.CHROMIUM_BIN||'chromium',['--headless','--no-sandbox','--use-gl=angle','--use-angle=swiftshader','--enable-unsafe-swiftshader','--remote-debugging-port=0',`--user-data-dir=${profile}`,'about:blank'],{stdio:['ignore','ignore','pipe']});
let diagnostics='';browser.stderr.on('data',chunk=>{diagnostics=(diagnostics+chunk).slice(-4000);});
browser.on('error',error=>{diagnostics=error.message;});
const sleep=ms=>new Promise(resolve=>setTimeout(resolve,ms));
let ws;
try{
  const portFile=path.join(profile,'DevToolsActivePort');
  for(let i=0;i<120&&!existsSync(portFile)&&!diagnostics.match(/DevTools listening on ws:\/\/127\.0\.0\.1:(\d+)/);i++){if(browser.exitCode!==null)throw new Error(diagnostics);await sleep(250);}
  const port=existsSync(portFile)?readFileSync(portFile,'utf8').split('\n')[0]:diagnostics.match(/DevTools listening on ws:\/\/127\.0\.0\.1:(\d+)/)?.[1];
  if(!port)throw new Error('Chromium did not start: '+diagnostics);
  const page=await(await fetch(`http://127.0.0.1:${port}/json/new?about:blank`,{method:'PUT'})).json();
  ws=new WebSocket(page.webSocketDebuggerUrl);await new Promise(resolve=>ws.addEventListener('open',resolve,{once:true}));
  let next=0;const pending=new Map();
  ws.addEventListener('message',event=>{const message=JSON.parse(event.data);if(message.id){const entry=pending.get(message.id);if(!entry)return;pending.delete(message.id);clearTimeout(entry.timer);message.error?entry.reject(new Error(JSON.stringify(message.error))):entry.resolve(message.result);}});
  const call=(method,params={})=>new Promise((resolve,reject)=>{const id=++next;const timer=setTimeout(()=>{pending.delete(id);reject(new Error(`CDP timeout: ${method}`));},60000);pending.set(id,{resolve,reject,timer});ws.send(JSON.stringify({id,method,params}));});
  const evaluate=async expression=>{const value=await call('Runtime.evaluate',{expression,returnByValue:true,awaitPromise:true});if(value.exceptionDetails)throw new Error(JSON.stringify(value.exceptionDetails));return value.result.value;};
  await call('Page.enable');await call('Runtime.enable');
  await call('Emulation.setDeviceMetricsOverride',{width:960,height:720,deviceScaleFactor:1,mobile:false});
  await call('Page.navigate',{url:`${app}/scene-capture?run=${runId}`});
  let ready=false;
  for(let i=0;i<120;i++){if(await evaluate('window.captureReady===true')){ready=true;break;}await sleep(500);}
  if(!ready)throw new Error('Native scene capture page failed to load');
  const records=[];
  for(const segment of segments)for(const [phase,progress]of [['before',0],['after',1]]){
    const snapshot=await evaluate(`window.captureSegment(${JSON.stringify(segment.step_id)},${progress})`);
    const screenshot=await call('Page.captureScreenshot',{format:'png'});
    const filename=`scene-${segment.step_id}-${phase}.png`;
    writeFileSync(path.join(output,filename),Buffer.from(screenshot.data,'base64'));
    records.push({step_id:segment.step_id,phase,file:filename,snapshot});
  }
  writeFileSync(path.join(output,'render-captures.json'),JSON.stringify(records,null,2));
  console.log(`Captured ${records.length} actual OpenIndustries segment endpoint renders.`);
}finally{ws?.close();browser.kill('SIGTERM');await new Promise(resolve=>{if(browser.exitCode!==null)resolve();else{browser.once('exit',resolve);setTimeout(resolve,5000);}});rmSync(profile,{recursive:true,force:true,maxRetries:5,retryDelay:200});}
