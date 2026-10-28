import test from 'node:test';
import assert from 'node:assert/strict';
import {discLayout,imageCover,WaterRipples,referenceOpacity} from '../paperscientist/static/intro/reference-art.mjs';
import {createPrelude} from '../paperscientist/static/intro/cosmic-art.mjs';

test('disc layout keeps one equally sized row, bounded drag and a stable reduced-motion pose',()=>{
 for(const [w,h] of [[351,658],[1728,842],[3456,1684]]){
  for(const yaw of [-30,0,30]){
   const poses=[0,1,2,3].map(i=>discLayout(w,h,i,yaw,20));
   for(const p of poses)assert.ok(Object.values(p).every(Number.isFinite));
   for(let i=1;i<poses.length;i++){assert.ok(poses[i].x>poses[i-1].x);assert.equal(poses[i].y,poses[0].y);assert.equal(poses[i].d,poses[0].d);assert.equal(poses[i].angle,poses[0].angle);}
  }
  assert.deepEqual(discLayout(w,h,2,0,0,true),discLayout(w,h,2,0,50,true));
  assert.deepEqual(discLayout(w,h,2,30),discLayout(w,h,2,1.8));
 }
});
test('gallery uses the former second-disc diameter, uniform gaps and narrow draggable edge crops',()=>{
 for(const [w,h] of [[351,658],[921,1065],[1152,562],[2094,902],[3456,1684]]){
  const p=[0,1,2,3].map(i=>discLayout(w,h,i,0,0,true)),d=p[0].d;
  if(w/h>2)assert.equal(d,Math.min(w*.4,h*.56));
  const gaps=p.slice(1).map((v,i)=>v.x-p[i].x-d*.94);
  assert.ok(gaps[0]>=0);assert.ok(Math.max(...gaps)-Math.min(...gaps)<1e-9);
  const leftClip=d*.47-p[0].x,rightClip=p[3].x+d*.47-w;
  assert.ok(leftClip>d*.05&&leftClip<d*.15);assert.ok(Math.abs(leftClip-rightClip)<1e-9);
  assert.ok(discLayout(w,h,0,1.8).x-d*.47>=0);
  assert.ok(discLayout(w,h,3,-1.8).x+d*.47<=w);
 }
});
test('panoramic image cover stays in bounds at narrow and wide aspect ratios',()=>{
 for(const [w,h] of [[390,844],[2157,1244],[3840,2160]]){const c=imageCover(1672,941,w,h);assert.ok(c.x>=0&&c.y>=0&&c.x+c.w<=1672.0001&&c.y+c.h<=941.0001);assert.ok(Math.abs(c.w/c.h-w/h)<1e-10);}
});
test('water ripples have a fixed budget, expire, and clear in reduced motion',()=>{
 const water=new WaterRipples();for(let i=0;i<20;i++)water.add(i,0);assert.equal(water.items.length,4);assert.ok(water.items.every(p=>p.x<=1&&p.y>=.72));
 for(let i=0;i<30;i++)water.tick(.1,false);assert.equal(water.items.length,0);water.add(.5,.8);water.tick(.1,true);assert.equal(water.items.length,0);
 assert.equal(referenceOpacity(0),1);assert.equal(referenceOpacity(1),0);assert.equal(referenceOpacity(2),1);assert.equal(referenceOpacity(3),0);
 for(let p=0;p<3;p+=.01)assert.ok(Math.abs(referenceOpacity(p)-referenceOpacity(p+.1-.1))<1e-12);
});
test('reference art shares the existing clock and stage selection, stops at later chapters and disposes',()=>{
 Object.assign(globalThis,{innerWidth:1280,innerHeight:720,devicePixelRatio:1});
 const gradient={addColorStop(){}};const ctx=new Proxy({createLinearGradient:()=>gradient,createRadialGradient:()=>gradient},{get:(o,k)=>o[k]??(()=>{})});
 const art=createPrelude({getContext:()=>ctx,style:{},dataset:{}});let frame,hidden=0,disposed=false;
 art.attachReference({available:true,render(v){frame=v;return [{index:3,x:900,y:300}];},hide(){hidden++;},dispose(){disposed=true;}});
 art.render(0,0);art.render(0,1);assert.ok(frame.time>0);art.render(0,2,true);assert.equal(frame.time,0);
 art.render(2,3);art.activate();art.render(2,4);assert.equal(frame.state.selected,3);assert.match(art.info.selection,/实验/);
 frame=null;art.render(1,5);assert.equal(frame,null);art.render(4,6);assert.equal(frame,null);assert.ok(hidden>=2);
 art.dispose();assert.equal(disposed,true);
});
