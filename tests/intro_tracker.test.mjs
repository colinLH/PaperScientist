import test from 'node:test';
import assert from 'node:assert/strict';
import {HandTracker} from '../paperscientist/static/intro/hand-tracker.mjs';

const deferred=()=>{let resolve,reject;const promise=new Promise((a,b)=>{resolve=a;reject=b;});return {promise,resolve,reject};};
function env(overrides={}){
  const track={enabled:true,stops:0,stop(){this.stops++;}},stream={getTracks:()=>[track],getVideoTracks:()=>[track]},messages=[],results=[],statuses=[];
  const video={srcObject:null,readyState:2,currentTime:1,play:async()=>{}};
  const worker={postMessage:m=>messages.push(m),terminate(){this.terminated=true;}};
  let closes=0,captures=0;
  const tracker=new HandTracker({video,media:async()=>stream,worker:()=>worker,bitmap:async()=>{captures++;return {close(){closes++;}};},onResult:(r)=>results.push(r),onStatus:(s)=>statuses.push(s),...overrides});
  const ready=async()=>{tracker.setActive(true);await tracker.start();worker.onmessage({data:{type:'ready'}});clearTimeout(tracker.timer);};
  return {tracker,video,worker,track,stream,messages,results,statuses,ready,get closes(){return closes;},get captures(){return captures;}};
}

test('requests video only, leaves model unloaded outside chapter four, and disposes tracks',async()=>{
  let constraints;const e=env();e.tracker.media=async c=>{constraints=c;return e.stream;};
  await e.tracker.start();assert.equal(constraints.audio,false);assert.equal(e.messages.length,0);assert.equal(e.track.enabled,false);
  e.tracker.setActive(true);assert.equal(e.messages[0].type,'init');assert.equal(e.track.enabled,true);
  e.tracker.dispose();assert.equal(e.track.stops,1);assert.equal(e.worker.terminated,true);assert.equal(e.video.srcObject,null);
});
test('permission denied can be retried without duplicate cameras',async()=>{
  const e=env();e.tracker.media=async()=>{throw Object.assign(new Error(),{name:'NotAllowedError'});};
  await e.tracker.start();assert.equal(e.tracker.state,'unavailable');assert.equal(e.tracker.enabled,false);
  e.tracker.media=async()=>e.stream;await e.tracker.start();await e.tracker.start();assert.equal(e.video.srcObject,e.stream);e.tracker.dispose();assert.equal(e.track.stops,1);
});
test('late permission after shutdown releases the stream without loading a worker',async()=>{
  const wait=deferred(),e=env({media:()=>wait.promise});const pending=e.tracker.start();e.tracker.dispose();wait.resolve(e.stream);await pending;
  assert.equal(e.track.stops,1);assert.equal(e.video.srcObject,null);assert.equal(e.messages.length,0);
});
test('backpressure allows one frame, deduplicates video timestamps, and pauses detection',async()=>{
  const e=env();await e.ready();await e.tracker.capture();await e.tracker.capture();assert.equal(e.captures,1);
  e.worker.onmessage({data:{type:'result',landmarks:[[]],ms:100}});clearTimeout(e.tracker.timer);
  await e.tracker.capture();clearTimeout(e.tracker.timer);assert.equal(e.captures,1);
  e.video.currentTime=2;e.tracker.setActive(false);await e.tracker.capture();assert.equal(e.captures,1);assert.equal(e.track.enabled,false);
  e.tracker.dispose();assert.equal(e.tracker.timer,0);assert.equal(e.tracker.watchdog,0);
});
test('bitmap captured after a stop is closed rather than sent to a dead worker',async()=>{
  const wait=deferred(),e=env({bitmap:()=>wait.promise});await e.ready();const pending=e.tracker.capture();e.tracker.stop();let closed=false;
  wait.resolve({close(){closed=true;}});await pending;assert.equal(closed,true);assert.equal(e.messages.length,1);
});
test('worker failures free model and camera resources, and allow a retry',async()=>{
  const e=env();await e.ready();e.worker.onmessage({data:{type:'error',message:'test model failure'}});
  assert.equal(e.tracker.state,'unavailable');assert.equal(e.worker.terminated,true);assert.equal(e.track.stops,1);assert.equal(e.tracker.enabled,false);assert.deepEqual(e.results.at(-1),[]);e.tracker.dispose();
});
