import test from 'node:test';
import assert from 'node:assert/strict';
import {BONES,particleBudget,sampleHand,openness,HandPresence,assignSlots,coverFit} from '../paperscientist/static/intro/hand-motion.mjs';

// Image-space hand: y grows downward, wrist at the origin, palm length ~1.
function hand(fist=false){
  const p=[[0,0,0],[-.35,-.25,0],[-.55,-.45,0],[-.7,-.65,0],[-.85,-.8,0]];
  for(const x of [-.3,-.1,.1,.3]){
    p.push([x,-1,0]);
    if(fist)p.push([x,-1.2,-.2],[x,-.95,-.3],[x,-.75,-.15]);
    else p.push([x,-1.4,0],[x,-1.65,0],[x,-1.85,0]);
  }
  return Float32Array.from(p.flat());
}

test('particle budget is stable, even and within 1000-3000 on every device class',()=>{
  const devices=[{},{cores:1,memory:.5},{cores:2,memory:2,coarse:true},{cores:4,memory:4},{cores:16,memory:32}];
  for(const d of devices){const n=particleBudget(d);assert.ok(n>=1000&&n<=3000,`${n}`);assert.equal(n%2,0);assert.equal(particleBudget(d),n);}
  assert.ok(particleBudget({cores:2,memory:2})<particleBudget({cores:16,memory:32}));
});

test('contour samples reference valid joints, split evenly across both hands and are deterministic',()=>{
  const n=2000,s=sampleHand(n,7),again=sampleHand(n,7);
  assert.equal(s.slot.length,n);assert.equal(s.index.length,n*3);assert.equal(s.weight.length,n*3);assert.equal(s.offset.length,n*2);assert.equal(s.seed.length,n*4);
  assert.deepEqual(s.index,again.index);assert.deepEqual(s.weight,again.weight);
  let palm=0,left=0;
  for(let i=0;i<n;i++){
    const w=s.weight.subarray(i*3,i*3+3);assert.ok(Math.abs(w[0]+w[1]+w[2]-1)<1e-5);assert.ok(w.every(x=>x>=0));
    assert.ok(s.index.subarray(i*3,i*3+3).every(k=>Number.isInteger(k)&&k>=0&&k<=20));
    if(s.offset[i*2+1]===0)palm++;if(s.slot[i]===0)left++;
  }
  assert.equal(left,n/2);assert.ok(palm>n*.3&&palm<n*.55,`${palm}`);
  assert.ok(s.seed.every(x=>x>=0&&x<1));
});

test('fist gathers and open palm spreads; metric ignores hand size and position',()=>{
  const open=openness(hand()),fist=openness(hand(true));
  assert.ok(open>.85,`${open}`);assert.ok(fist<.15,`${fist}`);
  const moved=hand().map((v,i)=>v*3+(i%3===0?40:i%3===1?-7:0));
  assert.ok(Math.abs(openness(moved)-open)<1e-5);
});

test('a lost hand fades out within one second, ignores brief dropouts, and is reborn on return',()=>{
  const h=new HandPresence();let t=0;
  for(;t<1;t+=1/30)h.update(t,true);
  assert.equal(h.alpha,1);
  const lost=t;h.update(t+=.04,false);h.update(t+=.04,false);h.update(t+=1/30,true);assert.equal(h.alpha,1);
  const gone=t+=1/30;
  while(t<gone+1&&h.alpha>0){h.update(t,false);t+=1/30;}
  assert.equal(h.alpha,0);assert.ok(t-gone<=1,`${t-gone}`);assert.ok(lost<gone);
  h.update(t+=1/30,true);assert.equal(h.reborn,true);assert.equal(h.alpha,1);assert.equal(h.born,t);
  h.update(t+=1/30,true);assert.equal(h.reborn,false);
});

test('hand identity follows proximity, not detection order',()=>{
  const previous=[{x:100,y:200,alpha:1},{x:600,y:220,alpha:1}];
  assert.deepEqual(assignSlots([[590,230],[110,190]],previous),[1,0]);
  assert.deepEqual(assignSlots([[120,190],[580,240]],previous),[0,1]);
  assert.deepEqual(assignSlots([[570,200]],previous),[1]);
  assert.deepEqual(assignSlots([[570,200]],[{x:0,y:0,alpha:0},{x:0,y:0,alpha:0}]),[0]);
  assert.deepEqual(assignSlots([[50,50]],[{x:0,y:0,alpha:0},{x:600,y:200,alpha:.4}]),[1]);
  assert.deepEqual(assignSlots([],previous),[]);
});

test('loss also expires after a delayed frame instead of needing many animation ticks',()=>{
  const h=new HandPresence();h.update(0,true);h.update(.1,true);h.update(1.1,false);assert.equal(h.alpha,0);
});

test('camera frame covers the viewport without distortion; skeleton has 21 bones',()=>{
  for(const [w,h] of [[1920,1080],[390,844],[1280,1280]]){
    const f=coverFit(640,480,w,h);
    assert.ok(640*f.scale>=w-1e-6&&480*f.scale>=h-1e-6);
    assert.ok(Math.abs(f.x*2+640*f.scale-w)<1e-6&&Math.abs(f.y*2+480*f.scale-h)<1e-6);
  }
  assert.equal(BONES.length,21);assert.ok(BONES.flat().every(i=>i>=0&&i<=20));
});
