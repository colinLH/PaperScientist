import test from 'node:test';
import assert from 'node:assert/strict';
import {landingLeaf,pondLeafPose,fishPose,framedFishPose,pondPoint,inPond,createGardenPond,createFishSchool,fishIndices,fishScale,FISH_BUDGET} from '../paperscientist/static/intro/garden-pond.mjs';
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


test('nearby water clicks accelerate fish without teleporting and settle back to cruising',()=>{
 const w=1280,h=720,crop={x:0,y:0,w:1,h:1},school=createFishSchool(),initial=school.pose(0,0,false,crop),click=pondPoint(initial.x,initial.y,w,h,crop);
 assert.equal(school.startle(5,5,0,w,h,crop),0);
 assert.equal(school.startle(w*.3,h*.99,0,w,h,crop),0);
 assert.ok(school.startle(click.x,click.y,0,w,h,crop)>=1);
 assertSamePose(school.pose(0,0,false,crop),initial,w,h,crop);
 for(let n=1;n<=180;n++)school.tick(1/60,n/60,w,h,crop,false);
 const moved=school.pose(0,3,false,crop),calm=framedFishPose(0,3,false,crop),distance=p=>Math.hypot((p.x-initial.x)*w,(p.y-initial.y)*h);
 assert.ok(distance(moved)>20&&distance(moved)>distance(calm)*3);
 for(let n=181;n<=480;n++)school.tick(1/60,n/60,w,h,crop,false);
 assert.equal(school.startled,0);
 const a=school.pose(0,8,false,crop);school.tick(.016,8.016,w,h,crop,false);const b=school.pose(0,8.016,false,crop);
 assert.ok(Math.hypot((b.x-a.x)*w,(b.y-a.y)*h)<fishScale(w,h,crop)*4*.016,'returns to slow cruising');
 assert.equal(school.startle(click.x,click.y,8,w,h,crop,true),0);
 assert.deepEqual(school.pose(0,100,true,crop),school.pose(0,0,true,crop));
});

test('repeated startles keep visible fish apart, inside the water, and turning continuously at every size',()=>{
 for(const [w,h] of [[390,844],[1280,720],[2327,1105],[3840,2160],[640,360]]){
  const c=imageCover(3840,2160,w,h,w<=700?.62:.5),crop={x:c.x/3840,y:c.y/2160,w:c.w/3840,h:c.h/2160};
  const school=createFishSchool(),ids=fishIndices(w),radius=fishScale(w,h,crop)*11.5;
  let previous=ids.map(i=>school.pose(i,0,false,crop));
  for(let n=1;n<=1800;n++){
   const t=n/60;
   if(n%45===0){const p=previous[(n/45)%ids.length],q=pondPoint(p.x,p.y,w,h,crop);school.startle(q.x,q.y,t-1/60,w,h,crop);}
   school.tick(1/60,t,w,h,crop,false);const poses=ids.map(i=>school.pose(i,t,false,crop));
   for(let i=0;i<poses.length;i++){
    const p=poses[i],a=pondPoint(p.x,p.y,w,h,crop),old=previous[i];
    assert.ok(inPond(p.x,p.y));assert.ok(a.x>radius&&a.x<w-radius&&a.y>radius&&a.y<h-radius,JSON.stringify({w,h,t,i,a,radius}));
    assert.equal(p.alpha,.94);
    const heading=v=>v.heading??Math.atan2(v.vy*h/crop.h,v.vx*w/crop.w),delta=heading(p)-heading(old);
    assert.ok(Math.abs(Math.atan2(Math.sin(delta),Math.cos(delta)))<.14,'turn stays below eight degrees per frame');
    for(let j=i+1;j<poses.length;j++){const b=pondPoint(poses[j].x,poses[j].y,w,h,crop);assert.ok(Math.hypot(a.x-b.x,a.y-b.y)>radius*2,'body and tail clearance');}
   }previous=poses;
  }
  school.tick(.1,40,w,h,crop,true);assert.equal(school.startled,0);
 }
});

test('pond interactions use the displayed crop and stop accepting taps when hidden or disposed',()=>{
 const pond=createGardenPond(),ctx=new Proxy({},{get:()=>()=>{}}),crop={x:0,y:0,w:1,h:1};
 assert.equal(pond.tap(400,600).water,false);pond.fish(ctx,1280,720,0,false,crop);
 const p=framedFishPose(0,0,false,crop),hit=pond.tap(p.x*1280,p.y*720);
 assert.equal(hit.water,true);assert.ok(hit.fish>0);assert.equal(pond.tap(20,20).water,false);
 pond.pause();assert.equal(pond.tap(p.x*1280,p.y*720).water,false);
 pond.fish(ctx,1280,720,1,true,crop);assert.equal(pond.tap(p.x*1280,p.y*720).fish,0);
 pond.dispose();assert.equal(pond.startled,0);assert.equal(pond.tap(400,600).water,false);
});

function assertSamePose(a,b,w,h,crop){
 assert.equal(a.x,b.x);assert.equal(a.y,b.y);
 const angle=p=>p.heading??Math.atan2(p.vy*h/crop.h,p.vx*w/crop.w);
 assert.ok(Math.abs(Math.atan2(Math.sin(angle(a)-angle(b)),Math.cos(angle(a)-angle(b))))<1e-10,'input preserves heading');
}

test('510 startle directions produce moving escape arcs, not stationary reversals or endpoint holds',()=>{
 let checked=0,headOn=0;
 for(const [w,h] of [[390,844],[1280,720],[3840,2160]]){
  const c=imageCover(3840,2160,w,h,w<700?.62:.5),crop={x:c.x/3840,y:c.y/2160,w:c.w/3840,h:c.h/2160},size=fishScale(w,h,crop);
  for(const i of fishIndices(w))for(const time of [0,10,30,55])for(let side=0;side<8;side++){
   const school=createFishSchool(),p=school.pose(i,time,false,crop),origin=pondPoint(p.x,p.y,w,h,crop),angle=side*Math.PI/4;
   const x=origin.x+Math.cos(angle)*28,y=origin.y+Math.sin(angle)*28;
   if(!inPond(crop.x+x/w*crop.w,crop.y+y/h*crop.h))continue;
   assert.ok(school.startle(x,y,time,w,h,crop)>0);assertSamePose(school.pose(i,time,false,crop),p,w,h,crop);
   if((p.vx*w/crop.w)*(x-origin.x)+(p.vy*h/crop.h)*(y-origin.y)>0)headOn++;
   let previous=origin,heading=Math.atan2(p.vy*h/crop.h,p.vx*w/crop.w),travel=0,stall=0,escapeDistance=0;
   // Escape first, then keep swimming after the burst rather than holding the
   // far end of an ellipse. A curved turn may briefly move closer to the tap.
   for(let n=1;n<=300;n++){
    school.tick(1/60,time+n/60,w,h,crop,false);const pose=school.pose(i,time+n/60,false,crop),q=pondPoint(pose.x,pose.y,w,h,crop);
    const movement=Math.hypot(q.x-previous.x,q.y-previous.y),delta=pose.heading-heading;
    travel+=movement;stall=movement<size*.01?stall+1:0;
    assert.ok(stall<10,JSON.stringify({w,h,i,time,side,n,stall}));
    assert.ok(Math.abs(Math.atan2(Math.sin(delta),Math.cos(delta)))<.14,'continuous heading, including +/-pi');
    if(n===90){escapeDistance=Math.hypot(q.x-x,q.y-y);assert.ok(escapeDistance>28+size*2,JSON.stringify({w,h,i,time,side,escapeDistance}));assert.ok(travel>size*30,'rapid translation while turning');}
    previous=q;heading=pose.heading;
   }
   assert.ok(travel>size*45,'continues swimming after startle');checked++;
  }
 }
 assert.equal(checked,510);assert.ok(headOn>150);
});

test('repeated opposite-side ripples redirect a moving fish without position or heading jumps',()=>{
 const w=1280,h=720,crop={x:0,y:0,w:1,h:1},school=createFishSchool(),size=fishScale(w,h,crop);let time=10;
 for(let hit=0;hit<6;hit++){
  const p=school.pose(1,time,false,crop),q=pondPoint(p.x,p.y,w,h,crop),x=q.x+(hit%2?25:-25),y=q.y;
  assert.ok(school.startle(x,y,time,w,h,crop));assertSamePose(school.pose(1,time,false,crop),p,w,h,crop);
  let travel=0,previous=q,stall=0;
  for(let n=0;n<100;n++){
   time+=1/60;school.tick(1/60,time,w,h,crop,false);const p=school.pose(1,time,false,crop),q=pondPoint(p.x,p.y,w,h,crop),step=Math.hypot(q.x-previous.x,q.y-previous.y);
   travel+=step;stall=step<size*.01?stall+1:0;assert.ok(stall<10);previous=q;
  }
  assert.ok(travel>size*25,'does not wait for the previous escape to finish');
 }
});
