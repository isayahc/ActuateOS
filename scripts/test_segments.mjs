/** Negative structural checks against a real agent-authored storyboard; no API calls. */
import {mkdtempSync,copyFileSync,readFileSync,writeFileSync,rmSync} from 'node:fs';
import {spawnSync} from 'node:child_process';
import path from 'node:path';
const source=path.resolve('artifacts/video-workcells',process.argv[2]||'7ab1900b51ad4600ba9305d9d345a111');
const dir=mkdtempSync('/tmp/opencode/segment-test-');
try{
  for(const file of ['analysis.json','scene-spec.json'])copyFileSync(path.join(source,file),path.join(dir,file));
  const original=JSON.parse(readFileSync(path.join(source,'segments-spec.json'),'utf8'));
  const cases=[
    ['valid',()=>{},null],
    ['coverage',s=>s.segments.pop(),'Exactly one scene segment'],
    ['continuity',s=>s.segments[1].tracks[0].keys[0].position[0]+=.1,'State discontinuity'],
    ['mapping',s=>s.segments[0].object_mapping[0].scene_object_ids=['missing'],'Invalid object correspondence'],
    ['static',s=>{for(const t of s.segments[0].tracks)t.keys=t.keys.map(k=>({...structuredClone(t.keys[0]),progress:k.progress}));},'no actual pose'],
  ];
  for(const [name,edit,error]of cases){
    const spec=structuredClone(original);edit(spec);
    writeFileSync(path.join(dir,'segments-spec.json'),JSON.stringify(spec));
    const result=spawnSync(process.execPath,['ui/dist/compile-segments.mjs',dir,path.resolve('data/industreal/geometry.json')],{encoding:'utf8',timeout:120000});
    if(error?result.status===0||!result.stderr.includes(error):result.status!==0)throw new Error(`${name}: ${result.stderr}`);
  }
  console.log('PASS: segment coverage, native timelines, continuity, invalid mappings and nonchanging tracks.');
}finally{rmSync(dir,{recursive:true,force:true});}
