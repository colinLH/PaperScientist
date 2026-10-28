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
  const breeze=Math.sin(time*.34+i*.8)*.7+Math.sin(time*.71+i)*.3;
  return {angle:reduced?0:breeze*.0045,x:reduced?0:breeze*1.8,y:reduced?0:Math.sin(time*.39+i)*.9};
}
export function fogPose(i,time,w,h,reduced=false){
  const t=reduced?0:time,phase=i*1.37;
  return {x:w*(.12+i*.155+Math.sin(t*.033+phase)*.10),y:h*(.20+(i%3)*.068+Math.sin(t*.055+phase)*.014),
    width:w*(.43+noise(i+200)*.24),height:h*(.14+noise(i+220)*.08),alpha:.13+(Math.sin(t*.071+phase)+1)*.035};
}
export function waterSpan(y){const depth=clamp((y-.71)/.29,0,1);return {left:.29-depth*.14,right:.75+depth*.11};}

// All masks/textures are made once. Only the small foliage patches move, so
// the pagoda, bridge, composition and underlying painting remain stationary.
export function createGardenAtmosphere(){
  const fog=document.createElement('canvas');fog.width=320;fog.height=128;
  const f=fog.getContext('2d');
  if(f)for(let i=0;i<22;i++){
    const x=35+noise(i+300)*250,y=35+noise(i+330)*58,r=20+noise(i+360)*35;
    const g=f.createRadialGradient(x,y,0,x,y,r);g.addColorStop(0,'rgba(249,251,238,.26)');g.addColorStop(.5,'rgba(246,249,237,.13)');g.addColorStop(1,'rgba(246,249,237,0)');
    f.fillStyle=g;f.fillRect(x-r,y-r,r*2,r*2);
  }
  let patches=[],source=null,disposed=false;
  function prepare(img){
    if(source===img||!img.complete||!img.naturalWidth)return;
    source=img;
    patches=[[0,0,.23,.31],[0,.26,.20,.33],[.82,0,.18,.59]].map(([x,y,w,h])=>{
      const sprite=document.createElement('canvas'),iw=img.naturalWidth,ih=img.naturalHeight;
      const ratio=Math.min(1,620/(w*iw),620/(h*ih));sprite.width=Math.ceil(w*iw*ratio);sprite.height=Math.ceil(h*ih*ratio);
      const c=sprite.getContext('2d');if(c){c.drawImage(img,x*iw,y*ih,w*iw,h*ih,0,0,sprite.width,sprite.height);
        c.globalCompositeOperation='destination-in';
        const gx=c.createLinearGradient(0,0,sprite.width,0);gx.addColorStop(0,'transparent');gx.addColorStop(.13,'#000');gx.addColorStop(.72,'#000');gx.addColorStop(1,'transparent');c.fillStyle=gx;c.fillRect(0,0,sprite.width,sprite.height);
        const gy=c.createLinearGradient(0,0,0,sprite.height);gy.addColorStop(0,'transparent');gy.addColorStop(.12,'#000');gy.addColorStop(.68,'#000');gy.addColorStop(1,'transparent');c.fillStyle=gy;c.fillRect(0,0,sprite.width,sprite.height);
      }
      return {sprite,x:x*iw,y:y*ih,w:w*iw,h:h*ih};
    });
  }
  function foliage(ctx,img,crop,w,h,time,reduced){
    if(disposed||reduced)return;prepare(img);
    patches.forEach((p,i)=>{
      const x=(p.x-crop.x)/crop.w*w,y=(p.y-crop.y)/crop.h*h,pw=p.w/crop.w*w,ph=p.h/crop.h*h;
      if(x+pw<0||x>w)return;const pose=canopyPose(i,time),anchorX=i===2?x+pw:x;
      ctx.save();ctx.translate(anchorX+pose.x,y+pose.y);ctx.rotate(pose.angle);ctx.drawImage(p.sprite,x-anchorX,0,pw,ph);ctx.restore();
    });
  }
  function shimmer(ctx,crop,w,h,time,reduced){
    if(disposed||reduced)return;
    const iw=source?.naturalWidth||1672,ih=source?.naturalHeight||941;
    ctx.save();ctx.lineCap='round';
    for(let i=0;i<72;i++){
      const sy=.735+noise(i+450)*.255,span=waterSpan(sy),sx=span.left+(span.right-span.left)*noise(i+540);
      const x=(sx*iw-crop.x)/crop.w*w,y=(sy*ih-crop.y)/crop.h*h;
      const wave=Math.sin(time*(.65+noise(i+630)*.5)+i*2.4),alpha=Math.pow((wave+1)/2,3)*(.12+(sy-.73)*.45);
      const length=(3+noise(i+720)*24)*(w/1280),shift=Math.sin(time*.52+i)*2;
      ctx.strokeStyle=`rgba(255,249,211,${alpha})`;ctx.lineWidth=.6+(sy-.73)*3;ctx.beginPath();ctx.moveTo(x+shift,y);ctx.quadraticCurveTo(x+length*.5+shift,y+wave*.7,x+length+shift,y);ctx.stroke();
    }ctx.restore();
  }
  function air(ctx,w,h,time,reduced){
    if(disposed)return;
    ctx.save();for(let i=0;i<6;i++){const p=fogPose(i,time,w,h,reduced);ctx.globalAlpha=p.alpha;ctx.drawImage(fog,p.x-p.width/2,p.y-p.height/2,p.width,p.height);}
    if(!reduced)for(let i=0;i<(w<700?10:LEAF_BUDGET);i++){
      const p=leafPose(i,time,w,h);ctx.save();ctx.globalAlpha=p.alpha;ctx.translate(p.x,p.y);ctx.rotate(p.angle);ctx.scale(p.scale*p.flutter,p.scale);
      ctx.fillStyle=leafColors[i%4];ctx.beginPath();ctx.moveTo(-1,0);ctx.bezierCurveTo(-.35,-.8,.6,-.65,1.2,0);ctx.bezierCurveTo(.5,.62,-.4,.65,-1,0);ctx.fill();
      ctx.strokeStyle='#563c2477';ctx.lineWidth=.12;ctx.beginPath();ctx.moveTo(-1.2,0);ctx.quadraticCurveTo(0,.07,1.1,0);ctx.stroke();ctx.restore();
    }ctx.restore();
  }
  return {foliage,shimmer,air,dispose(){disposed=true;patches.forEach(p=>{p.sprite.width=p.sprite.height=1;});patches=[];source=null;fog.width=fog.height=1;}};
}
