import * as THREE from './vendor/three.module.min.js';
import {BONES,particleBudget,sampleHand,openness,HandPresence,assignSlots} from './hand-motion.mjs';
import {HandTracker} from './hand-tracker.mjs';

export function createHands({renderer,panel,button,wake,trackerOptions={}}){
  const video=panel.querySelector('video'),canvas=panel.querySelector('canvas'),ctx=canvas.getContext('2d'),status=panel.querySelector('[role=status]');
  const count=particleBudget({cores:navigator.hardwareConcurrency,memory:navigator.deviceMemory,coarse:matchMedia('(pointer:coarse)').matches});
  const sample=sampleHand(count),geometry=new THREE.BufferGeometry();
  geometry.setAttribute('position',new THREE.BufferAttribute(new Float32Array(count*3),3));
  for(const [name,data,size] of [['slot',sample.slot,1],['joints',sample.index,3],['weights',sample.weight,3],['offset',sample.offset,2],['seed',sample.seed,4]])geometry.setAttribute(name,new THREE.BufferAttribute(data,size));
  const joints=Array.from({length:42},()=>new THREE.Vector3()),targets=Array.from({length:42},()=>new THREE.Vector3());
  const uniforms={handJoints:{value:joints},alpha:{value:new THREE.Vector2()},spread:{value:new THREE.Vector2()},viewport:{value:new THREE.Vector2(1,1)},pixelRatio:{value:1},frameAspect:{value:4/3}};
  const material=new THREE.ShaderMaterial({transparent:true,depthWrite:false,depthTest:false,uniforms,
    vertexShader:`attribute float slot;attribute vec3 joints,weights;attribute vec2 offset;attribute vec4 seed;
uniform vec3 handJoints[42];uniform vec2 alpha,spread,viewport;uniform float pixelRatio,frameAspect;
varying float opacity;
vec3 joint(int n){return handJoints[n];}
void main(){int s=int(slot),base=s*21;vec3 a=joint(base+int(joints.x)),b=joint(base+int(joints.y)),c=joint(base+int(joints.z));
  vec3 p=a*weights.x+b*weights.y+c*weights.z;
  vec2 tangent=(b.xy-a.xy)*vec2(frameAspect,1.);tangent/=max(length(tangent),.00001);
  vec2 normal=vec2(-tangent.y,tangent.x)/vec2(frameAspect,1.);
  float palm=length((joint(base).xy-joint(base+9).xy)*vec2(frameAspect,1.));
  p.xy+=normal*offset.x*offset.y*palm;
  vec3 center=(joint(base)+joint(base+5)+joint(base+9)+joint(base+13)+joint(base+17))*.2;
  p=mix(center,p,.42+.58*spread[s]);
  // Fit the whole camera frame, including on portrait screens. Mirror once.
  vec2 fit=vec2(min(1.,frameAspect*viewport.y/viewport.x),min(1.,viewport.x/(frameAspect*viewport.y)))*.92;
  gl_Position=vec4(vec2(1.-p.x*2.,1.-p.y*2.)*fit,clamp(p.z,-.8,.8),1.);
  gl_PointSize=(1.5+seed.x*1.1)*pixelRatio*clamp(1.-p.z*.5,.8,1.25);opacity=alpha[s];
}`,
    fragmentShader:`varying float opacity;void main(){float d=length(gl_PointCoord-.5),aa=fwidth(d);float a=(1.-smoothstep(.5-aa,.5,d))*opacity;if(a<.002)discard;gl_FragColor=vec4(.64,.94,1.,a);}`});
  const points=new THREE.Points(geometry,material);points.frustumCulled=false;
  const overlay=new THREE.Scene();overlay.add(points);const camera=new THREE.Camera();
  const states=[0,1].map(()=>({presence:new HandPresence(),x:.5,y:.5,alpha:0,seen:-Infinity,captured:-Infinity,open:1,spread:1,initialized:false}));
  let dead=false,active=false,last=0,lastPreview=0,detected=[],resume=false;
  panel.dataset.particles=String(count);
  const tracker=new HandTracker({...trackerOptions,video,onStatus:(state,text)=>{panel.dataset.state=state;status.textContent=text;button.setAttribute('aria-pressed',String(tracker.enabled));button.textContent=tracker.enabled?'手势已开启':'开启手势';if(!tracker.enabled)ctx.clearRect(0,0,320,240);wake();},
    onResult:(hands,ms,timestamp)=>{
      const now=performance.now()/1000,slots=assignSlots(hands.map(h=>[h[0].x,h[0].y]),states);detected=hands;
      hands.forEach((hand,i)=>{const s=slots[i],state=states[s];state.x=hand[0].x;state.y=hand[0].y;state.seen=now;state.captured=Number.isFinite(timestamp)?timestamp/1000:now;
        state.open=openness(Float32Array.from(hand.flatMap(p=>[p.x,p.y,p.z])));
        for(let k=0;k<21;k++){const p=hand[k],index=s*21+k;targets[index].set(p.x,p.y,p.z);if(!state.initialized||state.alpha<.02)joints[index].copy(targets[index]);}
        state.initialized=true;
      });panel.dataset.hands=String(hands.length);panel.dataset.inferenceMs=ms.toFixed(1);wake();
    }});
  function toggle(){if(tracker.enabled){tracker.stop();tracker.status('off','手势已关闭');}else tracker.start();}
  button.addEventListener('click',toggle);panel.querySelector('[data-retry]').addEventListener('click',toggle);
  function resize(){const size=renderer.getSize(new THREE.Vector2());uniforms.viewport.value.copy(size);uniforms.pixelRatio.value=renderer.getPixelRatio();}
  function setActive(value){if(value===active)return;active=value;panel.hidden=!active;tracker.setActive(active);}
  function drawPreview(now){
    if(!active||!tracker.stream||video.readyState<2||now-lastPreview<1/15)return;lastPreview=now;
    const scale=Math.min(320/video.videoWidth,240/video.videoHeight),w=video.videoWidth*scale,h=video.videoHeight*scale,x=(320-w)/2,y=(240-h)/2;
    ctx.clearRect(0,0,320,240);ctx.save();ctx.translate(320,0);ctx.scale(-1,1);ctx.drawImage(video,x,y,w,h);
    ctx.strokeStyle='#fff';ctx.fillStyle='#fff';ctx.lineWidth=1.25;ctx.lineCap='round';
    if(states.some(s=>now-s.seen<.3))for(const hand of detected){ctx.beginPath();for(const [a,b] of BONES){ctx.moveTo(x+hand[a].x*w,y+hand[a].y*h);ctx.lineTo(x+hand[b].x*w,y+hand[b].y*h);}ctx.stroke();for(const p of hand){ctx.beginPath();ctx.arc(x+p.x*w,y+p.y*h,2,0,Math.PI*2);ctx.fill();}}
    ctx.restore();
  }
  function render(now,amount){
    if(dead)return;const dt=Math.min(.1,last?now-last:1/30);last=now;const blend=1-Math.exp(-dt/.055);
    states.forEach((state,s)=>{const h=state.presence.update(now,active&&now-state.seen<.16);
      // Late inference must not revive an old hand frame beyond the loss window.
      h.alpha=Math.min(h.alpha,Math.max(0,(.9-(now-state.captured))/.55));
      state.alpha=h.alpha;uniforms.alpha.value.setComponent(s,h.alpha*Math.min(1,Math.max(0,(now-h.born)/.25))*amount);
      state.spread+=(state.open-state.spread)*blend;uniforms.spread.value.setComponent(s,state.spread);
      for(let k=0;k<21;k++)joints[s*21+k].lerp(targets[s*21+k],blend);
    });
    if(video.videoWidth)uniforms.frameAspect.value=video.videoWidth/video.videoHeight;
    drawPreview(now);
    if(amount>0&&(states[0].alpha>0||states[1].alpha>0)){
      const auto=renderer.autoClear;renderer.autoClear=false;renderer.clearDepth();renderer.render(overlay,camera);renderer.autoClear=auto;
    }
    panel.dataset.visibleParticles=String(states.filter(s=>s.alpha>0).length*count/2);
  }
  function visibility(hidden){if(hidden){resume=tracker.enabled;tracker.stop();ctx.clearRect(0,0,320,240);states.forEach(s=>{s.presence.alpha=s.alpha=0;s.seen=-Infinity;s.initialized=false;});}else if(resume){resume=false;tracker.start();}}
  function dispose(){if(dead)return;dead=true;tracker.dispose();geometry.dispose();material.dispose();button.removeEventListener('click',toggle);panel.querySelector('[data-retry]').removeEventListener('click',toggle);}
  resize();tracker.start();
  return {render,resize,setActive,visibility,dispose,get moving(){return active&&tracker.ready;}};
}
