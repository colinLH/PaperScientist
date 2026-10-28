import test from 'node:test';
import assert from 'node:assert/strict';
import {landingLeaf,pondLeafPose,fishPose,pondPoint,inPond,createGardenPond,FISH_BUDGET} from '../paperscientist/static/intro/garden-pond.mjs';
import {imageCover} from '../paperscientist/static/intro/reference-art.mjs';

test('water-bound leaves land continuously at their ripple origin, float inside the pond and fade before recycling',()=>{
 for(let i=0;i<18;i++){
  if(i%3===2)continue;
  const impact=3+(i-Math.floor(i/3))*4,before=landingLeaf(i,impact-.001),hit=landingLeaf(i,impact),after=landingLeaf(i,impact+.001);
  assert.equal(before.floating,false);assert.equal(hit.floating,true);assert.equal(hit.age,0);
  assert.equal(hit.x,hit.impactX);assert.equal(hit.y,hit.impactY);assert.ok(inPond(hit.x,hit.y,.03));
  assert.ok(Math.hypot(hit.x-before.x,hit.y-before.y)<.0001);assert.ok(Math.hypot(hit.x-after.x,hit.y-after.y)<.0001);
  assert.ok(Math.abs(hit.angle-before.angle)<.001);
  for(let age=0;age<8;age+=.1){const p=landingLeaf(i,impact+age);assert.ok(inPond(p.x,p.y));assert.ok(p.alpha>=0&&p.alpha<=.8);}
  assert.ok(landingLeaf(i,impact+7.99).alpha<.0001);assert.ok(landingLeaf(i,impact+8.01).alpha<.0001);
  const next=landingLeaf(i,impact+48);assert.equal(next.x,hit.x);assert.equal(next.y,hit.y);assert.equal(next.age,0);
 }
});

test('fish follow continuous shallow-water paths with margin for their tails and a stable reduced-motion pose',()=>{
 for(let t=0;t<600;t+=.5)for(let i=0;i<FISH_BUDGET;i++){
  const p=fishPose(i,t),q=fishPose(i,t+.01);assert.ok(inPond(p.x,p.y,.045));
  assert.ok(Math.hypot(q.x-p.x,q.y-p.y)<.001);assert.ok(p.alpha>=.73&&p.alpha<=.86);
  assert.deepEqual(fishPose(i,t,true),fishPose(i,0,true));
 }
});

test('leaf contact and water ripples share artwork coordinates after portrait and 4K crops',()=>{
 for(const [w,h] of [[390,844],[1280,720],[3840,2160]]){
  const c=imageCover(3840,2160,w,h,w<=700?.62:.5),crop={x:c.x/3840,y:c.y/2160,w:c.w/3840,h:c.h/2160};
  for(let i=0;i<18;i++){
   if(i%3===2)continue;const impact=3+(i-Math.floor(i/3))*4;
   const leaf=pondLeafPose(i,impact,w,h,false,crop),raw=landingLeaf(i,impact),ring=pondPoint(raw.impactX,raw.impactY,w,h,crop);
   assert.equal(leaf.x,ring.x);assert.equal(leaf.y,ring.y);assert.equal(pondLeafPose(i,impact,w,h,true,crop).alpha,0);
  }
 }
});

test('pond renderer keeps fixed populations, suppresses reduced-motion impacts, and releases cleanly',()=>{
 let calls=0,clips=0;const ctx=new Proxy({clip(){clips++;}},{get:(o,k)=>o[k]??(()=>{calls++;})}),crop={x:0,y:0,w:1,h:1},pond=createGardenPond();
 for(let frame=0;frame<1800;frame++){
  const time=frame/30;assert.equal(pond.fish(ctx,1280,720,time,false,crop),6);
  assert.ok(pond.surface(ctx,1280,720,time,false,crop)<=1);
 }
 assert.equal(pond.fish(ctx,390,844,4,false,crop),4);assert.equal(pond.surface(ctx,1280,720,4,true,crop),0);assert.ok(clips>3000);
 assert.equal(pond.surface(ctx,1280,720,0,false,crop),0);assert.equal(pond.surface(ctx,1280,720,2.99,false,crop),0);assert.equal(pond.surface(ctx,1280,720,3.01,false,crop),1);
 pond.dispose();const stopped=calls;assert.equal(pond.fish(ctx,1280,720,5,false,crop),0);assert.equal(pond.surface(ctx,1280,720,5,false,crop),0);assert.equal(calls,stopped);
});
