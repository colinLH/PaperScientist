import test from 'node:test';
import assert from 'node:assert/strict';
import {Journey} from '../paperscientist/static/intro/motion.mjs';
import {WORK_RANGE,CURTAIN_COUNT,CURTAIN_START,CURTAIN_END,railLayout,railCard,playingCards,progressForCard,entryForCard,wallTile,workPixelRatio,workCamera,portalBounds,cameraTile,workSpring,workScrollRange,workDistance} from '../paperscientist/static/intro/work-layout.mjs';
import {createPreviewPlayback} from '../paperscientist/static/intro/paper-previews.mjs';

test('at most two curtains including partial edges, disjoint alternating rails across viewport sizes',()=>{
 for(const [w,h] of [[390,844],[680,380],[1280,720],[2160,1440],[3840,2160]]){
  const layout=railLayout(w,h);
  for(let step=0;step<=1000;step++){
   const p=step/1000,rects=Array.from({length:CURTAIN_COUNT},(_,i)=>railCard(i,p,layout));
   assert.ok(rects.filter(r=>r.visible).length<=2,`${w} at ${p}: too many curtains`);
   for(const row of [0,1])assert.ok(rects.filter(r=>r.visible&&r.row===row).length<=1);
   for(const a of rects){
    assert.ok(a.y>=0&&a.y+a.height<=h);
    for(const b of rects.filter(b=>b.index>a.index)){
     const overlapX=a.x<b.x+b.width&&b.x<a.x+a.width,overlapY=a.y<b.y+b.height&&b.y<a.y+a.height;
     assert.equal(overlapX&&overlapY,false,`${w} at ${p}: ${a.index}, ${b.index}`);
    }
    if(step)assert.ok(a.x<railCard(a.index,p-.001,layout).x);
    assert.deepEqual(railCard(a.index,p,layout),a);
   }
   const live=playingCards(rects,w);assert.ok(live.length<=2);assert.equal(new Set(live.map(i=>i%2)).size,live.length);
  }
  for(let i=0;i<CURTAIN_COUNT;i++){const r=railCard(i,progressForCard(i,layout),layout);assert.ok(r.visible);if(i)assert.ok(Math.abs(r.x+r.width/2-w/2)<1e-8);}
 }
});

test('the opened wall starts empty and curtains enter from the right only at the preceding card reaches the half-screen handoff',()=>{
 for(const [w,h] of [[390,844],[1280,720],[3840,2160]]){
  const layout=railLayout(w,h);
  for(let p=0;p<CURTAIN_START;p+=.01)for(let i=0;i<CURTAIN_COUNT;i++)assert.equal(railCard(i,p,layout).visible,false);
  for(let i=0;i<CURTAIN_COUNT;i++){
   const entry=entryForCard(i,layout),incoming=railCard(i,entry+1e-7,layout);
   assert.ok(incoming.visible&&incoming.x>w-1,'enters at right edge');
   if(i){const outgoing=railCard(i-1,entry,layout);assert.notEqual(incoming.row,outgoing.row);assert.ok(outgoing.visible);assert.ok(Math.abs(outgoing.x+outgoing.width-w/2)<1e-6);}
  }
  for(const p of [CURTAIN_END+.001,1])for(let i=0;i<CURTAIN_COUNT;i++)assert.equal(railCard(i,p,layout).visible,false);
 }
});

test('camera pushes in before unfolding and folds before pulling back over the same reversible path',()=>{
 const closed=workCamera(5),focus=workCamera(5.35),unroll=workCamera(5.65),open=workCamera(6);
 assert.equal(closed.zoom,1);assert.equal(closed.unfold,0);
 assert.ok(focus.zoom>1.5);assert.equal(focus.unfold,0);
 assert.ok(unroll.unfold>0&&unroll.unfold<1);assert.equal(unroll.zoom,open.zoom);
 assert.equal(open.unfold,1);
 for(let i=0;i<=100;i++){
  const a=workCamera(5+i/100),b=workCamera(9-i/100);
  for(const key of Object.keys(a))assert.ok(Math.abs(a[key]-b[key])<1e-8);
  for(const [w,h] of [[390,844],[1280,720],[3840,2160]]){
   const box=portalBounds(w,h,a);assert.ok(Object.values(box).every(Number.isFinite));
   assert.ok(Math.abs(box.x+box.width/2-w/2)<1e-8);assert.ok(Math.abs(box.y+box.height/2-h/2)<1e-8);
   for(let j=0;j<25;j++){const tile=cameraTile(j,25,w,h,a,0);if(tile)assert.ok(Object.values(tile).every(Number.isFinite));}
  }
 }
 const b0=portalBounds(1280,720,closed),b1=portalBounds(1280,720,focus);assert.ok(b1.height>b0.height*1.5);
 assert.equal(workSpring(5.2,6),6);assert.equal(workSpring(8.2,9),6);assert.equal(workSpring(6.5,6.8),11);
});

test('closed WORK remains central after narrow resize at both entrance and exit',()=>{
 for(const [w,h] of [[320,568],[390,844],[768,1024],[1280,720],[3840,2160]]){
  for(const position of [5,9])for(const progress of [0,1]){
   const tile=cameraTile(12,25,w,h,workCamera(position),progress);
   assert.ok(tile&&Object.values(tile).every(Number.isFinite));
   assert.ok(Math.abs(tile.x+tile.width/2-w/2)<1e-8);
   assert.ok(Math.abs(tile.y+tile.height/2-h/2)<1e-8);
  }
 }
});

test('cylindrical wall follows progress left, remains finite, and drawing resolution is bounded at 4K',()=>{
 const a=wallTile(12,25,1280,720,1,.2),b=wallTile(12,25,1280,720,1,.21);assert.ok(b.x<a.x);
 for(const [w,h] of [[390,844],[1280,720],[3840,2160]]){
  for(let p=0;p<=1;p+=.02)for(let i=0;i<25;i++){const r=wallTile(i,25,w,h,1,p);if(r)assert.ok(Object.values(r).every(Number.isFinite));}
  const ratio=workPixelRatio(w,h,3);assert.ok(w*h*ratio*ratio<=2200001);
 }
});

test('one wheel gesture advances a third of the viewport regardless of delta or trailing inertia',()=>{
 for(const [w,h] of [[390,844],[1280,720],[3840,2160]]){
  const range=workScrollRange(w,h),layout=railLayout(w,h),j=new Journey(10);j.go(6.5,true);
  const before=railCard(1,(j.target-6)/2,layout);
  j.wheel(9000,0,range);
  for(let t=16;t<300;t+=16){j.wheel(120,t,range);j.tick(1/60,11);}
  assert.ok(Math.abs(j.target-(6.5+range.step))<1e-10);
  const after=railCard(1,(j.target-6)/2,layout);assert.ok(Math.abs(before.x-after.x-w/3)<1e-8);
  assert.ok(Math.abs(workDistance(.25+range.step/2,layout)-workDistance(.25,layout)-w/3)<1e-8);
  const value=j.value,velocity=j.velocity;j.wheel(-120,310,range);
  assert.equal(j.value,value);assert.equal(j.velocity,velocity);assert.ok(Math.abs(j.target-6.5)<1e-10);
  j.wheel(30,600,range);assert.ok(Math.abs(j.target-(6.5+range.step))<1e-10);
 }
});

test('small trackpad events accumulate once; entrance and exit retain boundary protection',()=>{
 const range=workScrollRange(1280,720),j=new Journey(10);j.go(5,true);j.wheel(100,0,range);
 for(let t=10;t<200;t+=10)j.wheel(30,t,range);assert.equal(j.target,6);
 assert.equal(j.wheel(90,500,range),false);for(let i=0;i<120;i++)j.tick(1/60,6);
 for(let t=1000;t<1480;t+=16)j.wheel(3,t,range);
 assert.ok(Math.abs(j.target-(6+range.step))<1e-10);
 j.go(8-range.step/2,true);j.wheel(9999,2000,range);assert.equal(j.target,8);
 j.wheel(100,2010,range);assert.equal(j.target,8);assert.equal(j.wheel(100,2400,range),false);
 for(let i=0;i<120;i++)j.tick(1/60,11);assert.equal(j.wheel(100,4000,range),true);assert.equal(j.target,9);
});

test('Work spring reaches the destination sooner without discontinuous mid-flight reversal',()=>{
 const old=new Journey(10),fast=new Journey(10);old.go(5,true);fast.go(5,true);old.go(6);fast.go(6);
 for(let i=0;i<36;i++){old.tick(1/60);fast.tick(1/60,11);}assert.ok(fast.value>5.98);assert.ok(old.value<5.85);
 const p=fast.value,v=fast.velocity;fast.go(5);assert.equal(fast.value,p);assert.equal(fast.velocity,v);fast.tick(1/60,11);assert.ok(Math.abs(fast.value-p)<.03);
});

function mediaItems(){return Array.from({length:CURTAIN_COUNT},(_,index)=>{
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
