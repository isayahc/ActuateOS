import * as THREE from 'three';
import {OrbitControls} from 'three/addons/controls/OrbitControls.js';
import {createWorld,applyWorldPoses} from '../.deps/OpenIndustries/src/lib/world';
import {readManifest,hydrateManifest,evaluateWorkspace} from '../.deps/OpenIndustries/src/lib/workspace';

export function mountScene(container:HTMLElement, manifest:any, onSelect:(id:string)=>void) {
  const workspace=hydrateManifest(readManifest(manifest),[]);
  const world=createWorld(workspace.items.map(item=>item.asset),workspace.room,-1,-1,evaluateWorkspace(workspace.items,workspace.animation,null));
  const robotVisual=new THREE.Group();world.scene.add(robotVisual);
  const robotMeshes=new Map<number,THREE.Mesh>();
  const renderer=new THREE.WebGLRenderer({antialias:true,alpha:false});
  renderer.setPixelRatio(Math.min(devicePixelRatio,2));
  renderer.outputColorSpace=THREE.SRGBColorSpace;
  renderer.toneMapping=THREE.ACESFilmicToneMapping;
  renderer.toneMappingExposure=1.1;
  container.replaceChildren(renderer.domElement);
  const camera=new THREE.PerspectiveCamera(40,1,.01,200);
  const size=Math.max(workspace.room[0],workspace.room[1]);
  const controls=new OrbitControls(camera,renderer.domElement);
  controls.enableDamping=true; controls.maxDistance=30;controls.minDistance=.2;
  const home=()=>{camera.position.set(size*.85,size*.65,size*.95);controls.target.set(0,.55,0);controls.update();};
  home();
  const resize=new ResizeObserver(()=>{const w=container.clientWidth,h=container.clientHeight;renderer.setSize(w,h,false);camera.aspect=w/h;camera.updateProjectionMatrix();});
  resize.observe(container);
  const ray=new THREE.Raycaster();
  let down:[number,number]=[0,0];
  renderer.domElement.addEventListener('pointerdown',e=>{down=[e.clientX,e.clientY];});
  renderer.domElement.addEventListener('pointerup',e=>{
    if(Math.hypot(e.clientX-down[0],e.clientY-down[1])>5)return;
    const rect=renderer.domElement.getBoundingClientRect();
    ray.setFromCamera(new THREE.Vector2((e.clientX-rect.left)/rect.width*2-1,1-(e.clientY-rect.top)/rect.height*2),camera);
    const hit=ray.intersectObjects(world.groups,true)[0];
    if(hit){let group=hit.object;while(group.parent && !world.groups.includes(group as any))group=group.parent;const index=world.groups.indexOf(group as any);if(index>=0)onSelect(workspace.items[index].id);}
  });
  let frame=0;
  let segment:any=null, segmentItems=workspace.items, localTime=0;
  let clock:(()=>number)|null=null;
  let physicsMode=false, physicsState:any=null;
  const updatePose=()=>{
    if(physicsMode)return;
    if(segment){
      if(clock)localTime=Math.max(0,Math.min(segment.duration_s,clock()));
      applyWorldPoses(world.groups,evaluateWorkspace(segmentItems,segment.animation,localTime));
    }
  };
  const tick=()=>{updatePose();controls.update();renderer.render(world.scene,camera);frame=requestAnimationFrame(tick);};tick();
  return {
    home,
    setPhysicsMode(enabled:boolean){physicsMode=enabled;physicsState=null;robotVisual.visible=false;},
    setPhysicsState(state:any){
      if(!physicsMode || state.step_id!==segment?.step_id)return;
      physicsState=state;localTime=state.time_s;
      const poses=new Map(state.objects.map((item:any)=>[item.id,item]));
      world.groups.forEach((group,index)=>{
        const pose:any=poses.get(workspace.items[index].id);if(!pose)return;
        group.position.fromArray(pose.position);group.quaternion.fromArray(pose.quaternion);group.visible=pose.visible;
      });
      robotVisual.visible=state.mode==='robot';
      for(const geom of state.robot_geoms || []){
        let mesh=robotMeshes.get(geom.id);
        if(!mesh){
          const geometry=geom.type===2?new THREE.SphereGeometry(geom.size[0],16,12):geom.type===3?
            new THREE.CapsuleGeometry(geom.size[0],geom.size[1]*2,6,16).rotateX(Math.PI/2):
            new THREE.BoxGeometry(geom.size[0]*2,geom.size[1]*2,geom.size[2]*2);
          mesh=new THREE.Mesh(geometry,new THREE.MeshStandardMaterial({color:new THREE.Color(...geom.color),roughness:.65}));
          robotMeshes.set(geom.id,mesh);robotVisual.add(mesh);
        }
        mesh.position.fromArray(geom.position);mesh.quaternion.fromArray(geom.quaternion);
      }
    },
    setSegment(next:any){
      segment=next;localTime=0;
      if(!next){segmentItems=workspace.items;applyWorldPoses(world.groups,evaluateWorkspace(workspace.items,workspace.animation,null));return;}
      const poses=new Map(next.instances.map((item:any)=>[item.id,item]));
      segmentItems=workspace.items.map(item=>({...item,...(poses.get(item.id) as any)}));
      if(physicsMode)applyWorldPoses(world.groups,evaluateWorkspace(segmentItems,next.animation,0));
      updatePose();
    },
    setTime(seconds:number){localTime=Math.max(0,Math.min(segment?.duration_s??0,seconds));updatePose();},
    setClock(source:(()=>number)|null){clock=source;},
    focusSegment(){
      const fixture=workspace.items.find(item=>item.id.includes('fixture'));
      const target=fixture?new THREE.Vector3(...fixture.position).add(new THREE.Vector3(0,.12,0)):new THREE.Vector3(0,.9,0);
      controls.target.copy(target);camera.position.copy(target).add(new THREE.Vector3(.65,.55,.8));controls.update();
    },
    focusRobot(){controls.target.set(0,.95,0);camera.position.set(1.3,1.75,1.65);controls.update();},
    snapshot(){return {step_id:segment?.step_id??null,time_s:localTime,engine:physicsMode?'MuJoCo':'OI storyboard',physics:physicsState?{steps:physicsState.steps,contacts:physicsState.contacts,max_tracking_error_m:physicsState.max_tracking_error_m,mode:physicsState.mode,joints:physicsState.joints,phase:physicsState.phase,running:physicsState.running,result:physicsState.result,robot_meshes:robotMeshes.size}:null,objects:world.groups.map((group,index)=>({id:workspace.items[index].id,position:group.position.toArray(),rotation:[group.rotation.x,group.rotation.y,group.rotation.z],visible:group.visible}))};},
    highlight(ids:string[]){world.groups.forEach((group,index)=>group.traverse((child:any)=>{if(child.material?.emissive){child.material.emissive.set(ids.includes(workspace.items[index].id)?'#506e20':'#000000');child.material.emissiveIntensity=.65;}}));},
    stats:()=>world.resourceStats(),
    dispose(){cancelAnimationFrame(frame);resize.disconnect();controls.dispose();for(const mesh of robotMeshes.values()){mesh.geometry.dispose();(mesh.material as THREE.Material).dispose();}robotVisual.removeFromParent();world.dispose();renderer.dispose();container.replaceChildren();},
  };
}
