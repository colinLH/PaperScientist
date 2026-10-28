import {clamp,smooth} from './motion.mjs';

const TAU=Math.PI*2;
const leafColors=['#ab6838','#c69042','#9a5032','#b1a05b'];
const noise=i=>{const n=Math.sin(i*127.1+311.7)*43758.5453;return n-Math.floor(n);};
export const LEAF_BUDGET=18;
const leaves=Array.from({length:LEAF_BUDGET},(_,i)=>({phase:noise(i),duration:42+noise(i+20)*30,x:noise(i+40),size:3+noise(i+60)*4,spin:noise(i+80)*TAU}));

// Fixed seeds and the existing scene clock make reverse navigation/resizing
// deterministic; no emitters, timers, or unbounded particle arrays are needed.
export function leafPose(i,time,w,h,reduced=false){
  time=reduced?0:time;
  const seed=leaves[i],age=((time/seed.duration+seed.phase)%1+1)%1;
  return {x:(seed.x*.96-.08+age*.21+Math.sin(age*TAU*1.4+seed.spin)*.035)*w,y:(age*1.18-.10)*h,
    angle:seed.spin+age*5+Math.sin(time*.63+seed.spin)*.45,scale:Math.max(.65,Math.min(1.35,h/800))*seed.size,
    flutter:.35+.65*Math.abs(Math.cos(time*.8+seed.spin)),alpha:reduced?0:smooth(age/.09)*(1-smooth((age-.88)/.12))*.8};
}
export function canopyPose(i,time,reduced=false){
  const breeze=Math.sin(time*.72+i*.8)*.7+Math.sin(time*1.13+i)*.3;
  return {angle:reduced?0:breeze*.018,x:reduced?0:breeze*6,y:reduced?0:Math.sin(time*.8+i)*2.5};
}
export const FOG_BUDGET=9;
export function fogPose(i,time,w,h,reduced=false){
  const t=reduced?0:time,phase=i*1.37;
  if(i<4)return {x:w*(.13+i*.25+Math.sin(t*.19+phase)*.12),y:h*(.20+(i%2)*.09+Math.sin(t*.24+phase)*.018),
    width:w*.61,height:h*.19,alpha:.34+(Math.sin(t*.27+phase)+1)*.045};
  // Persistent overlapping veils travel across the pagoda, rather than fading
  // out like particle smoke. Positions are tied to the artwork, not viewport.
  return {x:w*(.61+Math.sin(t*(.28+(i-4)*.018)+phase)*.12),y:h*(.12+(i-4)*.049+Math.sin(t*.31+phase)*.016),
    width:w*(.26+noise(i+200)*.13),height:h*(.08+noise(i+220)*.04),alpha:.48+(Math.sin(t*.32+phase)+1)*.055};
}
export function waterSpan(y){const depth=clamp((y-.71)/.29,0,1);return {left:.29-depth*.14,right:.75+depth*.11};}

// Native-resolution CSS image layers keep foliage crisp on 4K displays;
// only their transforms change per frame. The shared image is decoded once.
export function createGardenCanopy(host,img){
  const regions=[[0,0,.23,.31],[0,.26,.20,.33],[.82,0,.18,.59]];
  const layers=regions.map(()=>{const el=document.createElement('div');el.className='garden-canopy-patch';host.append(el);return el;});
  let key='',disposed=false;
  return {render(crop,w,h,time,reduced){
    if(disposed)return;host.hidden=reduced||!img.complete||!img.naturalWidth;if(host.hidden)return;
    const iw=img.naturalWidth,ih=img.naturalHeight,scale=w/crop.w,next=[w,h,iw,ih,crop.x,crop.y,img.src].join(':');
    if(next!==key){key=next;regions.forEach(([x,y,pw,ph],i)=>{const s=layers[i].style;
      Object.assign(s,{left:(x*iw-crop.x)*scale+'px',top:(y*ih-crop.y)*scale+'px',width:pw*iw*scale+'px',height:ph*ih*scale+'px',backgroundImage:`url("${img.src}")`,backgroundSize:`${iw*scale}px ${ih*scale}px`,backgroundPosition:`${-x*iw*scale}px ${-y*ih*scale}px`,transformOrigin:i===2?'100% 0':'0 0'});
    });}
    layers.forEach((el,i)=>{const p=canopyPose(i,time),size=Math.min(1.5,Math.max(.65,w/1280));el.style.transform=`translate3d(${p.x*size}px,${p.y*size}px,0) rotate(${p.angle}rad)`;});
  },dispose(){disposed=true;layers.forEach(el=>{el.style.backgroundImage='none';el.remove();});host.hidden=true;}};
}

// One small cached mist texture; no full-image repaint or additional clock.
export function createGardenAtmosphere(){
  const fog=document.createElement('canvas');fog.width=320;fog.height=128;
  const f=fog.getContext('2d');
  if(f)for(let i=0;i<22;i++){
    const x=35+noise(i+300)*250,y=35+noise(i+330)*58,r=20+noise(i+360)*35;
    const g=f.createRadialGradient(x,y,0,x,y,r);g.addColorStop(0,'rgba(244,249,240,.68)');g.addColorStop(.5,'rgba(238,246,239,.38)');g.addColorStop(1,'rgba(238,246,239,0)');
    f.fillStyle=g;f.fillRect(x-r,y-r,r*2,r*2);
  }
  let disposed=false;
  function shimmer(ctx,crop,w,h,time,reduced,iw=3840,ih=2160){
    if(disposed||reduced)return;
    ctx.save();ctx.lineCap='round';
    for(let i=0;i<72;i++){
      const sy=.735+noise(i+450)*.255,span=waterSpan(sy),sx=span.left+(span.right-span.left)*noise(i+540);
      const x=(sx*iw-crop.x)/crop.w*w,y=(sy*ih-crop.y)/crop.h*h;
      const wave=Math.sin(time*(.65+noise(i+630)*.5)+i*2.4),alpha=Math.pow((wave+1)/2,3)*(.12+(sy-.73)*.45);
      const length=(3+noise(i+720)*24)*(w/1280),shift=Math.sin(time*.52+i)*2;
      ctx.strokeStyle=`rgba(255,249,211,${alpha})`;ctx.lineWidth=.6+(sy-.73)*3;ctx.beginPath();ctx.moveTo(x+shift,y);ctx.quadraticCurveTo(x+length*.5+shift,y+wave*.7,x+length+shift,y);ctx.stroke();
    }ctx.restore();
  }
  function air(ctx,w,h,time,reduced,crop={x:0,y:0,w:1,h:1}){
    if(disposed)return;
    const sw=w/crop.w,sh=h/crop.h;
    ctx.save();for(let i=0;i<FOG_BUDGET;i++){const p=fogPose(i,time,sw,sh,reduced);ctx.globalAlpha=p.alpha;ctx.drawImage(fog,p.x-crop.x*sw-p.width/2,p.y-crop.y*sh-p.height/2,p.width,p.height);}
    if(!reduced)for(let i=0;i<(w<700?10:LEAF_BUDGET);i++){
      const p=leafPose(i,time,w,h);ctx.save();ctx.globalAlpha=p.alpha;ctx.translate(p.x,p.y);ctx.rotate(p.angle);ctx.scale(p.scale*p.flutter,p.scale);
      ctx.fillStyle=leafColors[i%4];ctx.beginPath();ctx.moveTo(-1,0);ctx.bezierCurveTo(-.35,-.8,.6,-.65,1.2,0);ctx.bezierCurveTo(.5,.62,-.4,.65,-1,0);ctx.fill();
      ctx.strokeStyle='#563c2477';ctx.lineWidth=.12;ctx.beginPath();ctx.moveTo(-1.2,0);ctx.quadraticCurveTo(0,.07,1.1,0);ctx.stroke();ctx.restore();
    }ctx.restore();
  }
  return {shimmer,air,dispose(){disposed=true;fog.width=fog.height=1;}};
}
