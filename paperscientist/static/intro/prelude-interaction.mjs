import {clamp,smooth} from './motion.mjs';

export const concepts=['文献','假设','方法','实验','证据','数据','讨论','表达'];
export const experiments=['问题','方法','数据','实验','评估','表达'];
export const conceptNotes=['沿着引用找到关联文献','把观察转化为可检验的假设','连接问题与具体设计','用实验检验设计选择','让结论与证据相互对应','保留可追溯的数据来源','解释结果、边界与局限','将发现组织成清晰的论文'];
export const experimentNotes=['明确要回答的问题','设计与创新点对应的模块','选择数据并记录处理过程','运行可复现的实验','比较基线、消融与误差','用图表与文字解释发现'];

export function turnPoint(q,yaw,pitch){
  const z=q.z||0,c=Math.cos(yaw),s=Math.sin(yaw),x=q.x*c+z*s,d=-q.x*s+z*c;
  return {x,y:q.y*Math.cos(pitch)-d*Math.sin(pitch),z:q.y*Math.sin(pitch)+d*Math.cos(pitch)};
}
export function interactivePoint(q,phase,state,pointer={x:9,y:9}){
  const rotated=turnPoint(q,state.yaw*smooth(phase),state.pitch*smooth(phase));
  const wave=1-smooth(phase),dx=rotated.x-pointer.x,dy=rotated.y-pointer.y;
  const pull=Math.exp(-(dx*dx+dy*dy)/.55)*state.hover;
  rotated.y+=wave*pull*(.18+state.press*.38)*Math.sin(dx*3+state.flow);
  rotated.z+=wave*pull*(.18+state.press*.3);
  if(!state.reduced)for(const pulse of state.pulses){
    const d=Math.hypot(rotated.x-pulse.x,rotated.y-pulse.y),ring=Math.exp(-(((d-pulse.age*1.5)/.18)**2))*(1-pulse.age/1.8);
    rotated.y+=ring*.18*wave;rotated.z+=ring*.12;
  }
  const perspective=1/(1-rotated.z*.12);
  return {x:rotated.x*perspective,y:rotated.y*perspective,z:rotated.z,light:pull};
}
export class PreludeInteraction{
  constructor(){this.yaw=this.pitch=this.targetYaw=this.targetPitch=0;this.press=this.hover=0;this.held=false;this.over=false;this.pulses=[];this.selected=-1;this.speed=1;this.flow=0;this.reduced=false;this.actions=0;this.activated=false;}
  drag(dx,dy){this.targetYaw+=clamp(dx,-.45,.45)*3;this.targetPitch=clamp(this.targetPitch+dy*2,-.85,.85);this.actions++;}
  pulse(x=0,y=0){this.activated=true;this.pulses.push({x,y,age:0});if(this.pulses.length>4)this.pulses.shift();this.actions++;}
  update(dt,reduced=false){
    this.reduced=reduced;dt=clamp(dt,0,.05);const k=reduced?1:1-Math.exp(-dt*12);
    this.yaw+=(this.targetYaw-this.yaw)*k;this.pitch+=(this.targetPitch-this.pitch)*k;
    this.press+=((this.held?1:0)-this.press)*k;this.hover+=((this.over?1:0)-this.hover)*k;
    if(!reduced){this.flow+=dt*this.speed;for(const p of this.pulses)p.age+=dt;this.pulses=this.pulses.filter(p=>p.age<1.8);}
    else this.pulses=[];
  }
  reset(){this.targetYaw=this.targetPitch=0;this.selected=-1;this.pulses=[];this.speed=1;this.held=false;this.activated=false;this.actions++;}
}

// Pointer capture belongs only to the artwork. Vertical touch swipes still
// reach the chapter navigator; horizontal gestures rotate the artwork.
export function bindPreludeInput(surface,art,wake){
  const abort=new AbortController(),options={signal:abort.signal};let gesture=null,claimed=false;
  surface.addEventListener('pointerdown',e=>{
    if(e.button!==0)return;gesture={id:e.pointerId,x:e.clientX,y:e.clientY,lastX:e.clientX,lastY:e.clientY,type:e.pointerType,moved:false};claimed=false;
    surface.setPointerCapture(e.pointerId);art.hold(true);art.pointer(e.clientX/innerWidth*2-1,e.clientY/innerHeight*2-1);wake();
  },options);
  surface.addEventListener('pointermove',e=>{
    if(!gesture||gesture.id!==e.pointerId)return;
    const dx=e.clientX-gesture.x,dy=e.clientY-gesture.y;gesture.moved ||= Math.hypot(dx,dy)>7;
    if(gesture.type!=='touch'||Math.abs(dx)>Math.abs(dy)||claimed){
      if(gesture.moved){claimed=true;art.drag((e.clientX-gesture.lastX)/innerWidth,(e.clientY-gesture.lastY)/innerHeight);wake();}
    }
    gesture.lastX=e.clientX;gesture.lastY=e.clientY;
  },options);
  function release(e,cancel=false){if(!gesture||gesture.id!==e.pointerId)return;const tap=!gesture.moved;gesture=null;art.hold(false);if(!cancel&&tap)art.tap(e.clientX,e.clientY);if(surface.hasPointerCapture(e.pointerId))surface.releasePointerCapture(e.pointerId);wake();}
  surface.addEventListener('pointerup',e=>release(e),options);
  surface.addEventListener('pointercancel',e=>release(e,true),options);
  surface.addEventListener('lostpointercapture',()=>{gesture=null;art.hold(false);},options);
  surface.addEventListener('pointerenter',()=>art.over(true),options);
  surface.addEventListener('pointerleave',()=>{if(!gesture)art.over(false);},options);
  surface.addEventListener('touchend',e=>{if(claimed)e.stopPropagation();claimed=false;},{...options,passive:true});
  surface.addEventListener('keydown',e=>{
    if(e.target!==surface&&e.target?.closest?.('button,a,input,select,textarea'))return;
    if(!['ArrowLeft','ArrowRight','Enter',' ','Escape'].includes(e.key))return;e.preventDefault();e.stopPropagation();
    if(e.key==='Escape')art.reset();else if(e.key==='ArrowLeft'||e.key==='ArrowRight')art.drag(e.key==='ArrowLeft'?-.1:.1,0);else art.activate();wake();
  },options);
  return {cancel(){const id=gesture?.id;gesture=null;claimed=false;if(id!==undefined&&surface.hasPointerCapture(id))surface.releasePointerCapture(id);art.hold(false);art.over(false);},dispose(){abort.abort();gesture=null;art.hold(false);}};
}
