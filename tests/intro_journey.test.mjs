import test from 'node:test';
import assert from 'node:assert/strict';
import {Journey,musicGains} from '../paperscientist/static/intro/motion.mjs';
import {LAST_STOP,journeyFrame,warpDepth,workColumn} from '../paperscientist/static/intro/journey-map.mjs';
import {createWarp} from '../paperscientist/static/intro/warp.js';
import {createWork} from '../paperscientist/static/intro/work.js';

test('new camera, apertures and soundtrack traverse the same continuous path in both directions',()=>{
 const forward=[];
 for(let p=0;p<=LAST_STOP;p+=.005){
  const f=journeyFrame(p);forward.push(f);
  assert.ok(f.landscape>=0&&f.landscape<=5);
  for(const key of ['work','warp','aperture','star'])assert.ok(f[key]>=0&&f[key]<=1);
  if(forward.length>1){const before=forward.at(-2);for(const key of ['landscape','work','warp','aperture','music'])assert.ok(Math.abs(f[key]-before[key])<.025,`${key} at ${p}`);}
  const gains=musicGains(f.music);
  if(p>=2)assert.ok(Math.abs(gains.reduce((s,x)=>s+x*x,0)-1)<1e-10);
 }
 for(const f of forward.reverse())assert.deepEqual(journeyFrame(f.p),f);
 assert.equal(journeyFrame(2).landscape,2);assert.equal(journeyFrame(3).warp,1);
 assert.equal(journeyFrame(4).landscape,3);assert.equal(journeyFrame(4).work,0);
 assert.equal(journeyFrame(5).aperture,0);assert.equal(journeyFrame(6).aperture,1);
 assert.equal(journeyFrame(8).aperture,1);assert.equal(journeyFrame(9).aperture,0);
 assert.equal(journeyFrame(10).landscape,5);assert.equal(journeyFrame(10).work,0);
});
test('one wheel gesture per travel beat, with a mid-entrance reversal and an instant final keyboard jump',()=>{
 const j=new Journey(LAST_STOP);j.go(5,true);j.wheel(30,1000);
 for(let i=0;i<24;i++){j.wheel(10,1010+i*16);j.tick(1/60);}assert.equal(j.target,6);
 const before=j.value,v=j.velocity;j.wheel(-30,1500);assert.equal(j.target,5);assert.equal(j.velocity,v);assert.equal(j.value,before);
 j.tick(1/60);assert.ok(Math.abs(j.value-before)<.04);
 for(let i=0;i<500;i++)j.tick(1/60);assert.equal(journeyFrame(j.value).aperture,0);
 j.go(99,true);assert.equal(j.value,10);assert.equal(j.moving,false);
});
test('star depth is periodic and reversible; wall planes stay finite and meet at the capsule',()=>{
 for(let i=0;i<400;i++){const seed=i/400,position=warpDepth(seed,.137);assert.ok(position>=.055&&position<1);assert.ok(Math.abs(warpDepth(seed,1.137)-position)<1e-12);}
 for(let i=0;i<21;i++){const closed=workColumn(i,21,3840,2160,0);assert.equal(Math.abs(closed.x)+Math.abs(closed.y)+Math.abs(closed.z),0);
  const open=workColumn(i,21,3840,2160,1,.5,999);assert.ok(Object.values(open).every(Number.isFinite));
  assert.deepEqual(workColumn(i,21,390,844,1,.5,999,true),workColumn(i,21,390,844,1,-.5,1000,true));}
});

test('warp skips all hidden drawing, keeps 400 particles across UHD resizes, and stops moving for reduced motion',()=>{
 Object.assign(globalThis,{innerWidth:3840,innerHeight:2160,devicePixelRatio:2});
 let strokes=0,segments=[];const ctx={setTransform(){},clearRect(){segments=[];},fillRect(){},createRadialGradient(){return {addColorStop(){}};},beginPath(){},moveTo(x,y){segments.push([x,y]);},lineTo(x,y){segments.push([x,y]);},stroke(){strokes++;}};
 const canvas={getContext:()=>ctx,style:{},dataset:{}};const warp=createWarp(canvas);
 assert.equal(canvas.dataset.particles,400);assert.ok(canvas.width*canvas.height<=2604000);
 warp.render(3,1,1/30);assert.ok(strokes>0);const count=strokes;
 for(let i=0;i<60;i++)warp.render(4,0,1/30);assert.equal(strokes,count);assert.equal(canvas.hidden,true);
 innerWidth=390;innerHeight=844;warp.resize();assert.equal(canvas.dataset.particles,400);
 warp.render(3,1,1/30,true);const still=structuredClone(segments);warp.render(3,1,.08,true);assert.deepEqual(segments,still);
 warp.dispose();assert.equal(canvas.width*canvas.height,1);assert.equal(canvas.hidden,true);
});

class Element {
 constructor(){this.children=[];this.style={};this.dataset={};this.hidden=false;this.attrs={};}
 append(...nodes){this.children.push(...nodes);}
 replaceChildren(...nodes){this.children=nodes;}
 setAttribute(k,v){this.attrs[k]=v;}
 remove(){this.removed=true;}
}
test('gallery bounds its preview pool, exposes keyboard selection, clears hidden previews, and disposes all nodes',()=>{
 const selectors=['.work-wall','.work-portal','.work-grid','.work-trail','.work-picker','.work-caption'];
 const elements=Object.fromEntries(selectors.map(k=>[k,new Element()])),root=new Element();root.querySelector=s=>elements[s];
 globalThis.document={createElement:()=>new Element(),createElementNS:()=>new Element()};
 Object.assign(globalThis,{innerWidth:1280,innerHeight:720});
 const work=createWork(root,()=>{});work.render(journeyFrame(6),performance.now()/1000,1/30,false);
 assert.equal(elements['.work-picker'].children.length,6);assert.equal(elements['.work-trail'].children.length,5);assert.equal(elements['.work-wall'].children.length,21);
 for(let i=0;i<200;i++)elements['.work-picker'].children[i%6].onclick();
 assert.equal(elements['.work-trail'].children.length,5);assert.equal(elements['.work-trail'].children.filter(x=>!x.hidden).length,1);
 work.render(journeyFrame(6),performance.now()/1000,1/30,true);
 elements['.work-picker'].children[4].onfocus();assert.equal(elements['.work-caption'].textContent,'把发现写成论文');
 innerWidth=390;innerHeight=640;work.resize();const preview=elements['.work-trail'].children.find(x=>!x.hidden);assert.equal(preview.style.left,'195px');assert.equal(preview.style.top,'320px');
 work.render(journeyFrame(10),performance.now()/1000,1/30,true);assert.equal(root.hidden,true);assert.ok(elements['.work-trail'].children.every(x=>x.hidden));
 work.dispose();for(const selector of ['.work-wall','.work-trail','.work-picker'])assert.ok(elements[selector].children.every(x=>x.removed));
});
