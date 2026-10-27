import test from 'node:test';
import assert from 'node:assert/strict';
import {ribbonGeometry,lensOffsets,sculptureOpacity} from '../paperscientist/static/intro/research-sculpture.mjs';
import {createPrelude} from '../paperscientist/static/intro/cosmic-art.mjs';

test('sculpted strip has finite unit normals and bounded reusable geometry',()=>{
 const g=ribbonGeometry(),p=g.attributes.position,n=g.attributes.normal;
 assert.ok(p.count<6000);assert.ok(g.index.count<32000);
 for(let i=0;i<p.count;i++){
  assert.ok(Number.isFinite(p.getX(i)+p.getY(i)+p.getZ(i)));
  assert.ok(Math.abs(Math.hypot(n.getX(i),n.getY(i),n.getZ(i))-1)<1e-5);
 }
 assert.ok([...g.index.array].every(i=>i<p.count));g.dispose();
});
test('lens selection keeps optical stages ordered and reversible transitions never flash at the globe',()=>{
 for(let selected=-1;selected<6;selected++)for(const spread of [0,.2,.8,1]){
  const xs=lensOffsets(selected,spread);for(let i=1;i<xs.length;i++)assert.ok(xs[i]-xs[i-1]>=.38);
 }
 assert.equal(sculptureOpacity(0),1);assert.equal(sculptureOpacity(1),0);assert.equal(sculptureOpacity(2),1);assert.equal(sculptureOpacity(3),0);
 for(let p=0;p<3;p+=.01){assert.ok(sculptureOpacity(p)>=0&&sculptureOpacity(p)<=1);assert.ok(Math.abs(sculptureOpacity(p)-sculptureOpacity(p+.1-.1))<1e-12);}
});
test('studio shares the existing clock and stage selection, stops at later chapters and disposes',()=>{
 Object.assign(globalThis,{innerWidth:1280,innerHeight:720,devicePixelRatio:1});
 const gradient={addColorStop(){}};const ctx=new Proxy({createLinearGradient:()=>gradient,createRadialGradient:()=>gradient},{get:(o,k)=>o[k]??(()=>{})});
 const art=createPrelude({getContext:()=>ctx,style:{},dataset:{}});let frame,hidden=0,disposed=false;
 art.attachSculpture({available:true,render(v){frame=v;return [{index:3,x:900,y:300}];},hide(){hidden++;},dispose(){disposed=true;}});
 art.render(0,0);art.render(0,1);assert.ok(frame.time>0);art.render(0,2,true);assert.equal(frame.time,0);
 art.render(2,3);art.activate();art.render(2,4);assert.equal(frame.state.selected,3);assert.match(art.info.selection,/实验/);
 frame=null;art.render(1,5);assert.equal(frame,null);art.render(4,6);assert.equal(frame,null);assert.ok(hidden>=2);
 art.dispose();assert.equal(disposed,true);
});
