import test from 'node:test';
import assert from 'node:assert/strict';
import {landingLeaf,pondLeafPose,fishPose,framedFishPose,pondPoint,inPond,createGardenPond,FISH_BUDGET} from '../paperscientist/static/intro/garden-pond.mjs';
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
  const p=fishPose(i,t),q=fishPose(i,t+.01);assert.ok(inPond(p.x,p.y,.025));
  assert.ok(Math.hypot(q.x-p.x,q.y-p.y)<.001);assert.ok(p.alpha>=.73&&p.alpha<=.86);
  assert.deepEqual(fishPose(i,t,true),fishPose(i,0,true));
 }
});

test('fish swept paths keep bodies and tails apart and turn gradually without reversal snaps',()=>{
 for(let time=0;time<900;time+=.05){
  const poses=Array.from({length:FISH_BUDGET},(_,i)=>fishPose(i,time));
  for(let i=0;i<FISH_BUDGET;i++){
   const p=poses[i],q=fishPose(i,time+.05),a=Math.atan2(p.vy*720,p.vx*1280),b=Math.atan2(q.vy*720,q.vx*1280);
   const turn=Math.abs(Math.atan2(Math.sin(b-a),Math.cos(b-a)));
   assert.ok(turn<.025); // Under 1.44 degrees per 50 ms, including angle wrapping.
   assert.ok(Math.hypot(p.vx,p.vy)>.0004);
   for(let j=i+1;j<FISH_BUDGET;j++){
    const distance=Math.hypot((p.x-poses[j].x)*1280,(p.y-poses[j].y)*720);
    assert.ok(distance>70); // Maximum combined body/tail reach is below 58 px.
   }
  }
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

test('visible fish retain collision clearance and gentle headings in wide, portrait, and 4K views',()=>{
 for(const [w,h] of [[390,844],[1280,720],[2327,1105],[3840,2160],[640,360]]){
  const c=imageCover(3840,2160,w,h,w<=700?.62:.5),crop={x:c.x/3840,y:c.y/2160,w:c.w/3840,h:c.h/2160};
  const indices=w<700?[0,2,3,5]:[0,1,2,3,4,5];
  for(let t=0;t<600;t+=.25){
   const poses=indices.map(i=>framedFishPose(i,t,false,crop));
   for(let i=0;i<poses.length;i++){
    const p=poses[i],a=pondPoint(p.x,p.y,w,h,crop),radius=Math.max(1,Math.min(4.8,h/720*2.5))*p.size*11.5;
    assert.ok(inPond(p.x,p.y));assert.ok(a.x>radius&&a.x<w-radius&&a.y>radius&&a.y<h-radius,JSON.stringify({w,h,t,i,a,radius,crop}));
    const q=framedFishPose(indices[i],t+.05,false,crop),heading=v=>Math.atan2(v.vy*h/crop.h,v.vx*w/crop.w),delta=heading(q)-heading(p);
    assert.ok(Math.abs(Math.atan2(Math.sin(delta),Math.cos(delta)))<.025);
    for(let j=i+1;j<poses.length;j++){const b=pondPoint(poses[j].x,poses[j].y,w,h,crop);assert.ok(Math.hypot(a.x-b.x,a.y-b.y)>radius*2);}
   }
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
