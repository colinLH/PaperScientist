import {clamp,smooth} from './motion.mjs';
import {leafPose} from './garden-atmosphere.mjs?v=4';

const TAU=Math.PI*2,PERIOD=48,FLOAT_TIME=8;
export const FISH_BUDGET=6;
// Separate starting poses and reduced-motion patrols. Interactive swimming
// below uses free steering with bank and neighbor clearance.
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
// Bound body/tail size by the initial layout, including narrow cover crops.
// The interactive school keeps this clearance while swimming freely.
export function fishScale(w,h,crop){
  const poses=fishIndices(w).map(i=>framedFishPose(i,0,false,crop));let clearance=Infinity;
  for(let i=0;i<poses.length;i++)for(let j=i+1;j<poses.length;j++){
    const a=poses[i],b=poses[j],ax=a.x-Math.cos(a.angle)*a.rx,ay=a.y-Math.sin(a.angle)*a.ry,bx=b.x-Math.cos(b.angle)*b.rx,by=b.y-Math.sin(b.angle)*b.ry;
    const dx=Math.max(0,Math.abs(ax-bx)-a.rx-b.rx)*w/crop.w,dy=Math.max(0,Math.abs(ay-by)-a.ry-b.ry)*h/crop.h;
    clearance=Math.min(clearance,Math.hypot(dx,dy));
  }
  return Math.min(clamp(h/720*3.5,1.4,7)*poses[0].size,clearance*.43/11.5);
}

// Fish steer in the pool rather than reversing on a one-dimensional ellipse.
// Every visible heading is the direction of travel; no separate spin/hold state.
export function createFishSchool(){
  const fresh=()=>({ready:false,x:0,y:0,heading:0,turn:0,speed:0,alarm:0,tail:0,threat:null,launch:0,age:0,sx:1,sy:1});
  const fish=Array.from({length:FISH_BUDGET},fresh);
  function init(f,i,time,w,h,crop){
    if(f.ready)return;const p=framedFishPose(i,time,false,crop);
    Object.assign(f,{ready:true,x:p.x,y:p.y,heading:Math.atan2(p.vy*h/crop.h,p.vx*w/crop.w),
      speed:Math.hypot(p.vx*w/crop.w,p.vy*h/crop.h),tail:(p.angle-i*1.71)/(.065+i*.003)*(4.4+i*.17)+i*1.71,sx:w/crop.w,sy:h/crop.h});
  }
  function bounds(y,r,w,h,crop){
    const sy=h/crop.h,sx=w/crop.w,top=Math.max(0,(.78-crop.y)*sy)+r+2,bottom=Math.min(h,(1-crop.y)*sy)-r-2;
    y=clamp(y,top,bottom);const ys=[y-r,y,y+r].map(v=>crop.y+v/sy);
    for(const [edge] of banks)if(edge>ys[0]&&edge<ys[2])ys.push(edge);
    const spans=ys.map(pondSpan);
    return {top,bottom,left:Math.max(0,(Math.max(...spans.map(s=>s.left))-crop.x)*sx)+r+2,
      right:Math.min(w,(Math.min(...spans.map(s=>s.right))-crop.x)*sx)-r-2};
  }
  function contain(p,r,w,h,crop){const b=bounds(p.y,r,w,h,crop);p.y=clamp(p.y,b.top,b.bottom);p.x=clamp(p.x,b.left,b.right);}
  function safeHeading(q,desired,heading,threat,size,speed,w,h,crop,points,index){
    const hit=threat?pondPoint(threat.x,threat.y,w,h,crop):null,r=size*11.5;
    const valid=p=>{const b=bounds(p.y,r,w,h,crop);return p.y>=b.top&&p.y<=b.bottom&&p.x>=b.left&&p.x<=b.right&&points.every((other,k)=>k===index||Math.hypot(p.x-other.x,p.y-other.y)>=r*2+2);};
    for(const look of [Math.max(r*2.2,speed*.65),r*.7]){
      let best=null,score=-Infinity;
      for(let j=-12;j<=12;j++){
        const a=desired+j*Math.PI/12,dx=Math.cos(a)*look,dy=Math.sin(a)*look;
        if(!valid({x:q.x+dx,y:q.y+dy})||!valid({x:q.x+dx*.5,y:q.y+dy*.5}))continue;
        const away=hit?(Math.hypot(q.x+dx-hit.x,q.y+dy-hit.y)-Math.hypot(q.x-hit.x,q.y-hit.y))/look:0;
        const value=Math.cos(a-desired)+Math.cos(a-heading)*.18+away*3;
        if(value>score){score=value;best=a;}
      }if(best!==null)return best;
    }return desired;
  }
  function escapeHeading(q,hit,f,size,w,h,crop){
    let best=f.heading,bestScore=-Infinity;const initial=Math.hypot(q.x-hit.x,q.y-hit.y);
    // Pick one short launch arc on input. This avoids chasing an angle that
    // flips across +/-pi while the fish is still making its first tail stroke.
    for(let j=-8;j<=8;j++){
      const target=f.heading+j*Math.PI/8,p={...q};let heading=f.heading,speed=f.speed,min=initial,clipped=0;
      for(let n=0;n<12;n++){
        const delta=Math.atan2(Math.sin(target-heading),Math.cos(target-heading));heading+=clamp(delta,-.32,.32);
        const dx=p.x-hit.x,dy=p.y-hit.y,d=Math.hypot(dx,dy),toward=Math.cos(heading)*dx+Math.sin(heading)*dy<0;
        const v=toward?Math.min(size*22,Math.max(size*4,d*1.6)):size*38;speed+=(v-speed)*.5;
        p.x+=Math.cos(heading)*speed*.04;p.y+=Math.sin(heading)*speed*.04;const old={...p};contain(p,size*11.5,w,h,crop);
        clipped+=Math.hypot(old.x-p.x,old.y-p.y);min=Math.min(min,Math.hypot(p.x-hit.x,p.y-hit.y));
      }
      const score=(Math.hypot(p.x-hit.x,p.y-hit.y)-initial)*2+(min-initial)*3-clipped*4-Math.abs(j)*size*.08;
      if(score>bestScore){bestScore=score;best=target;}
    }return best;
  }
  return {
    pose(i,time,reduced,crop){
      const f=fish[i],p=framedFishPose(i,time,reduced,crop);
      if(reduced||!f.ready)return {...p,heading:null,bend:0,alpha:.94,tail:reduced?0:p.tail};
      return {...p,x:f.x,y:f.y,vx:Math.cos(f.heading)*f.speed/f.sx,vy:Math.sin(f.heading)*f.speed/f.sy,
        heading:f.heading,bend:clamp(f.turn/8,-1,1)*.65,alpha:.94,tail:Math.sin(f.tail)*(.55+Math.min(.25,f.speed/f.sx*3))};
    },
    tick(dt,time,w,h,crop,reduced){
      if(reduced){for(const f of fish){f.alarm=0;f.threat=null;}return;}
      const elapsed=clamp(dt,0,.1),steps=Math.max(1,Math.ceil(elapsed/(1/120))),step=elapsed/steps;
      const ids=fishIndices(w),size=fishScale(w,h,crop),radius=size*11.5,cruise=size*3.2;
      for(const i of ids)init(fish[i],i,time-elapsed,w,h,crop);
      for(let n=0;n<steps;n++){
        const points=ids.map(i=>pondPoint(fish[i].x,fish[i].y,w,h,crop));
        for(let j=0;j<ids.length;j++){
          const i=ids[j],f=fish[i],q=points[j];
          f.alarm=Math.max(0,f.alarm-step);f.age+=step;
          // A short C-start bends the body and moves it throughout the turn.
          // Keep a little forward momentum even for a head-on disturbance.
          let gx=Math.cos(f.heading),gy=Math.sin(f.heading),approachingDistance=null;
          if(f.threat&&f.alarm>0){
            const hit=pondPoint(f.threat.x,f.threat.y,w,h,crop),dx=q.x-hit.x,dy=q.y-hit.y,d=Math.hypot(dx,dy);
            if(f.age<.3&&d>1&&(gx*dx+gy*dy)<0)approachingDistance=d;
            const weight=1-smooth(f.age/.45);
            gx=dx/Math.max(1,d)*(1-weight)+Math.cos(f.launch)*weight;gy=dy/Math.max(1,d)*(1-weight)+Math.sin(f.launch)*weight;
          }else {f.threat=null;const drift=Math.sin(time*.38+i*2.1)*.12;gx=Math.cos(f.heading+drift);gy=Math.sin(f.heading+drift);}
          for(let k=0;k<ids.length;k++){
            if(k===j)continue;const other=fish[ids[k]],p=points[k];
            const dx=q.x-p.x+(Math.cos(f.heading)*f.speed-Math.cos(other.heading)*other.speed)*.16;
            const dy=q.y-p.y+(Math.sin(f.heading)*f.speed-Math.sin(other.heading)*other.speed)*.16;
            const d=Math.hypot(dx,dy),reach=radius*3.3;
            if(d<reach&&d>1e-5){const repulsion=(1-d/reach)*4;gx+=dx/d*repulsion;gy+=dy/d*repulsion;}
          }
          const desired=safeHeading(q,Math.atan2(gy,gx),f.heading,f.threat,size,f.speed,w,h,crop,points,j),raw=desired-f.heading;let delta=Math.atan2(Math.sin(raw),Math.cos(raw));
          const maxTurn=f.alarm>0?8:3.6,targetTurn=clamp(delta*11,-maxTurn,maxTurn);
          f.turn+=(targetTurn-f.turn)*(1-Math.exp(-step*24));f.heading+=f.turn*step;
          const alignment=(1+Math.cos(delta))*.5,burst=f.alarm>0?size*48:cruise;
          let targetSpeed=burst*(.38+.62*alignment);
          if(approachingDistance!==null)targetSpeed=Math.min(targetSpeed,Math.max(size*4,approachingDistance*1.6));
          f.speed+=(targetSpeed-f.speed)*(1-Math.exp(-step*(approachingDistance!==null?30:targetSpeed>f.speed?22:4.5)));
          q.x+=Math.cos(f.heading)*f.speed*step;q.y+=Math.sin(f.heading)*f.speed*step;
          contain(q,radius,w,h,crop);f.tail+=step*(4.4+Math.min(16,f.speed/size*.25));
        }
        // Predictive steering does the normal avoidance. Bounded pair projection
        // handles simultaneous clicks and narrow resizes without overlap.
        for(let pass=0;pass<3;pass++)for(let j=0;j<points.length;j++)for(let k=j+1;k<points.length;k++){
          const a=points[j],b=points[k],dx=b.x-a.x,dy=b.y-a.y,d=Math.hypot(dx,dy),gap=radius*2+2;
          if(d>=gap)continue;const nx=d>1e-5?dx/d:1,ny=d>1e-5?dy/d:0,shift=(gap-d)*.5;
          a.x-=nx*shift;a.y-=ny*shift;b.x+=nx*shift;b.y+=ny*shift;contain(a,radius,w,h,crop);contain(b,radius,w,h,crop);
        }
        for(let j=0;j<ids.length;j++){const f=fish[ids[j]],p=points[j];f.x=crop.x+p.x/w*crop.w;f.y=crop.y+p.y/h*crop.h;f.sx=w/crop.w;f.sy=h/crop.h;}
      }
    },
    startle(x,y,time,w,h,crop,reduced=false){
      if(reduced||!inPond(crop.x+x/w*crop.w,crop.y+y/h*crop.h))return 0;
      const radius=clamp(h*.12,65,165);let affected=0;
      for(const i of fishIndices(w)){
        const p=this.pose(i,time,false,crop),q=pondPoint(p.x,p.y,w,h,crop);if(Math.hypot(q.x-x,q.y-y)>radius)continue;
        const f=fish[i];init(f,i,time,w,h,crop);
        const size=fishScale(w,h,crop);f.threat={x:crop.x+x/w*crop.w,y:crop.y+y/h*crop.h};
        f.launch=escapeHeading(q,{x,y},f,size,w,h,crop);f.alarm=1.25;f.age=0;affected++;
      }return affected;
    },
    get startled(){return fish.filter(f=>f.alarm>0).length;},
    reset(){for(const f of fish)Object.assign(f,fresh());}
  };
}
function clipWater(ctx,w,h,crop){
  ctx.beginPath();outline.forEach(([x,y],i)=>{const p=pondPoint(x,y,w,h,crop);i?ctx.lineTo(p.x,p.y):ctx.moveTo(p.x,p.y);});ctx.closePath();ctx.clip();
}
function drawFish(ctx,p,heading,size,index){
  ctx.save();ctx.translate(p.x,p.y);ctx.rotate(heading);ctx.scale(size,size);ctx.globalAlpha=p.alpha;
  const bend=-(p.bend||0)*2,tail=clamp(p.tail+bend,-1.1,1.1),orange=index%3===1?'#ed632a':'#f19723',light=index%3===2?'#fff5dc':'#ffe3a0';
  ctx.globalAlpha=.26;ctx.fillStyle='#183e36';ctx.beginPath();ctx.ellipse(-.2,1.4,4.7,2,0,0,TAU);ctx.fill();
  // Thin, translucent double tail and pectoral fins sit beneath the warm body.
  ctx.fillStyle='#f4ae66';ctx.globalAlpha=p.alpha*.78;ctx.beginPath();ctx.moveTo(-3,bend*.45);
  ctx.bezierCurveTo(-6,-1+tail,-8,-4+tail*2,-10,-3+tail*2);
  ctx.quadraticCurveTo(-8,tail*3,-10,3+tail*2);ctx.bezierCurveTo(-7,4+tail*2,-5,1+tail,-3,bend*.45);ctx.fill();
  ctx.beginPath();ctx.moveTo(1,0);ctx.quadraticCurveTo(-1,-5,-3,-3);ctx.lineTo(-1,0);ctx.quadraticCurveTo(-1,4,-3,3);ctx.closePath();ctx.fill();
  ctx.globalAlpha=p.alpha;ctx.fillStyle=orange;ctx.beginPath();ctx.moveTo(5,0);
  ctx.bezierCurveTo(4,-2.4,-1,-2.5+bend*.4,-4,bend*.5);ctx.bezierCurveTo(-1,2.5+bend*.4,4,2.4,5,0);ctx.fill();ctx.strokeStyle='#934420';ctx.lineWidth=.3;ctx.stroke();
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
