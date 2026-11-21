/** Compile Gemini's constrained scene specification using native OpenIndustries APIs. */
import fs from 'node:fs';
import crypto from 'node:crypto';
import * as THREE from 'three';
import {finalizeAsset} from '../.deps/OpenIndustries/src/lib/scene';
import {makeManifest, readManifest, hydrateManifest} from '../.deps/OpenIndustries/src/lib/workspace';

const [specPath, geometryPath, outputPath] = process.argv.slice(2);
if (!outputPath) throw new Error('Usage: compile-scene spec.json geometry.json output.oi.json');
const spec = JSON.parse(fs.readFileSync(specPath, 'utf8'));
const geometry = JSON.parse(fs.readFileSync(geometryPath, 'utf8'));
const vector = (v:any, positive=false) => Array.isArray(v) && v.length===3 && v.every(n=>typeof n==='number' && Number.isFinite(n) && Math.abs(n)<=100 && (!positive || n>0));
if (!vector(spec.room,true) || spec.room.some((n:number)=>n<1 || n>20)) throw new Error('Room must be 1–20 m per axis.');
if (!Array.isArray(spec.objects) || !spec.objects.length || spec.objects.length>30) throw new Error('Expected 1–30 scene objects.');
const ids = new Set();
const items = spec.objects.map((object:any) => {
  if (typeof object.id!=='string' || !/^[a-zA-Z0-9_-]{1,80}$/.test(object.id) || ids.has(object.id)) throw new Error('Invalid/duplicate object ID.');
  ids.add(object.id);
  if (typeof object.name!=='string' || !vector(object.position) || !vector(object.rotation)) throw new Error('Invalid object transform/name.');
  let asset;
  if (object.kind==='dataset') {
    const source = geometry.assets.find((a:any)=>a.id===object.asset_id);
    if (!source) throw new Error(`Unknown dataset asset: ${object.asset_id}`);
    asset = finalizeAsset(structuredClone(source));
  } else if (object.kind==='proposal') {
    if (!Array.isArray(object.parts) || !object.parts.length || object.parts.length>30) throw new Error('Proposal needs 1–30 primitive parts.');
    const parts = object.parts.map((part:any,index:number) => {
      if (!vector(part.size,true) || part.size.some((n:number)=>n>8) || !vector(part.position) || !vector(part.rotation)
        || !vector(part.color) || part.color.some((n:number)=>n<0 || n>1)) throw new Error('Invalid primitive dimensions, pose or RGB color.');
      if (!['box','cylinder'].includes(part.shape)) throw new Error('Only box/cylinder primitives are supported.');
      const mesh = part.shape==='box' ? new THREE.BoxGeometry(...part.size) : new THREE.CylinderGeometry(part.size[0]/2,part.size[0]/2,part.size[1],20);
      if (part.shape==='cylinder') mesh.scale(1,1,part.size[2]/part.size[0]);
      mesh.rotateX(THREE.MathUtils.degToRad(part.rotation[0]));
      mesh.rotateY(THREE.MathUtils.degToRad(part.rotation[1]));
      mesh.rotateZ(THREE.MathUtils.degToRad(part.rotation[2]));
      mesh.translate(...part.position);
      const result = {id:`${object.id}/part-${index}`,name:part.name || `${object.name} ${index+1}`,
        vertices:Array.from(mesh.attributes.position.array),indices:Array.from(mesh.index!.array),color:part.color,
        metadata:{representation:'Gemini-proposed conceptual geometry; not measured',source:'Gemini Managed Agent'}};
      mesh.dispose(); return result;
    });
    asset=finalizeAsset({id:`asset-${object.id}`,name:object.name,
      source:{kind:'generated',filename:'scene-spec.json',digest:crypto.createHash('sha256').update(JSON.stringify(object)).digest('hex'),generator:'oi-fixture'},
      parts,hierarchy:{id:`${object.id}/root`,name:object.name,partIds:parts.map((p:any)=>p.id),children:[]},
      warnings:['Conceptual proposal; dimensions, reachability, contact and machine suitability are unverified.']});
  } else throw new Error('Object kind must be dataset or proposal.');
  return {id:object.id,name:object.name,asset,position:object.position,rotation:object.rotation,visible:true};
});
const workspace={room:spec.room,items,animation:{duration:10,loop:false,tracks:[]}};
const manifest=makeManifest(workspace,true);
const checked=hydrateManifest(readManifest(manifest),[]);
if(checked.items.some(item=>item.missing))throw new Error('Native OI hydration found missing geometry.');
fs.writeFileSync(outputPath,JSON.stringify(manifest));
const warnings:string[]=[];
for(const item of checked.items){
  const bounds=new THREE.Box3();
  const transform=new THREE.Matrix4().compose(new THREE.Vector3(...item.position),new THREE.Quaternion().setFromEuler(new THREE.Euler(...item.rotation.map(THREE.MathUtils.degToRad))),new THREE.Vector3(1,1,1));
  for(const part of item.asset.parts)for(let i=0;i<part.vertices.length;i+=3)bounds.expandByPoint(new THREE.Vector3().fromArray(part.vertices,i).applyMatrix4(transform));
  if(bounds.min.x < -spec.room[0]/2 || bounds.max.x > spec.room[0]/2 || bounds.min.z < -spec.room[1]/2 || bounds.max.z > spec.room[1]/2 || bounds.min.y < -.01 || bounds.max.y > spec.room[2]) warnings.push(`${item.name} extends beyond the proposed room.`);
}
console.log(JSON.stringify({native_manifest_valid:true,geometry_hydrated:true,instances:items.length,
  dataset_instances:spec.objects.filter((o:any)=>o.kind==='dataset').length,proposed_instances:spec.objects.filter((o:any)=>o.kind==='proposal').length,
  renderer:'OpenIndustries createWorld / readManifest / hydrateManifest',revision:'838ea330296148621f7a23f7cb647b11e73b5184',warnings,
  physical_execution_verified:false,scope:'Scene schema and geometry references only; no collision/contact/reach verification.'}));
