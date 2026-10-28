import {clamp,smooth} from './motion.mjs';
import {imageCover,WaterRipples} from './reference-art.mjs?v=5';
import {createGardenAtmosphere,createGardenCanopy,canopyPose} from './garden-atmosphere.mjs?v=4';

export const closingOpacity=p=>smooth((p-9.25)/.72);
export const closingWaterSpan=y=>({left:.17-(y-.8)*.17,right:.86+(y-.8)*.1});
export function closingFogPose(i,time,w,h,reduced=false){
  const t=reduced?0:time,phase=i*1.43;
  if(i<4)return {x:w*(.13+i*.23+Math.sin(t*.18+phase)*.10),y:h*(.39+(i%2)*.09+Math.sin(t*.22+phase)*.012),width:w*.47,height:h*.14,alpha:.29+(1+Math.sin(t*.27+phase))*.035};
  return {x:w*(.77+Math.sin(t*.23+phase)*.09),y:h*(.17+(i-4)*.09+Math.sin(t*.19+phase)*.012),width:w*.25,height:h*.10,alpha:.23+(1+Math.sin(t*.25+phase))*.035};
}
export function cloudPose(i,time){return {x:Math.sin(time*.12+i*1.8)*18,y:Math.sin(time*.09+i)*4,angle:Math.sin(time*.08+i)*.002};}

// The final landscape uses the same artwork/effects approach as chapter three,
// but its trees, clouds, fog and water are mapped to this image's composition.
// It owns no RAF or interval: only the journey's existing clock can render it.
export function createClosingLandscape(host,wake){
  host.innerHTML='<div class="closing-plate"><img alt="红色塔楼、樱花、石桥与湖面群山" decoding="async"/><div class="closing-clouds garden-canopy" aria-hidden="true"></div><div class="closing-branches garden-canopy" aria-hidden="true"></div><canvas aria-hidden="true"></canvas></div>';
  const plate=host.querySelector('.closing-plate'),img=plate.querySelector('img'),canvas=plate.querySelector('canvas'),ctx=canvas.getContext('2d',{alpha:true});
  const clouds=createGardenCanopy(plate.querySelector('.closing-clouds'),img,{regions:[[.12,0,.43,.29],[.47,0,.35,.16]],pose:cloudPose});
  const branches=createGardenCanopy(plate.querySelector('.closing-branches'),img,{regions:[[0,.06,.16,.67],[.83,.39,.17,.39]],pose:(i,t)=>canopyPose(i,t*.85)});
  const atmosphere=createGardenAtmosphere({fogPose:closingFogPose,fogCount:7,waterStart:.81,waterSpan:closingWaterSpan,leafColors:['#e7a1a6','#f5c4c7','#d68790','#eab4aa']});
  const ripples=new WaterRipples(),abort=new AbortController(),aim={x:0,y:0};
  let dead=false,requested=false,last=null,elapsed=0,ratioKey='',width=1,height=1;
  img.addEventListener('load',wake,{signal:abort.signal});img.addEventListener('error',()=>{host.dataset.unavailable='true';wake();},{signal:abort.signal});
  function hide(){host.hidden=true;last=null;ripples.items=[];}
  return {
    render(p,now,w,h,reduced=false){
      if(dead)return 0;
      if(p>8.8&&!requested){requested=true;img.src='/intro-assets/textures/disc-pagoda-4k.webp';}
      const opacity=closingOpacity(p);
      if(opacity<.001||!img.complete||!img.naturalWidth){hide();return 0;}
      host.hidden=false;host.style.opacity=String(opacity);width=w;height=h;
      const dt=last===null?0:clamp(now-last,0,.08);last=now;if(!reduced)elapsed+=dt;
      const time=reduced?0:elapsed,ratio=Math.min(devicePixelRatio||1,1.5,Math.sqrt(1400000/Math.max(1,w*h))),key=[w,h,ratio].join(':');
      if(key!==ratioKey){ratioKey=key;canvas.width=Math.round(w*ratio);canvas.height=Math.round(h*ratio);}
      plate.style.transform=`translate3d(${reduced?0:aim.x*5}px,${reduced?0:aim.y*3}px,0) scale(1.025)`;
      const crop=imageCover(img.naturalWidth,img.naturalHeight,w,h,w<700?.73:.5);
      clouds.render(crop,w,h,time,reduced);branches.render(crop,w,h,time,reduced);ripples.tick(dt,reduced);
      if(ctx){ctx.setTransform(ratio,0,0,ratio,0,0);ctx.clearRect(0,0,w,h);
        atmosphere.shimmer(ctx,crop,w,h,time,reduced,img.naturalWidth,img.naturalHeight);
        for(const r of ripples.items)for(let i=0;i<3;i++){const radius=r.age*50+i*17;ctx.beginPath();ctx.ellipse(r.x*w,r.y*h,radius,radius*.2,0,0,Math.PI*2);ctx.strokeStyle=`rgba(244,247,232,${(1-r.age/2.5)*.42})`;ctx.lineWidth=1;ctx.stroke();}
        atmosphere.air(ctx,w,h,time,reduced,{x:crop.x/img.naturalWidth,y:crop.y/img.naturalHeight,w:crop.w/img.naturalWidth,h:crop.h/img.naturalHeight});
      }
      host.dataset.motion=time.toFixed(3);host.dataset.ripples=String(ripples.items.length);return opacity;
    },
    pointer(x,y){aim.x=clamp(x,-1,1);aim.y=clamp(y,-1,1);},
    tap(x,y){if(dead||host.hidden)return;const crop=imageCover(img.naturalWidth,img.naturalHeight,width,height,width<700?.73:.5),sy=(crop.y+y*crop.h)/img.naturalHeight,sx=(crop.x+x*crop.w)/img.naturalWidth,span=closingWaterSpan(sy);if(sy>=.81&&sx>span.left&&sx<span.right){ripples.add(x,y);wake();}},
    hide,
    dispose(){dead=true;abort.abort();hide();clouds.dispose();branches.dispose();atmosphere.dispose();img.removeAttribute('src');canvas.width=canvas.height=1;host.replaceChildren();}
  };
}
