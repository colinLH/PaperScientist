import test from 'node:test';
import assert from 'node:assert/strict';
import {closingOpacity,closingFogPose,closingWaterSpan,cloudPose,createClosingLandscape} from '../paperscientist/static/intro/closing-landscape.mjs';

test('closing landscape fades reversibly after Work and has bounded persistent atmosphere',()=>{
 assert.equal(closingOpacity(9.25),0);assert.equal(closingOpacity(10),1);
 for(let p=9.25;p<10;p+=.01)assert.ok(closingOpacity(p)<=closingOpacity(p+.01));
 for(const t of [0,3,60,10000])for(let i=0;i<7;i++){
  const f=closingFogPose(i,t,3840,2160);assert.ok(Object.values(f).every(Number.isFinite));assert.ok(f.alpha>=.23&&f.alpha<.37);
  assert.deepEqual(closingFogPose(i,t,3840,2160,true),closingFogPose(i,0,3840,2160,true));
 }
 assert.notDeepEqual(cloudPose(0,0),cloudPose(0,3));
 for(let y=.81;y<1;y+=.01){const s=closingWaterSpan(y);assert.ok(s.left>0&&s.right<1&&s.left<s.right);}
});

test('closing artwork loads near the final chapter, uses bounded shared-clock effects, and stops cleanly',()=>{
 const oldDoc=globalThis.document,oldDpr=globalThis.devicePixelRatio;let draws=0,wakes=0;
 const nodes=[],gradient={addColorStop(){}};
 const ctx=new Proxy({createRadialGradient:()=>gradient,drawImage(){draws++;}},{get:(o,k)=>o[k]??(()=>{})});
 const node=()=>({style:{},hidden:false,dataset:{},children:[],append(x){this.children.push(x);},remove(){this.removed=true;},replaceChildren(){this.children=[];},addEventListener(){},removeAttribute(k){delete this[k];}});
 const canvas={...node(),width:0,height:0,getContext:()=>ctx},img={...node(),complete:false,naturalWidth:0,naturalHeight:0};
 const clouds=node(),branches=node(),plate=node(),host=node();
 plate.querySelector=s=>({'img':img,'canvas':canvas,'.closing-clouds':clouds,'.closing-branches':branches}[s]);host.querySelector=()=>plate;
 globalThis.document={createElement(tag){const n=tag==='canvas'?{...node(),getContext:()=>ctx}:node();nodes.push(n);return n;}};globalThis.devicePixelRatio=2;
 try{
  const art=createClosingLandscape(host,()=>wakes++);
  assert.equal(art.render(4,0,1280,720),0);assert.equal(img.src,undefined);
  assert.equal(art.render(9,1,1280,720),0);assert.match(img.src,/disc-pagoda-4k/);
  Object.assign(img,{complete:true,naturalWidth:3840,naturalHeight:2160});
  assert.equal(art.render(10,2,3840,2160),1);assert.equal(host.hidden,false);assert.ok(canvas.width*canvas.height<1401000);
  for(let i=0;i<120;i++)art.render(10,2+i/30,3840,2160);assert.equal(nodes.length,5);assert.equal(clouds.children.length,2);assert.equal(branches.children.length,2);assert.ok(draws>500);
  const still=wakes;art.tap(.5,.3);assert.equal(wakes,still);art.tap(.5,.9);assert.equal(wakes,still+1);
  art.render(10,7,390,844,true);assert.equal(host.dataset.motion,'0.000');assert.equal(clouds.hidden,true);assert.equal(branches.hidden,true);
  art.render(8,8,390,844);assert.equal(host.hidden,true);const stopped=draws;art.render(7,9,390,844);assert.equal(draws,stopped);
  art.render(10,10,1280,720);assert.equal(host.hidden,false);
  art.dispose();const done=draws;art.render(10,11,1280,720);assert.equal(draws,done);assert.equal(img.src,undefined);assert.equal(canvas.width,1);assert.ok(nodes.slice(0,4).every(n=>n.removed&&n.style.backgroundImage==='none'));
 }finally{globalThis.document=oldDoc;globalThis.devicePixelRatio=oldDpr;}
});
