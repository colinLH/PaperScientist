import test from 'node:test';
import assert from 'node:assert/strict';
import {leafPose,canopyPose,fogPose,waterSpan,LEAF_BUDGET,FOG_BUDGET,createGardenAtmosphere,createGardenCanopy} from '../paperscientist/static/intro/garden-atmosphere.mjs';

test('garden particles and deformations stay bounded through long running scenes and resize',()=>{
 for(const [w,h] of [[390,844],[1280,720],[3840,2160]])for(const t of [0,.1,8,120,1e6]){
  for(let i=0;i<LEAF_BUDGET;i++){
   const p=leafPose(i,t,w,h);assert.ok(Object.values(p).every(Number.isFinite));assert.ok(p.alpha>=0&&p.alpha<=.8);assert.ok(p.y>=-.11*h&&p.y<=1.09*h);assert.ok(p.scale<10);
   assert.deepEqual(leafPose(i,t,w,h,true),leafPose(i,0,w,h,true));
  }
  for(let i=0;i<3;i++){const p=canopyPose(i,t);assert.ok(Math.abs(p.angle)<=.018&&Math.abs(p.x)<=6&&Math.abs(p.y)<=2.5);assert.deepEqual(canopyPose(i,t,true),{angle:0,x:0,y:0});}
  for(let i=0;i<FOG_BUDGET;i++)assert.deepEqual(fogPose(i,t,w,h,true),fogPose(i,0,w,h,true));
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
  const art=createGardenAtmosphere(),crop={x:0,y:0,w:3840,h:2160};
  art.shimmer(ctx,crop,1280,720,0,true);assert.equal(calls,0);
  for(let i=0;i<200;i++){art.shimmer(ctx,crop,1280,720,i/30,false);art.air(ctx,1280,720,i/30,false);}
  assert.equal(canvases.length,1);assert.ok(canvases.every(c=>c.width<=320&&c.height<=128));assert.ok(calls>1000);
  art.dispose();const stopped=calls;art.shimmer(ctx,crop,1280,720,8,false);art.air(ctx,1280,720,8,false);
  assert.equal(calls,stopped);assert.ok(canvases.every(c=>c.width===1&&c.height===1));
 }finally{globalThis.document=original;}
});

test('pagoda fog stays present and moves visibly over a few seconds, without loop fade-outs',()=>{
 for(let t=0;t<=120;t+=.25){
  const veils=Array.from({length:5},(_,i)=>fogPose(i+4,t,1280,720));
  assert.ok(veils.every(p=>p.alpha>=.48&&p.alpha<=.591));
  // At least one veil always covers the central pagoda column.
  assert.ok(veils.some(p=>Math.abs(p.x-1280*.61)<p.width*.32));
 }
 assert.ok(Math.abs(fogPose(4,3,1280,720).x-fogPose(4,0,1280,720).x)>50);
 assert.ok(Math.abs(canopyPose(0,2).angle-canopyPose(0,0).angle)>.01);
});

test('native-resolution canopy reuses three layers through resize and releases image references',()=>{
 const original=globalThis.document,layers=[];let writes=0;
 globalThis.document={createElement:()=>({style:new Proxy({},{set(o,k,v){writes++;o[k]=v;return true;}}),remove(){this.removed=true;}})};
 const host={append(el){layers.push(el);},hidden:false},img={complete:true,naturalWidth:3840,naturalHeight:2160,src:'/garden.webp'};
 try{
  const art=createGardenCanopy(host,img),crop={x:0,y:0,w:3840,h:2160};
  art.render(crop,3840,2160,0,false);assert.equal(layers.length,3);assert.equal(layers[0].style.backgroundSize,'3840px 2160px');
  const initial=writes;for(let i=0;i<100;i++)art.render(crop,3840,2160,i/30,false);assert.equal(writes-initial,300);
  art.render(crop,1280,720,4,false);assert.equal(layers[0].style.backgroundSize,'1280px 720px');
  art.render(crop,1280,720,5,true);assert.equal(host.hidden,true);
  art.render(crop,1280,720,6,false);assert.equal(host.hidden,false);
  art.dispose();const end=writes;art.render(crop,3840,2160,7,false);assert.equal(writes,end);assert.ok(layers.every(p=>p.removed&&p.style.backgroundImage==='none'));
 }finally{globalThis.document=original;}
});
