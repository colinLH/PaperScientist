import test from 'node:test';
import assert from 'node:assert/strict';
import {Journey} from '../paperscientist/static/intro/motion.mjs';
import {WORK_RANGE,railLayout,railCard,playingCards,progressForCard,wallTile,workPixelRatio} from '../paperscientist/static/intro/work-layout.mjs';
import {createPreviewPlayback} from '../paperscientist/static/intro/paper-previews.mjs';

test('at most two curtains including partial edges, disjoint rails and offscreen wrapping across viewport sizes',()=>{
 for(const [w,h] of [[390,844],[680,380],[1280,720],[2160,1440],[3840,2160]]){
  const layout=railLayout(w,h);
  for(let step=0;step<=1000;step++){
   const p=step/1000,rects=Array.from({length:6},(_,i)=>railCard(i,p,layout));
   assert.ok(rects.filter(r=>r.visible).length<=2,`${w} at ${p}: too many curtains`);
   for(const row of [0,1])assert.ok(rects.filter(r=>r.visible&&r.row===row).length<=1);
   for(const a of rects){
    assert.ok(a.y>=0&&a.y+a.height<=h);
    for(const b of rects.filter(b=>b.index>a.index)){
     const overlapX=a.x<b.x+b.width&&b.x<a.x+a.width,overlapY=a.y<b.y+b.height&&b.y<a.y+a.height;
     assert.equal(overlapX&&overlapY,false,`${w} at ${p}: ${a.index}, ${b.index}`);
    }
    if(step){const before=railCard(a.index,p-.001,layout);if(a.x>before.x)assert.ok(before.x+before.width<0&&a.x>w,'wrap outside viewport');else assert.ok(a.x<before.x);}
    assert.deepEqual(railCard(a.index,p,layout),a);
   }
   const live=playingCards(rects,w);assert.ok(live.length<=2);assert.equal(new Set(live.map(i=>i%2)).size,live.length);
  }
  for(let i=0;i<6;i++){const r=railCard(i,progressForCard(i,layout),layout);assert.ok(r.visible);if(i)assert.ok(Math.abs(r.x+r.width/2-w/2)<1e-8);}
 }
});

test('cylindrical wall follows progress left, remains finite, and drawing resolution is bounded at 4K',()=>{
 const a=wallTile(12,25,1280,720,1,.2),b=wallTile(12,25,1280,720,1,.21);assert.ok(b.x<a.x);
 for(const [w,h] of [[390,844],[1280,720],[3840,2160]]){
  for(let p=0;p<=1;p+=.02)for(let i=0;i<25;i++){const r=wallTile(i,25,w,h,1,p);if(r)assert.ok(Object.values(r).every(Number.isFinite));}
  const ratio=workPixelRatio(w,h,3);assert.ok(w*h*ratio*ratio<=2200001);
 }
});

test('wheel magnitude scrubs Work continuously; entrance and exit inertia cannot skip the gallery',()=>{
 const j=new Journey(10);j.go(5,true);j.wheel(100,1000,WORK_RANGE);
 for(let t=1010;t<1200;t+=10)j.wheel(30,t,WORK_RANGE);assert.equal(j.target,6);
 assert.equal(j.wheel(90,1500,WORK_RANGE),false);for(let i=0;i<60;i++)j.tick(1/60,11);
 j.wheel(90,2500,WORK_RANGE);assert.equal(j.target,6.1);j.wheel(45,2510,WORK_RANGE);assert.ok(Math.abs(j.target-6.15)<1e-9);
 j.tick(1/60,11);const pos=j.value,velocity=j.velocity;j.wheel(-45,2520,WORK_RANGE);
 assert.equal(j.value,pos);assert.equal(j.velocity,velocity);assert.ok(Math.abs(j.target-6.1)<1e-9);
 j.wheel(9000,3000,WORK_RANGE);assert.equal(j.target,8);j.wheel(100,3010,WORK_RANGE);assert.equal(j.target,8);
 assert.equal(j.wheel(100,3300,WORK_RANGE),false);for(let i=0;i<90;i++)j.tick(1/60,11);
 j.wheel(100,5000,WORK_RANGE);assert.equal(j.target,9);
});

test('Work keeps fine-grained scroll and reversals unrestricted inside its boundaries',()=>{
 const j=new Journey(10);j.go(6.5,true);
 for(let i=0;i<30;i++){assert.equal(j.wheel(3,i*16,WORK_RANGE),true);j.tick(1/60,11);}
 assert.ok(Math.abs(j.target-6.6)<1e-10);
 for(let i=30;i<60;i++){assert.equal(j.wheel(-3,i*16,WORK_RANGE),true);j.tick(1/60,11);}
 assert.ok(Math.abs(j.target-6.5)<1e-10);
});

test('Work spring reaches the destination sooner without discontinuous mid-flight reversal',()=>{
 const old=new Journey(10),fast=new Journey(10);old.go(5,true);fast.go(5,true);old.go(6);fast.go(6);
 for(let i=0;i<36;i++){old.tick(1/60);fast.tick(1/60,11);}assert.ok(fast.value>5.98);assert.ok(old.value<5.85);
 const p=fast.value,v=fast.velocity;fast.go(5);assert.equal(fast.value,p);assert.equal(fast.velocity,v);fast.tick(1/60,11);assert.ok(Math.abs(fast.value-p)<.03);
});

function mediaItems(){return Array.from({length:6},(_,index)=>{
 const pending=[];return {index,source:'https://example.org/'+index+'.mp4',element:{dataset:{}},pending,video:{paused:true,src:'',play(){this.paused=false;return new Promise((resolve,reject)=>pending.push({resolve,reject}));},pause(){this.paused=true;},load(){},removeAttribute(){this.src='';}}};
});}
const flush=async()=>{await Promise.resolve();await Promise.resolve();};
test('only two videos load; leaving unloads them and late play fulfillment cannot revive them',async()=>{
 const items=mediaItems(),controller=createPreviewPlayback(items);controller.sync([0,1,2,3]);assert.deepEqual(controller.active,[0,1]);assert.equal(items.filter(x=>x.video.src).length,2);
 controller.sync([4,5]);assert.equal(items[0].video.src,'');assert.equal(items[1].video.paused,true);
 items[0].pending[0].resolve();await flush();assert.equal(items[0].video.paused,true);
 controller.dispose();for(const x of items){assert.equal(x.video.src,'');assert.equal(x.video.paused,true);assert.equal(x.video.onplaying,null);}
 controller.sync([0,1]);assert.deepEqual(controller.active,[]);
});
test('rapid reversal cannot let an older play promise pause a new playback of the same card',async()=>{
 const items=mediaItems(),controller=createPreviewPlayback(items);controller.sync([0,1]);controller.sync([2,3]);controller.sync([0,1]);
 items[0].pending[0].resolve();await flush();assert.equal(items[0].video.paused,false);
 items[0].pending[1].resolve();await flush();assert.equal(items[0].video.paused,false);controller.dispose();
});
test('media errors and autoplay rejection expose fallback and can be retried explicitly',async()=>{
 const items=mediaItems(),controller=createPreviewPlayback(items);controller.sync([0,1]);items[0].video.onerror();items[1].pending[0].reject(new Error('autoplay blocked'));await flush();
 assert.equal(items[0].element.dataset.media,'unavailable');assert.equal(items[1].element.dataset.media,'paused');
 controller.retry();controller.sync([0,1]);assert.equal(items[0].pending.length,2);assert.equal(items[1].pending.length,2);controller.dispose();
});
