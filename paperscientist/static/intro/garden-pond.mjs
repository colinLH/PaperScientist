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
export function fishPose(i,time,reduced=false){
  const t=reduced?0:time,phase=i*1.71,[cx,cy,rx,ry]=fishRoutes[i],rate=.065+i*.003,angle=t*rate+phase;
  return {x:cx+Math.cos(angle)*rx,y:cy+Math.sin(angle)*ry,
    vx:-Math.sin(angle)*rx*rate,vy:Math.cos(angle)*ry*rate,
    tail:Math.sin(t*(4.4+i*.17)+phase)*.55,alpha:.79+Math.sin(t*.18+phase)*.06};
}
export function framedFishPose(i,time,reduced,crop){
  const sy=clamp((Math.min(.98,crop.y+crop.h-.04)-.81)/.17,.05,1);
  const left=Math.max(.34,crop.x+.025),right=Math.min(.80,pondSpan(.81+.146*sy).right-.03,crop.x+crop.w-.025);
  const sx=clamp((right-left)/.46,.05,1);
  // Compress the swept envelopes and fish together when cover-cropping trims
  // the pool. Slower travel compensates for tighter turns in shallow viewports.
  const tempo=Math.min(sx,sy)/Math.max(sx,sy),p=fishPose(i,time*tempo,reduced);
  return {...p,x:left+(p.x-.34)*sx,y:.81+(p.y-.81)*sy,vx:p.vx*sx*tempo,vy:p.vy*sy*tempo,size:Math.min(sx,sy)};
}
function clipWater(ctx,w,h,crop){
  ctx.beginPath();outline.forEach(([x,y],i)=>{const p=pondPoint(x,y,w,h,crop);i?ctx.lineTo(p.x,p.y):ctx.moveTo(p.x,p.y);});ctx.closePath();ctx.clip();
}
function drawFish(ctx,p,heading,size,index){
  ctx.save();ctx.translate(p.x,p.y);ctx.rotate(heading);ctx.scale(size,size);ctx.globalAlpha=p.alpha;
  const tail=p.tail,orange=index%3===1?'#c65332':'#d97629',light=index%3===2?'#f4e3b3':'#efb451';
  ctx.globalAlpha=.18;ctx.fillStyle='#304c3f';ctx.beginPath();ctx.ellipse(-.2,1.4,4.3,1.7,0,0,TAU);ctx.fill();
  // Thin, translucent double tail and pectoral fins sit beneath the warm body.
  ctx.fillStyle='#df925b';ctx.globalAlpha=p.alpha*.56;ctx.beginPath();ctx.moveTo(-3,0);
  ctx.bezierCurveTo(-6,-1+tail,-8,-4+tail*2,-10,-3+tail*2);
  ctx.quadraticCurveTo(-8,tail*3,-10,3+tail*2);ctx.bezierCurveTo(-7,4+tail*2,-5,1+tail,-3,0);ctx.fill();
  ctx.beginPath();ctx.moveTo(1,0);ctx.quadraticCurveTo(-1,-5,-3,-3);ctx.lineTo(-1,0);ctx.quadraticCurveTo(-1,4,-3,3);ctx.closePath();ctx.fill();
  ctx.globalAlpha=p.alpha;ctx.fillStyle=orange;ctx.beginPath();ctx.moveTo(5,0);
  ctx.bezierCurveTo(4,-2.4,-1,-2.5,-4,0);ctx.bezierCurveTo(-1,2.5,4,2.4,5,0);ctx.fill();ctx.strokeStyle='#82522f';ctx.lineWidth=.2;ctx.stroke();
  ctx.fillStyle=light;ctx.globalAlpha=p.alpha*.8;ctx.beginPath();ctx.ellipse(.7,-.5,2.6,.78,-.07,0,TAU);ctx.fill();
  ctx.globalAlpha=p.alpha*.75;ctx.fillStyle='#563b27';ctx.beginPath();ctx.arc(3.7,-.85,.28,0,TAU);ctx.fill();
  // A cool surface reflection breaks up the silhouette without a blur pass.
  ctx.strokeStyle='#bed9ca';ctx.globalAlpha=.20;ctx.lineWidth=.45;ctx.beginPath();ctx.moveTo(-2,-.2);ctx.quadraticCurveTo(1,.4,3,.1);ctx.stroke();ctx.restore();
}

export function createGardenPond(){
  let disposed=false;
  return {
    fish(ctx,w,h,time,reduced,crop){
      if(disposed)return 0;
      const count=w<700?4:FISH_BUDGET,size=clamp(h/720*2.5,1,4.8);
      ctx.save();clipWater(ctx,w,h,crop);
      for(let i=0;i<count;i++){
        const index=w<700?[0,2,3,5][i]:i,p=framedFishPose(index,time,reduced,crop),a=pondPoint(p.x,p.y,w,h,crop);
        drawFish(ctx,{...p,...a},Math.atan2(p.vy*h/crop.h,p.vx*w/crop.w),size*p.size*(.85+seed(index+250)*.3),index);
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
    dispose(){disposed=true;}
  };
}
