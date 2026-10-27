import test from 'node:test';
import assert from 'node:assert/strict';
import {createPrelude,globeSeeds,globePoint,preludeOpacity,artRatio,narrativePoint,narrativePath} from '../paperscientist/static/intro/cosmic-art.mjs';
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
 for(const key of ['clearRect','strokeRect','bezierCurveTo','setTransform','fillRect','beginPath','moveTo','lineTo','closePath','fill','stroke','arc','ellipse','translate','rotate','clip'])ctx[key]=(...args)=>{assert.ok(args.every(Number.isFinite));calls.push([key,...args]);};
 const canvas={getContext:()=>ctx,style:{},dataset:{}};const art=createPrelude(canvas);
 for(const p of [0,.5,1,1.5,2]){calls=[];art.render(p,0,true);assert.ok(calls.length>100);const first=JSON.stringify(calls);calls=[];art.render(p,30,true);assert.equal(JSON.stringify(calls),first);}
 for(const p of [4,9.5,10]){calls=[];art.render(p,30);assert.equal(calls.length,0);assert.equal(canvas.hidden,true);}
 art.dispose();assert.equal(canvas.width*canvas.height,1);
});

test('star-map signals move along edges without reallocating geometry and stay static at fixed time',()=>{
 const atlas=createConstellation();let signals;
 atlas.group.traverse(n=>{if(n.geometry?.attributes.position.usage===35048)signals=n.geometry.attributes.position;});
 assert.ok(signals);const array=signals.array;atlas.render(1,0);const before=Array.from(array);
 atlas.render(1,2);assert.equal(signals.array,array);assert.notDeepEqual(Array.from(array),before);assert.ok([...array].every(Number.isFinite));
 const still=Array.from(array);atlas.render(1,2);assert.deepEqual(Array.from(array),still);atlas.dispose();
});

test('city globe shares the prelude clock, preserves selection, stops hidden drawing and is disposed',()=>{
 Object.assign(globalThis,{innerWidth:1280,innerHeight:720,devicePixelRatio:1});
 const gradient={addColorStop(){}};const ctx=new Proxy({createLinearGradient:()=>gradient,createRadialGradient:()=>gradient},{get:(o,k)=>o[k]??(()=>{})});
 const art=createPrelude({getContext:()=>ctx,style:{},dataset:{}});let frame,hidden=0,disposed=false;
 art.attachGlobe({available:true,render(v){frame=v;return [{index:0,x:900,y:320,z:1}];},hide(){hidden++;},dispose(){disposed=true;}});
 art.render(1,0);art.selectCity(20);art.render(1,1);assert.equal(frame.selected,20);assert.ok(frame.time>0);const before=frame.time;
 art.render(1,2);assert.ok(frame.time>before);art.render(1,3,true);assert.equal(frame.time,0);assert.equal(frame.reduced,true);
 frame=null;art.render(2,4);assert.equal(frame,null);assert.ok(hidden);art.render(6,5);assert.equal(frame,null);
 art.dispose();assert.equal(disposed,true);
});

test('the same seeds morph continuously through both chapter boundaries and reverse exactly',()=>{
 const seeds=globeSeeds();
 for(const i of [0,99,220,999,2300])for(const boundary of [0,1,2]){
  const a=narrativePoint(seeds[i],i,seeds.length,boundary-1e-5,12),b=narrativePoint(seeds[i],i,seeds.length,boundary+1e-5,12);
  assert.ok(Math.hypot(a.x-b.x,a.y-b.y,a.z-b.z)<1e-6);
 }
 for(let p=0;p<=2;p+=.02){
  const before=narrativePoint(seeds[712],712,seeds.length,p,42);
  const reversed=narrativePoint(seeds[712],712,seeds.length,p+.1-.1,42);
  assert.ok(Math.hypot(before.x-reversed.x,before.y-reversed.y,before.z-reversed.z)<1e-12);
  for(let band=0;band<6;band++)assert.ok(Object.values(narrativePath(.37,band,p,42)).every(Number.isFinite));
 }
});

test('sparse atlas spans all four quadrants without recreating the old dense network',()=>{
 const atlas=createConstellation();assert.equal(atlas.group.userData.nodes,18);assert.equal(atlas.group.userData.edges,11);
 let coords;atlas.group.traverse(n=>{if(n.isPoints&&n.geometry.attributes.position.count===18)coords=n.geometry.attributes.position;});
 assert.ok(coords);const x=[],y=[];for(let i=0;i<coords.count;i++){x.push(coords.getX(i));y.push(coords.getY(i));}
 assert.ok(Math.min(...x)<-.85&&Math.max(...x)>.85&&Math.min(...y)<-.7&&Math.max(...y)>.8);
 for(const sx of [-1,1])for(const sy of [-1,1])assert.ok(x.some((v,i)=>v*sx>.3&&y[i]*sy>.3));atlas.dispose();
});
