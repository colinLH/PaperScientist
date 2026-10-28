import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync,existsSync} from 'node:fs';
import {createHash} from 'node:crypto';
import vm from 'node:vm';
import {RECORD_SCORE,recordIndices,toggleRecord} from '../paperscientist/static/intro/record-score.mjs';
import {RecordChoreography,deckLayout,recordPlacement,recordLink,linkPoint} from '../paperscientist/static/intro/record-player.mjs';
import {RecordMusic} from '../paperscientist/static/intro/record-audio.mjs';
import {discLayout} from '../paperscientist/static/intro/reference-art.mjs';

test('all fifteen order-independent combinations have distinct attributed, local full-length music',()=>{
 const credits=JSON.parse(readFileSync(new URL('../paperscientist/static/intro/audio/records/credits.json',import.meta.url),'utf8'));
 assert.equal(new Set(RECORD_SCORE.filter(Boolean).map(t=>t.url)).size,15);
 assert.equal(new Set(credits.map(t=>t.sha256)).size,15);
 for(let mask=1;mask<16;mask++){
  const ids=recordIndices(mask);assert.equal(ids.reduce(toggleRecord,0),mask);assert.equal(ids.toReversed().reduce(toggleRecord,0),mask);
  assert.equal(credits[mask-1].title,RECORD_SCORE[mask].title);assert.equal(credits[mask-1].license,'CC BY 4.0');
  assert.ok(existsSync(new URL('../paperscientist/static/intro/audio/records/'+String(mask).padStart(2,'0')+'.opus',import.meta.url)));
  const bytes=readFileSync(new URL('../paperscientist/static/intro/audio/records/'+String(mask).padStart(2,'0')+'.opus',import.meta.url));
  assert.equal(createHash('sha256').update(bytes).digest('hex'),credits[mask-1].sha256);
 }
});

test('records start still, land before spinning, reverse mid-flight continuously and settle back',()=>{
 const c=new RecordChoreography();for(let i=0;i<100;i++)c.step(.033);
 assert.ok(c.items.every(i=>i.p===0&&i.spin===0));c.mask=5;
 c.step(.033);assert.equal(c.items[0].spin,0);assert.equal(c.items[2].spin,0);
 for(let i=0;i<7;i++)c.step(.033);const p=c.items[0].p;c.mask=0;
 c.step(.01);assert.ok(Math.abs(c.items[0].p-p)<.08);
 for(let i=0;i<240;i++)c.step(.033);assert.ok(c.items.every(i=>i.p===0&&Math.abs(i.spin)<.001));
 c.mask=15;for(let i=0;i<120;i++)c.step(.033);assert.ok(c.items.every(i=>i.p===1&&i.spin>20));
 const spin=c.items[0].spin;c.step(0);assert.equal(c.items[0].spin,spin);
 c.step(.03,true);assert.ok(c.items.every(i=>i.p===1&&i.spin===0));
});

test('decks stay in view and record centers meet the photographed platter through resize',()=>{
 for(const [w,h] of [[351,658],[1152,562],[2094,902],[3456,1684]])for(const yaw of [-1.8,0,1.8]){
  const poses=[0,1,2,3].map(i=>discLayout(w,h,i,yaw,0,true));
  poses.forEach((p,i)=>{
   const d=deckLayout(p,w,h,i);assert.ok(d.x>=0&&d.x+d.w<=w&&d.y>=0&&d.y+d.h<h);
   const a=recordPlacement(p,d,1,{yaw,pitch:.8},{x:1,y:1});assert.equal(a.x,d.cx);assert.ok(Math.abs(a.y-d.cy)<1e-8);assert.equal(a.rx,24);assert.equal(a.ry,0);assert.equal(a.z,0);
  });
 }
});

test('links follow left-to-right neighbors; skipped records are bypassed below the artwork',()=>{
 for(const [w,h] of [[351,658],[1152,562],[3456,1684]]){
  const ps=[0,1,2,3].map(i=>discLayout(w,h,i,0,0,true)),ds=ps.map((p,i)=>deckLayout(p,w,h,i));
  for(let mask=1;mask<16;mask++){
   const ids=recordIndices(mask),links=ids.slice(1).map((i,j)=>recordLink(ds[ids[j]],ds[i],ps,h));
   assert.equal(links.length,ids.length-1);
   for(const l of links){
    assert.equal(l.skipped,l.to-l.from>1);assert.ok(l.length>0);
    for(let n=1;n<l.points.length;n++)assert.ok(l.points[n].x>=l.points[n-1].x);
    for(let i=l.from+1;i<l.to;i++)for(const q of l.points){assert.ok(q.y>ps[i].y);assert.ok(Math.hypot(q.x-ps[i].x,q.y-ps[i].y)>ps[i].d*.52,JSON.stringify({w,h,mask,i,q,pose:ps[i]}));}
    assert.equal(linkPoint(l,0).x,l.points[0].x);assert.equal(linkPoint(l,l.length).x,l.points.at(-1).x);
   }
  }
 }
});

function fixture(saved={}){
 const pending=new Map(),elements=[],events=[],db={...saved};let next=0,blocked=false,defer=false;
 const param=()=>({value:0,cancelAndHoldAtTime(){},linearRampToValueAtTime(v){this.value=v;}});
 const node=()=>({gain:param(),connect(){return this;},disconnect(){this.disconnected=true;}});
 const ctx={currentTime:1,createGain:node,createMediaElementSource:node};
 const createAudio=url=>{const handlers=new Map(),audio={url,dataset:{},currentTime:0,duration:240,paused:true,removed:false,
  addEventListener(type,fn,options){handlers.set(type,fn);options?.signal?.addEventListener('abort',()=>handlers.delete(type));},
  emit(type){handlers.get(type)?.();},pause(){this.paused=true;},play(){this.paused=false;if(blocked)return Promise.reject(new Error('denied'));if(defer)return new Promise((resolve,reject)=>{this.resolve=resolve;this.reject=reject;});return Promise.resolve();},
  removeAttribute(){},load(){},remove(){this.removed=true;}};elements.push(audio);return audio;};
 const options={createAudio,storage:{getItem:k=>db[k],setItem:(k,v)=>db[k]=v},notify:(...e)=>events.push(e),schedule:fn=>{pending.set(++next,fn);return next;},cancel:id=>pending.delete(id)};
 const music=new RecordMusic(ctx,node(),options);
 return {music,elements,events,db,options,ctx,block:v=>blocked=v,defer:v=>defer=v,flush(){for(const [id,fn] of [...pending]){pending.delete(id);fn();}}};
}

test('solo and combination retain separate positions through pause, rapid switch, mute and reload',async()=>{
 const f=fixture(),m=f.music;m.set(1);await Promise.resolve();let a=f.elements.at(-1);a.emit('loadedmetadata');a.currentTime=23;
 m.set(3);await Promise.resolve();let b=f.elements.at(-1);b.emit('loadedmetadata');b.currentTime=41;f.flush();assert.equal(m.positions[1],23);
 m.set(1);await Promise.resolve();a=f.elements.at(-1);a.emit('loadedmetadata');assert.equal(a.currentTime,23);f.flush();assert.equal(m.positions[3],41);
 m.set(1,false);f.flush();assert.equal(m.voices.size,0);m.set(1,true);await Promise.resolve();a=f.elements.at(-1);a.emit('loadedmetadata');assert.equal(a.currentTime,23);
 m.dispose();assert.ok(f.elements.every(a=>a.paused&&a.removed));
 const restored=new RecordMusic(f.ctx,{},f.options);restored.set(3);await Promise.resolve();b=f.elements.at(-1);b.emit('loadedmetadata');assert.equal(b.currentTime,41);restored.dispose();
});

test('rapid multi-selection uses at most two decoders and stale completion cannot restart music',async()=>{
 const f=fixture();f.defer(true);
 for(const mask of [1,3,7,15,13,9,1,0,15,7,0]){f.music.set(mask);assert.ok(f.music.voices.size<=2);}
 for(const a of f.elements)a.resolve();await Promise.resolve();f.flush();assert.equal(f.music.voices.size,0);assert.ok(f.elements.every(a=>a.paused));f.music.dispose();
});

test('load failures latch until explicit retry and preserve saved progress before metadata',async()=>{
 const f=fixture({'paperscientist.record-progress.v1':'{"4":81}'});f.block(true);f.music.set(4);await Promise.resolve();await Promise.resolve();
 assert.equal(f.events.at(-1)[0],'error');assert.equal(f.music.voices.size,0);assert.equal(f.music.positions[4],81);
 for(let i=0;i<30;i++)f.music.set(4);assert.equal(f.elements.length,1);
 f.block(false);f.music.set(4,false);f.music.set(4,true);await Promise.resolve();f.elements.at(-1).emit('loadedmetadata');assert.equal(f.elements.at(-1).currentTime,81);f.music.dispose();
});

test('browser timer defaults do not receive the music controller as a native receiver',async()=>{
 const f=fixture(),source=readFileSync(new URL('../paperscientist/static/intro/record-audio.mjs',import.meta.url),'utf8').replace(/^import.*\n/gm,'').replace('export class RecordMusic','class RecordMusic');
 let scheduled=0,cancelled=0;
 const Music=vm.runInNewContext(source+'\nRecordMusic;',{RECORD_SCORE,AbortController,setTimeout:function(){assert.equal(this,undefined);scheduled++;return 1;},clearTimeout:function(){assert.equal(this,undefined);cancelled++;}});
 const {schedule,cancel,...options}=f.options,m=new Music(f.ctx,{},options);
 m.set(1);await Promise.resolve();m.set(3);m.set(1);m.dispose();
 assert.ok(scheduled>=2&&cancelled>=3);
});
