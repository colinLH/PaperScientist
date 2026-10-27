import test from 'node:test';
import assert from 'node:assert/strict';
import {PreludeInteraction,interactivePoint,turnPoint,bindPreludeInput} from '../paperscientist/static/intro/prelude-interaction.mjs';

test('drag rotates the artwork, limits tilt, smooths reversal and resets without teleporting',()=>{
 const state=new PreludeInteraction(),p={x:.5,y:.4,z:.6},before=interactivePoint(p,1,state);
 state.drag(.2,.2);state.update(1/30);const moved=interactivePoint(p,1,state);
 assert.notDeepEqual(moved,before);assert.ok(state.yaw>0&&state.yaw<state.targetYaw);
 const yaw=state.yaw;state.drag(-.4,10);assert.equal(state.yaw,yaw);assert.ok(state.targetPitch<=.85);state.update(1/30);assert.ok(state.yaw<yaw);
 state.reset();for(let i=0;i<100;i++)state.update(1/30);assert.ok(Math.abs(state.yaw)<1e-6);assert.ok(Math.abs(state.pitch)<1e-6);
 for(const a of [-2,0,2])assert.ok(Math.abs(Math.hypot(...Object.values(turnPoint(p,a,.7)))-Math.hypot(...Object.values(p)))<1e-10);
});
test('pointer bends the stream and click pulses have a bounded population and expire',()=>{
 const state=new PreludeInteraction();state.over=true;state.held=true;for(let i=0;i<10;i++)state.update(1/30);
 const p={x:.3,y:.1,z:0},near=interactivePoint(p,0,state,{x:0,y:0}),far=interactivePoint(p,0,state,{x:8,y:8});
 assert.ok(Math.hypot(near.y-far.y,near.z-far.z)>.1);
 for(let i=0;i<30;i++)state.pulse(i/30,0);assert.equal(state.pulses.length,4);
 for(let i=0;i<60;i++)state.update(1/30);assert.equal(state.pulses.length,0);
 state.pulse();state.update(1/30,true);assert.equal(state.pulses.length,0);assert.equal(state.activated,true);const flow=state.flow;state.update(.05,true);assert.equal(state.flow,flow);
});
test('touch keeps vertical chapter gestures separate from horizontal artwork dragging and cancels capture',()=>{
 Object.assign(globalThis,{innerWidth:390,innerHeight:844});const handlers=new Map(),captures=new Set(),calls=[];
 const surface={addEventListener(k,f){handlers.set(k,f);},setPointerCapture(i){captures.add(i);},hasPointerCapture:i=>captures.has(i),releasePointerCapture(i){captures.delete(i);}};
 const art={hold:v=>calls.push(['hold',v]),over(){},pointer(){},drag:(...v)=>calls.push(['drag',...v]),tap:()=>calls.push(['tap']),activate(){},reset(){}};
 const input=bindPreludeInput(surface,art,()=>{});const emit=(name,x,y)=>handlers.get(name)({button:0,pointerId:1,pointerType:'touch',clientX:x,clientY:y});
 emit('pointerdown',100,400);emit('pointermove',102,500);emit('pointerup',102,500);let stopped=false;handlers.get('touchend')({stopPropagation(){stopped=true;}});assert.equal(stopped,false);assert.ok(!calls.some(x=>x[0]==='drag'||x[0]==='tap'));
 emit('pointerdown',100,400);emit('pointermove',180,410);emit('pointerup',180,410);handlers.get('touchend')({stopPropagation(){stopped=true;}});assert.equal(stopped,true);assert.ok(calls.some(x=>x[0]==='drag'));assert.equal(captures.size,0);
 emit('pointerdown',100,400);input.cancel();assert.equal(captures.size,0);assert.deepEqual(calls.at(-1),['hold',false]);input.dispose();
});
