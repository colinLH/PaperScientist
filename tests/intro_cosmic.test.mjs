import test from 'node:test';
import assert from 'node:assert/strict';
import {createPrelude,globeSeeds,globePoint,preludeOpacity,artRatio} from '../paperscientist/static/intro/cosmic-art.mjs';
import {createConstellation} from '../paperscientist/static/intro/constellation.js';

test('opening artwork has a fixed sphere budget and finite projections at every viewport',()=>{
 const seeds=globeSeeds();assert.equal(seeds.length,2400);assert.deepEqual(seeds,globeSeeds());
 assert.ok(seeds.some(p=>p.land)&&seeds.some(p=>!p.land));
 for(const time of [0,20,1000])for(const p of seeds){const q=globePoint(p,time);assert.ok(Object.values(q).every(Number.isFinite));assert.ok(Math.abs(Math.hypot(q.x,q.y,q.z)-1)<1e-12);}
 for(const [w,h] of [[390,844],[1280,720],[3840,2160]])assert.ok(w*h*artRatio(w,h,3)**2<=2200001);
 assert.equal(preludeOpacity(2),1);assert.equal(preludeOpacity(3),0);
});

test('new opening stops hidden drawing, reduces motion deterministically, and releases its canvas',()=>{
 Object.assign(globalThis,{innerWidth:1280,innerHeight:720,devicePixelRatio:1});
 let calls=[];const ctx={globalAlpha:1,save(){},restore(){},createLinearGradient(){return {addColorStop(){}};},createRadialGradient(){return {addColorStop(){}};}};
 for(const key of ['setTransform','fillRect','beginPath','moveTo','lineTo','closePath','fill','stroke','arc','ellipse','translate','rotate','clip'])ctx[key]=(...args)=>{assert.ok(args.every(Number.isFinite));calls.push([key,...args]);};
 const canvas={getContext:()=>ctx,style:{},dataset:{}};const art=createPrelude(canvas);
 for(const p of [0,.5,1,1.5,2]){calls=[];art.render(p,0,true);assert.ok(calls.length>100);const first=JSON.stringify(calls);calls=[];art.render(p,30,true);assert.equal(JSON.stringify(calls),first);}
 calls=[];art.render(4,30);assert.equal(calls.length,0);assert.equal(canvas.hidden,true);
 art.dispose();assert.equal(canvas.width*canvas.height,1);
});

test('star-map signals move along edges without reallocating geometry and stay static at fixed time',()=>{
 const atlas=createConstellation();let signals;
 atlas.group.traverse(n=>{if(n.geometry?.attributes.position.usage===35048)signals=n.geometry.attributes.position;});
 assert.ok(signals);const array=signals.array;atlas.render(1,0);const before=Array.from(array);
 atlas.render(1,2);assert.equal(signals.array,array);assert.notDeepEqual(Array.from(array),before);assert.ok([...array].every(Number.isFinite));
 const still=Array.from(array);atlas.render(1,2);assert.deepEqual(Array.from(array),still);atlas.dispose();
});
