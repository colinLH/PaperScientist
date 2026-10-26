import test from 'node:test';
import assert from 'node:assert/strict';
import {Journey,musicGains} from '../paperscientist/static/intro/motion.mjs';
import {LAST_STOP,journeyFrame,warpDepth} from '../paperscientist/static/intro/journey-map.mjs';
import {createWarp} from '../paperscientist/static/intro/warp.js';

test('new camera, apertures and soundtrack traverse the same continuous path in both directions',()=>{
 const forward=[];
 for(let p=0;p<=LAST_STOP;p+=.005){
  const f=journeyFrame(p);forward.push(f);
  assert.ok(f.landscape>=0&&f.landscape<=5);
  for(const key of ['work','warp','aperture','star'])assert.ok(f[key]>=0&&f[key]<=1);
  if(forward.length>1){const before=forward.at(-2);for(const key of ['landscape','work','warp','aperture','music'])assert.ok(Math.abs(f[key]-before[key])<(key==='aperture'?.04:.025),`${key} at ${p}`);}
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
test('star depth is periodic and reversible',()=>{
 for(let i=0;i<400;i++){const seed=i/400,position=warpDepth(seed,.137);assert.ok(position>=.055&&position<1);assert.ok(Math.abs(warpDepth(seed,1.137)-position)<1e-12);}
});

test('warp skips all hidden drawing, keeps 400 particles across UHD resizes, and stops moving for reduced motion',()=>{
 Object.assign(globalThis,{innerWidth:3840,innerHeight:2160,devicePixelRatio:2});
 let strokes=0,segments=[];const ctx={setTransform(){},clearRect(){segments=[];},fillRect(){},createRadialGradient(){return {addColorStop(){}};},beginPath(){},ellipse(){},quadraticCurveTo(){assert.fail('Warp rays must remain straight');},moveTo(x,y){segments.push([x,y]);},lineTo(x,y){segments.push([x,y]);},stroke(){strokes++;}};
 const canvas={getContext:()=>ctx,style:{},dataset:{}};const warp=createWarp(canvas);
 assert.equal(canvas.dataset.particles,400);assert.ok(canvas.width*canvas.height<=2604000);
 warp.render(3,1,1/30);assert.ok(strokes>0);const count=strokes;
 for(let i=0;i<60;i++)warp.render(4,0,1/30);assert.equal(strokes,count);assert.equal(canvas.hidden,true);
 innerWidth=390;innerHeight=844;warp.resize();assert.equal(canvas.dataset.particles,400);
 warp.render(3,1,1/30,true);const still=structuredClone(segments);warp.render(3,1,.08,true);assert.deepEqual(segments,still);
 warp.dispose();assert.equal(canvas.width*canvas.height,1);assert.equal(canvas.hidden,true);
});
