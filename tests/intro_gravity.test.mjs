import test from 'node:test';
import assert from 'node:assert/strict';
import {makeGravitySeeds,fieldPoint,fieldStrength} from '../paperscientist/static/intro/gravity.mjs';
import {workCamera} from '../paperscientist/static/intro/work-layout.mjs';
import {createConstellation} from '../paperscientist/static/intro/constellation.js';

test('fixed particle orbits remain finite at all camera phases and retrace the same focus path',()=>{
 const seeds=makeGravitySeeds();assert.equal(seeds.length,420);assert.deepEqual(seeds,makeGravitySeeds());
 assert.equal(fieldStrength(workCamera(5)),1);assert.equal(fieldStrength(workCamera(6)),0);
 assert.equal(fieldStrength(workCamera(8)),0);assert.equal(fieldStrength(workCamera(9)),1);
 for(const [w,h] of [[390,844],[1280,720],[3840,2160]])for(let n=0;n<=20;n++){
  const cam=workCamera(5+n/20),reverse=workCamera(9-n/20);
  for(const seed of seeds){const p=fieldPoint(seed,12,cam,w,h),q=fieldPoint(seed,12,reverse,w,h);assert.ok(Object.values(p).every(Number.isFinite));assert.ok(Math.abs(p.x-q.x)<1e-5&&Math.abs(p.y-q.y)<1e-5);}
 }
});

test('4K constellation resizes reuse geometry and dispose every GPU resource',()=>{
 const atlas=createConstellation(),geometry=[],materials=[];
 atlas.group.traverse(n=>{if(n.geometry)geometry.push(n.geometry);if(n.material)materials.push(n.material);});
 const arrays=geometry.map(g=>g.attributes.position.array);let released=0;
 [...geometry,...materials].forEach(r=>r.addEventListener('dispose',()=>released++));
 for(const [w,h,dpr] of [[1280,720,1],[3840,2160,1],[390,844,2]]){
  atlas.resize(w,h,dpr);atlas.render(1,18);
  geometry.forEach((g,i)=>{assert.equal(g.attributes.position.array,arrays[i]);assert.ok([...arrays[i]].every(Number.isFinite));});
 }
 atlas.render(0,18);assert.equal(atlas.group.visible,false);atlas.dispose();assert.equal(released,geometry.length+materials.length);
});
