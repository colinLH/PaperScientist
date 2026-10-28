import test from 'node:test';
import assert from 'node:assert/strict';
import {leafPose,canopyPose,fogPose,waterSpan,LEAF_BUDGET,createGardenAtmosphere} from '../paperscientist/static/intro/garden-atmosphere.mjs';

test('garden particles and deformations stay bounded through long running scenes and resize',()=>{
 for(const [w,h] of [[390,844],[1280,720],[3840,2160]])for(const t of [0,.1,8,120,1e6]){
  for(let i=0;i<LEAF_BUDGET;i++){
   const p=leafPose(i,t,w,h);assert.ok(Object.values(p).every(Number.isFinite));assert.ok(p.alpha>=0&&p.alpha<=.8);assert.ok(p.y>=-.11*h&&p.y<=1.09*h);assert.ok(p.scale<10);
   assert.deepEqual(leafPose(i,t,w,h,true),leafPose(i,0,w,h,true));
  }
  for(let i=0;i<3;i++){const p=canopyPose(i,t);assert.ok(Math.abs(p.angle)<=.0045&&Math.abs(p.x)<=1.8&&Math.abs(p.y)<=.9);assert.deepEqual(canopyPose(i,t,true),{angle:0,x:0,y:0});}
  for(let i=0;i<6;i++)assert.deepEqual(fogPose(i,t,w,h,true),fogPose(i,0,w,h,true));
 }
 assert.notDeepEqual(leafPose(1,0,1280,720),leafPose(1,3,1280,720));
 assert.notDeepEqual(fogPose(1,0,1280,720),fogPose(1,3,1280,720));
 for(let y=.71;y<=1;y+=.01){const p=waterSpan(y);assert.ok(p.left>=.14&&p.right<=.87&&p.left<p.right);}
});

test('garden caches its textures, draws no moving layers in reduced motion, and releases on disposal',()=>{
 const original=globalThis.document,canvases=[];let calls=0;
 const gradient={addColorStop(){}};
 const ctx=new Proxy({createRadialGradient:()=>gradient,createLinearGradient:()=>gradient,drawImage(){calls++;}},{get:(o,k)=>o[k]??(()=>{})});
 globalThis.document={createElement(){const c={width:0,height:0,getContext:()=>ctx};canvases.push(c);return c;}};
 try{
  const art=createGardenAtmosphere(),img={complete:true,naturalWidth:1672,naturalHeight:941},crop={x:0,y:0,w:1672,h:941};
  art.foliage(ctx,img,crop,1280,720,0,true);art.shimmer(ctx,crop,1280,720,0,true);assert.equal(calls,0);
  for(let i=0;i<200;i++){art.foliage(ctx,img,crop,1280,720,i/30,false);art.shimmer(ctx,crop,1280,720,i/30,false);art.air(ctx,1280,720,i/30,false);}
  assert.equal(canvases.length,4);assert.ok(canvases.every(c=>c.width<=620&&c.height<=620));assert.ok(calls>1000);
  art.dispose();const stopped=calls;art.foliage(ctx,img,crop,1280,720,8,false);art.shimmer(ctx,crop,1280,720,8,false);art.air(ctx,1280,720,8,false);
  assert.equal(calls,stopped);assert.ok(canvases.every(c=>c.width===1&&c.height===1));
 }finally{globalThis.document=original;}
});
