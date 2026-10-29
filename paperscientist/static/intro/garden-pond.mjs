import {clamp,smooth} from './motion.mjs';
import {leafPose} from './garden-atmosphere.mjs?v=4';

const TAU=Math.PI*2,PERIOD=48,FLOAT_TIME=8;
export const FISH_BUDGET=6;
// Separate swept envelopes, not a shared crossing path. Even the tail's full
// reach fits between neighboring envelopes at the smallest supported viewport.
const fishRoutes=[
  [.385,.822,.027,.008],[.545,.824,.034,.009],[.680,.850,.018,.009],
  [.430,.945,.035,.012],[.600,.946,.038,.012],[.766,.968,.020,.012]
];
const seed=i=>{const n=Math.sin(i*127.1+311.7)*43758.5453;return n-Math.floor(n);};
// A conservative water mask, traced in the original painting's coordinates.
// It leaves the bridge piers and foreground rocks outside the swimming area.
const banks=[[.78,.34,.59],[.81,.30,.70],[.88,.35,.77],[.94,.36,.82],[1,.28,.83]];
const outline=[...banks.map(([y,l])=>[l,y]),...banks.slice().reverse().map(([y,,r])=>[r,y])];
export function pondSpan(y){
  y=clamp(y,.78,1);let j=1;while(j<banks.length-1&&y>banks[j][0])j++;
  const a=banks[j-1],b=banks[j],u=(y-a[0])/(b[0]-a[0]);
  return {left:a[1]+(b[1]-a[1])*u,right:a[2]+(b[2]-a[2])*u};
}
export function inPond(x,y,margin=0){const s=pondSpan(y);return y>=.78&&y<=1&&x>=s.left+margin&&x<=s.right-margin;}
export function pondPoint(x,y,w,h,crop){return {x:(x-crop.x)/crop.w*w,y:(y-crop.y)/crop.h*h};}

// Every water-bound leaf owns one deterministic landing per cycle. The ripple
// is derived from that exact landing, so resize/re-entry cannot emit duplicates.
export function landingLeaf(i,time){
  const slot=i-Math.floor(i/3),impactAt=3+slot*4;
  const age=((time-impactAt)%PERIOD+PERIOD)%PERIOD;
  const y=.835+seed(i+150)*.115,span=pondSpan(y),x=span.left+.065+(span.right-span.left-.13)*seed(i+170);
  const spin=seed(i+80)*TAU,floating=age<FLOAT_TIME;
  if(floating)return {x:x+age*.0018,y:y+age*.001,impactX:x,impactY:y,age,floating,
    angle:spin+5+Math.sin((time-age)*.63+spin)*.45+age*.06,
    flutter:(.35+.65*Math.abs(Math.cos((time-age)*.8+spin)))*(1-smooth(age/.65))+.75*smooth(age/.65),flatten:1-smooth(age/.65)*.67,alpha:time-age<0?0:(1-smooth((age-4)/4))*.8};
  const u=(age-FLOAT_TIME)/(PERIOD-FLOAT_TIME),origin=i%2?.96:.04,sy=.08+seed(i+190)*.22;
  return {x:origin+(x-origin)*u+Math.sin(u*TAU*1.4+spin)*Math.sin(u*Math.PI)*.065,y:sy+(y-sy)*u,
    impactX:x,impactY:y,age,floating,angle:spin+u*5+Math.sin(time*.63+spin)*.45,
    flutter:.35+.65*Math.abs(Math.cos(time*.8+spin)),flatten:1,alpha:smooth(u/.12)*.8};
}
export function pondLeafPose(i,time,w,h,reduced=false,crop={x:0,y:0,w:1,h:1}){
  if(i%3===2)return leafPose(i,time,w,h,reduced);
  const p=landingLeaf(i,reduced?0:time),point=pondPoint(p.x,p.y,w,h,crop);
  return {...p,...point,scale:Math.max(.65,Math.min(1.35,h/800))*(3+seed(i+60)*4),alpha:reduced?0:p.alpha};
}
export function fishPose(i,time,reduced=false,offset=0){
  const t=reduced?0:time,phase=i*1.71,[cx,cy,rx,ry]=fishRoutes[i],rate=.065+i*.003,angle=t*rate+phase+(reduced?0:offset);
  return {x:cx+Math.cos(angle)*rx,y:cy+Math.sin(angle)*ry,
    vx:-Math.sin(angle)*rx*rate,vy:Math.cos(angle)*ry*rate,
    tail:Math.sin(t*(4.4+i*.17)+phase)*.55,alpha:.79+Math.sin(t*.18+phase)*.06};
}
export function framedFishPose(i,time,reduced,crop,offset=0){
  const sy=clamp((Math.min(.98,crop.y+crop.h-.04)-.81)/.17,.05,1);
  const left=Math.max(.34,crop.x+.025),right=Math.min(.80,pondSpan(.81+.146*sy).right-.03,crop.x+crop.w-.025);
  const sx=clamp((right-left)/.46,.05,1);
  // Compress the swept envelopes and fish together when cover-cropping trims
  // the pool. Slower travel compensates for tighter turns in shallow viewports.
  const tempo=Math.min(sx,sy)/Math.max(sx,sy),p=fishPose(i,time*tempo,reduced,offset),rate=.065+i*.003;
  return {...p,x:left+(p.x-.34)*sx,y:.81+(p.y-.81)*sy,vx:p.vx*sx*tempo,vy:p.vy*sy*tempo,size:Math.min(sx,sy),
    rx:fishRoutes[i][2]*sx,ry:fishRoutes[i][3]*sy,rate:rate*tempo,angle:reduced?i*1.71:time*tempo*rate+i*1.71+offset};
}

export const fishIndices=width=>width<700?[0,2,3,5]:[0,1,2,3,4,5];
// Bigger, brighter fish still fit inside disjoint swept envelopes. Size is
// bounded by the closest pair of envelopes, independently of swimming phase.
export function fishScale(w,h,crop){
  const poses=fishIndices(w).map(i=>framedFishPose(i,0,false,crop));let clearance=Infinity;
  for(let i=0;i<poses.length;i++)for(let j=i+1;j<poses.length;j++){
    const a=poses[i],b=poses[j],ax=a.x-Math.cos(a.angle)*a.rx,ay=a.y-Math.sin(a.angle)*a.ry,bx=b.x-Math.cos(b.angle)*b.rx,by=b.y-Math.sin(b.angle)*b.ry;
    const dx=Math.max(0,Math.abs(ax-bx)-a.rx-b.rx)*w/crop.w,dy=Math.max(0,Math.abs(ay-by)-a.ry-b.ry)*h/crop.h;
    clearance=Math.min(clearance,Math.hypot(dx,dy));
  }
  return Math.min(clamp(h/720*3.5,1.4,7)*poses[0].size,clearance*.43/11.5);
}

export function createFishSchool(){
  const fresh=()=>({offset:0,speed:0,alarm:0,tail:0,direction:1,heading:null,threat:null});
  const fish=Array.from({length:FISH_BUDGET},fresh),turnRate=2.2;
  return {
    pose(i,time,reduced,crop){
      const f=fish[i],p=framedFishPose(i,time,reduced,crop,f.offset);
      return {...p,heading:reduced?null:f.heading,alpha:.94,tail:reduced?0:Math.sin(time*(4.4+i*.17)+i*1.71+f.tail)*(.55+Math.min(.25,f.speed*.3))};
    },
    tick(dt,time,w,h,crop,reduced){
      if(reduced){for(const f of fish){f.alarm=f.speed=0;f.threat=null;}return;}
      // Turn toward the escape tangent before accelerating. Integrate the full
      // signed phase (including cruise) so turning/holding cannot drift toward
      // the ripple through the otherwise time-driven patrol phase.
      const elapsed=clamp(dt,0,.1),steps=Math.max(1,Math.ceil(elapsed/.016)),step=elapsed/steps;
      for(let n=0;n<steps;n++)for(let i=0;i<FISH_BUDGET;i++){
        const f=fish[i],p=framedFishPose(i,time-elapsed+n*step,false,crop,f.offset);
        f.alarm=Math.max(0,f.alarm-step);
        f.speed+=((f.alarm>0?.9:0)-f.speed)*(1-Math.exp(-step*(f.alarm>0?12:2.5)));
        const a=p.rx*w/crop.w,b=p.ry*h/crop.h;
        const curvature=a*b/Math.max(1e-6,a*a*Math.sin(p.angle)**2+b*b*Math.cos(p.angle)**2);
        const tangent=Math.atan2(b*Math.cos(p.angle)*f.direction,-a*Math.sin(p.angle)*f.direction);
        f.heading??=Math.atan2(b*Math.cos(p.angle),-a*Math.sin(p.angle));
        const delta=Math.atan2(Math.sin(tangent-f.heading),Math.cos(tangent-f.heading));
        f.heading+=clamp(delta,-turnRate*step,turnRate*step);
        const alignment=Math.max(0,Math.cos(tangent-f.heading))**4;
        let velocity=f.direction*Math.min(f.speed+p.rate,1.6/curvature)*alignment;
        if(f.threat){
          const q=pondPoint(p.x,p.y,w,h,crop),hit=pondPoint(f.threat.x,f.threat.y,w,h,crop),next=p.angle+velocity*step;
          const dx=a*(Math.cos(next)-Math.cos(p.angle)),dy=b*(Math.sin(next)-Math.sin(p.angle));
          // Stop at the safe end of this route instead of looping back toward
          // the disturbance. Repeated taps replace the origin, not the pose.
          if(Math.hypot(q.x+dx-hit.x,q.y+dy-hit.y)<Math.hypot(q.x-hit.x,q.y-hit.y))velocity=0;
          if(f.alarm===0&&f.speed<.03)f.threat=null;
        }
        f.offset=(f.offset+(velocity-p.rate)*step)%TAU;f.tail=(f.tail+Math.abs(velocity)*step*12)%TAU;
      }
    },
    startle(x,y,time,w,h,crop,reduced=false){
      if(reduced||!inPond(crop.x+x/w*crop.w,crop.y+y/h*crop.h))return 0;
      const radius=clamp(h*.12,65,165);let affected=0;
      for(const i of fishIndices(w)){
        const p=this.pose(i,time,false,crop),q=pondPoint(p.x,p.y,w,h,crop);
        if(Math.hypot(q.x-x,q.y-y)>radius)continue;
        const f=fish[i],a=p.rx*w/crop.w,b=p.ry*h/crop.h;
        const gradient=(q.x-x)*(-a*Math.sin(p.angle))+(q.y-y)*b*Math.cos(p.angle);
        // The distance derivative chooses the direction away from the tap.
        // At a stationary point, compare both nearby positions to break ties.
        const distance=sign=>Math.hypot(q.x-x+a*(Math.cos(p.angle+sign*.02)-Math.cos(p.angle)),q.y-y+b*(Math.sin(p.angle+sign*.02)-Math.sin(p.angle)));
        const difference=distance(1)-distance(-1);
        f.direction=Math.abs(gradient)>1e-6?Math.sign(gradient):Math.abs(difference)>1e-6?Math.sign(difference):f.direction;
        f.threat={x:crop.x+x/w*crop.w,y:crop.y+y/h*crop.h};f.alarm=3.6;affected++;
      }return affected;
    },
    get startled(){return fish.filter(f=>f.alarm>0||f.speed>.03).length;},
    reset(){for(const f of fish)Object.assign(f,fresh());}
  };
}
function clipWater(ctx,w,h,crop){
  ctx.beginPath();outline.forEach(([x,y],i)=>{const p=pondPoint(x,y,w,h,crop);i?ctx.lineTo(p.x,p.y):ctx.moveTo(p.x,p.y);});ctx.closePath();ctx.clip();
}
function drawFish(ctx,p,heading,size,index){
  ctx.save();ctx.translate(p.x,p.y);ctx.rotate(heading);ctx.scale(size,size);ctx.globalAlpha=p.alpha;
  const tail=p.tail,orange=index%3===1?'#ed632a':'#f19723',light=index%3===2?'#fff5dc':'#ffe3a0';
  ctx.globalAlpha=.26;ctx.fillStyle='#183e36';ctx.beginPath();ctx.ellipse(-.2,1.4,4.7,2,0,0,TAU);ctx.fill();
  // Thin, translucent double tail and pectoral fins sit beneath the warm body.
  ctx.fillStyle='#f4ae66';ctx.globalAlpha=p.alpha*.78;ctx.beginPath();ctx.moveTo(-3,0);
  ctx.bezierCurveTo(-6,-1+tail,-8,-4+tail*2,-10,-3+tail*2);
  ctx.quadraticCurveTo(-8,tail*3,-10,3+tail*2);ctx.bezierCurveTo(-7,4+tail*2,-5,1+tail,-3,0);ctx.fill();
  ctx.beginPath();ctx.moveTo(1,0);ctx.quadraticCurveTo(-1,-5,-3,-3);ctx.lineTo(-1,0);ctx.quadraticCurveTo(-1,4,-3,3);ctx.closePath();ctx.fill();
  ctx.globalAlpha=p.alpha;ctx.fillStyle=orange;ctx.beginPath();ctx.moveTo(5,0);
  ctx.bezierCurveTo(4,-2.4,-1,-2.5,-4,0);ctx.bezierCurveTo(-1,2.5,4,2.4,5,0);ctx.fill();ctx.strokeStyle='#934420';ctx.lineWidth=.3;ctx.stroke();
  ctx.fillStyle=light;ctx.globalAlpha=p.alpha*.8;ctx.beginPath();ctx.ellipse(.7,-.5,2.6,.78,-.07,0,TAU);ctx.fill();
  ctx.globalAlpha=p.alpha*.75;ctx.fillStyle='#563b27';ctx.beginPath();ctx.arc(3.7,-.85,.28,0,TAU);ctx.fill();
  // A cool surface reflection breaks up the silhouette without a blur pass.
  ctx.strokeStyle='#bed9ca';ctx.globalAlpha=.20;ctx.lineWidth=.45;ctx.beginPath();ctx.moveTo(-2,-.2);ctx.quadraticCurveTo(1,.4,3,.1);ctx.stroke();ctx.restore();
}

export function createGardenPond(){
  let disposed=false,lastTime=null,view=null;const school=createFishSchool();
  return {
    tap(x,y){if(disposed||!view)return {water:false,fish:0};const {w,h,time,reduced,crop}=view;
      if(!inPond(crop.x+x/w*crop.w,crop.y+y/h*crop.h))return {water:false,fish:0};
      return {water:true,fish:school.startle(x,y,time,w,h,crop,reduced)};
    },
    get startled(){return school.startled;},
    pause(){lastTime=null;view=null;},
    fish(ctx,w,h,time,reduced,crop){
      if(disposed)return 0;
      const indices=fishIndices(w),count=indices.length,size=fishScale(w,h,crop);
      school.tick(lastTime===null?0:time-lastTime,time,w,h,crop,reduced);lastTime=time;view={w,h,time,reduced,crop};
      ctx.save();clipWater(ctx,w,h,crop);
      for(let i=0;i<count;i++){
        const index=indices[i],p=school.pose(index,time,reduced,crop),a=pondPoint(p.x,p.y,w,h,crop);
        drawFish(ctx,{...p,...a},p.heading??Math.atan2(p.vy*h/crop.h,p.vx*w/crop.w),size,index);
      }ctx.restore();return count;
    },
    surface(ctx,w,h,time,reduced,crop){
      if(disposed||reduced)return 0;
      let active=0;ctx.save();clipWater(ctx,w,h,crop);
      for(let i=0;i<(w<700?10:18);i++){
        if(i%3===2)continue;const leaf=landingLeaf(i,time);if(leaf.age>=3.2||time-leaf.age<0)continue;active++;
        const p=pondPoint(leaf.impactX,leaf.impactY,w,h,crop),scale=clamp(h/720,.7,3);
        for(let ring=0;ring<3;ring++){
          const age=leaf.age-ring*.26;if(age<0)continue;const r=(2+age*19)*scale;
          ctx.beginPath();ctx.ellipse(p.x,p.y,r,r*.27,0,0,TAU);
          ctx.lineWidth=scale*.8;ctx.strokeStyle=`rgba(244,242,210,${(1-age/3.2)*.48})`;ctx.stroke();
          ctx.beginPath();ctx.ellipse(p.x,p.y+scale,r+scale,r*.27,0,.2,Math.PI);
          ctx.strokeStyle=`rgba(46,82,69,${(1-age/3.2)*.20})`;ctx.stroke();
        }
      }ctx.restore();return active;
    },
    dispose(){disposed=true;school.reset();view=null;lastTime=null;}
  };
}
