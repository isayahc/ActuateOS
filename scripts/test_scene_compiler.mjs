import assert from 'node:assert/strict';
import {mkdtempSync,writeFileSync,readFileSync,rmSync} from 'node:fs';
import {spawnSync} from 'node:child_process';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
const folder=mkdtempSync(join(tmpdir(),'workcell-scene-test-'));
const geometry=join(folder,'geometry.json'),specPath=join(folder,'spec.json'),out=join(folder,'scene.json');
const valid={room:[4,3,3],objects:[{id:'bench',name:'Bench',kind:'proposal',position:[0,0,0],rotation:[0,0,0],parts:[{shape:'box',size:[1,.8,.6],position:[0,.4,0],rotation:[0,0,0],color:[.5,.5,.5]}]}]};
writeFileSync(geometry,JSON.stringify({assets:[]}));
function compile(spec){writeFileSync(specPath,JSON.stringify(spec));return spawnSync(process.execPath,['ui/dist/compile-scene.mjs',specPath,geometry,out],{encoding:'utf8'});}
try{
  let result=compile(valid);assert.equal(result.status,0,result.stderr);
  assert.equal(JSON.parse(readFileSync(out,'utf8')).format,'astra.scene');
  assert.equal(JSON.parse(result.stdout).geometry_hydrated,true);
  const unknown=structuredClone(valid);unknown.objects[0]={...unknown.objects[0],kind:'dataset',asset_id:'invented'};
  assert.notEqual(compile(unknown).status,0);
  const duplicate=structuredClone(valid);duplicate.objects.push(duplicate.objects[0]);assert.notEqual(compile(duplicate).status,0);
  const negative=structuredClone(valid);negative.objects[0].parts[0].size[0]=-1;assert.notEqual(compile(negative).status,0);
  const bounds=structuredClone(valid);bounds.objects[0].position=[50,0,0];result=compile(bounds);assert.equal(result.status,0);assert.equal(JSON.parse(result.stdout).warnings.length,1);
  console.log('PASS: native compilation, unknown geometry, duplicate IDs, invalid dimensions, bounds warnings.');
}finally{rmSync(folder,{recursive:true,force:true});}
