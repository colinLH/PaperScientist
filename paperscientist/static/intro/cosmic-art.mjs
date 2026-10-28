import {clamp,smooth} from './motion.mjs';
import {PreludeInteraction,interactivePoint,experiments,experimentNotes} from './prelude-interaction.mjs?v=3';

import {referenceOpacity} from './reference-art.mjs?v=2';
import {CITIES} from './earth-data.mjs';
import {geoPoint,cityFocus,earthOpacity,EARTH_YAW,EARTH_SPEED} from './earth-geometry.mjs';

// Procedural artwork inspired by the user's local 099, 138 and 195 demos.
// A shared clock, deterministic samples and bounded canvases replace their RAFs.
export const TAU=Math.PI*2;
export function seededStars(count=240){
  let n=138;const rand=()=>((n=(Math.imul(n,1664525)+1013904223)>>>0)/4294967296);
  return Array.from({length:count},()=>({x:rand(),y:rand(),r:.35+rand()*1.1,phase:rand()*TAU}));
}
export function artRatio(w,h,dpr=1){return Math.min(dpr,1.5,Math.sqrt(2200000/Math.max(1,w*h)));}
export function preludeOpacity(position){return 1-smooth((position-2.28)/.5);}
export function starDust(ctx,w,h,time,stars,alpha=1){
  ctx.fillStyle='#cedee9';
  for(const s of stars){ctx.globalAlpha=alpha*(.24+.46*(.5+.5*Math.sin(time*.5+s.phase)));ctx.fillRect(s.x*w,s.y*h,s.r,s.r);}
  ctx.globalAlpha=1;
}

// Approximate invented land silhouettes: decorative connectivity globe, not GIS.
const continents=[[-105,40,43,28],[-70,-13,20,46],[18,4,24,38],[65,42,70,24],[133,-25,24,15],[-42,72,17,16]];
export function globeSeeds(count=2400){
  return Array.from({length:count},(_,i)=>{
    const y=1-2*(i+.5)/count,a=i*Math.PI*(3-Math.sqrt(5)),r=Math.sqrt(1-y*y);
    const lon=((a*180/Math.PI+180)%360)-180,lat=Math.asin(y)*180/Math.PI;
    const land=continents.some(([cx,cy,rx,ry])=>((lon-cx)/rx)**2+((lat-cy)/ry)**2<.74+.19*Math.sin(lon*.22+lat*.17));
    return {x:Math.cos(a)*r,y,z:Math.sin(a)*r,land};
  });
}
export function globePoint(p,time,tilt=.18){
  const a=time*.075+.4,c=Math.cos(a),s=Math.sin(a),x=p.x*c+p.z*s,z=-p.x*s+p.z*c;
  return {x,y:p.y*Math.cos(tilt)-z*Math.sin(tilt),z:p.y*Math.sin(tilt)+z*Math.cos(tilt)};
}

const mix=(a,b,t)=>a+(b-a)*t;
export function narrativePoint(seed,index,count,progress,time){
  const p=clamp(progress,0,2),u=(index%200)/199,band=Math.floor(index/200);
  const wave={x:(u-.5)*3.5,y:Math.sin(u*7.5+time*.16+band*.08)*.28+(band-5.5)*.04,z:Math.cos(u*6+band*.12)*.14};
  const sphere=globePoint(seed,time);
  const ring=index%6,r=.24+ring*.21+Math.sin(index*2.4)*.012,a=index/count*TAU+time*(.13-ring*.012);
  const ox=Math.cos(a)*r,oy=Math.sin(a)*r*.47;
  const orbit={x:ox*Math.cos(-.24)-oy*Math.sin(-.24),y:ox*Math.sin(-.24)+oy*Math.cos(-.24),z:Math.sin(a)*r*.2};
  const from=p<=1?wave:sphere,to=p<=1?sphere:orbit,t=smooth(p<=1?p:p-1);
  return {x:mix(from.x,to.x,t),y:mix(from.y,to.y,t),z:mix(from.z,to.z,t)};
}
export function narrativePath(u,band,p,time){
  const a=u*TAU+time*.08,lat=(band-2.5)*.26,r=Math.sqrt(1-lat*lat);
  const wave={x:(u-.5)*3.5,y:Math.sin(u*7.5+time*.16+band*.17)*.28+(band-2.5)*.08,z:Math.cos(u*6+band*.12)*.14};
  const sphere=globePoint({x:Math.cos(a)*r,y:lat,z:Math.sin(a)*r},time);
  const radius=.24+band*.21,ox=Math.cos(a)*radius,oy=Math.sin(a)*radius*.47;
  const orbit={x:ox*Math.cos(-.24)-oy*Math.sin(-.24),y:ox*Math.sin(-.24)+oy*Math.cos(-.24),z:Math.sin(a)*radius*.2};
  const from=p<=1?wave:sphere,to=p<=1?sphere:orbit,t=smooth(p<=1?p:p-1);
  return {x:mix(from.x,to.x,t),y:mix(from.y,to.y,t),z:mix(from.z||0,to.z||0,t)};
}
export function createPrelude(canvas){
  const ctx=canvas.getContext('2d',{alpha:true}),stars=seededStars(),dots=globeSeeds(),interaction=new PreludeInteraction();
  const aim={x:0,y:0};let w=1,h=1,ratio=1,dead=false,lastTime=null,phase=0,cx=0,cy=0,unit=1,hits=[],lastStage=0,earth=null,studio=null;
  const colors=['#a8edf2','#b5c9ff','#e5c694','#80d6c5','#c3b2ee','#efc9ae'];
  function resize(){w=Math.max(1,innerWidth);h=Math.max(1,innerHeight);ratio=artRatio(w,h,devicePixelRatio||1);canvas.width=Math.round(w*ratio);canvas.height=Math.round(h*ratio);}
  function dot(x,y,r,color,alpha=1){ctx.globalAlpha=alpha;ctx.fillStyle=color;ctx.beginPath();ctx.arc(x,y,Math.max(.1,r),0,TAU);ctx.fill();ctx.globalAlpha=1;}
  function render(p,time,reduced=false){
    if(dead)return;const opacity=preludeOpacity(p);canvas.hidden=opacity<.001;canvas.style.opacity=String(opacity);
    if(!ctx||opacity<.001){lastTime=null;interaction.held=false;earth?.hide();studio?.hide();return;}
    const dt=lastTime===null?1/30:Math.max(0,Math.min(.05,time-lastTime));lastTime=time;interaction.update(dt,reduced);
    const t=reduced?0:interaction.flow;phase=clamp(p,0,2);const warm=smooth(phase-1),sphere=1-Math.abs(phase-1),narrow=w<900;
    unit=Math.min(w*(narrow?.42:.34),h*(narrow?.24:.37));cx=w*(narrow?.5:.70);cy=h*(narrow?.62:.51);
    if(Math.round(phase)!==lastStage){interaction.selected=-1;lastStage=Math.round(phase);}
    const earthBlend=earth?.available?earthOpacity(phase):0,studioBlend=studio?.available?referenceOpacity(p):0;
    const pointer={x:((aim.x+1)*w/2-cx)/unit,y:(cy-(aim.y+1)*h/2)/unit};
    const project=q=>{const a=interactivePoint(q,phase,interaction,pointer);return {...a,sx:cx+a.x*unit,sy:cy-a.y*unit};};
    ctx.setTransform(ratio,0,0,ratio,0,0);ctx.globalAlpha=1;ctx.clearRect(0,0,w,h);ctx.fillStyle='#040c18';ctx.fillRect(0,0,w,h);if(studioBlend<.999)starDust(ctx,w,h,t,stars,.7);
    const halo=ctx.createRadialGradient(cx,cy,unit*.12,cx,cy,unit*1.5);
    halo.addColorStop(0,`rgba(${24+warm*74},${100+warm*12},${150-warm*40},.24)`);halo.addColorStop(1,'rgba(4,12,24,0)');ctx.fillStyle=halo;ctx.fillRect(0,0,w,h);
    if(earthBlend<.999&&studioBlend<.999){
    // The sphere is translucent and volumetric, without the old stacked sheets.
    if(sphere>.01){
      const body=ctx.createRadialGradient(cx-unit*.27,cy-unit*.25,unit*.12,cx,cy,unit*1.12);
      body.addColorStop(0,`rgba(22,69,102,${sphere*.5})`);body.addColorStop(.78,`rgba(7,29,55,${sphere*.6})`);body.addColorStop(.94,`rgba(71,181,213,${sphere*.38})`);body.addColorStop(1,'rgba(4,12,24,0)');ctx.fillStyle=body;ctx.beginPath();ctx.arc(cx,cy,unit*1.12,0,TAU);ctx.fill();
    }
    // One population carries both the scroll morph and the pointer force.
    const accent=`rgb(${212+warm*43},${247-warm*22},${243-warm*69})`;
    for(let i=0;i<dots.length;i++){
      const q=project(narrativePoint(dots[i],i,dots.length,phase,t));
      const density=mix(.84,dots[i].land?1:.18,sphere),depth=.18+.72*(q.z+1)/2;
      ctx.globalAlpha=clamp(density*depth+.3*q.light,0,1);ctx.fillStyle=i%9===0?accent:i%3===0?'#d4f7f3':'#66b9e7';
      const size=(i%13===0?2.2:1.25)*(.8+.3*(q.z+1))*(1+q.light*.6);ctx.fillRect(q.sx,q.sy,size,size);
    }ctx.globalAlpha=1;
    for(let band=0;band<6;band++){
      if(band<5&&phase<.95){
        const sheet=ctx.createLinearGradient(cx-unit,cy-unit,cx+unit,cy+unit);sheet.addColorStop(0,'rgba(63,174,207,.015)');sheet.addColorStop(.5,`rgba(93,202,226,${.24*(1-smooth(phase))})`);sheet.addColorStop(1,'rgba(120,155,209,.01)');
        ctx.beginPath();for(let k=0;k<=80;k++){const q=project(narrativePath(k/80,band,phase,t));k?ctx.lineTo(q.sx,q.sy):ctx.moveTo(q.sx,q.sy);}
        for(let k=80;k>=0;k--){const q=project(narrativePath(k/80,band+1,phase,t));ctx.lineTo(q.sx,q.sy);}ctx.closePath();ctx.fillStyle=sheet;ctx.fill();
      }
      ctx.beginPath();for(let k=0;k<=100;k++){const q=project(narrativePath(k/100,band,phase,t));k?ctx.lineTo(q.sx,q.sy):ctx.moveTo(q.sx,q.sy);}
      ctx.strokeStyle=`rgba(140,219,239,${.32-sphere*.23+(interaction.selected===band?warm*.35:0)})`;ctx.lineWidth=interaction.selected===band?1.3:.8;ctx.stroke();
    }
    hits=[];
    if(sphere>.01){
      const anchors=CITIES.map(c=>{const p=geoPoint(c.lon,c.lat);const a=EARTH_YAW+t*EARTH_SPEED,cx=Math.cos(a),sx=Math.sin(a);return {x:p.x*cx+p.z*sx,y:p.y,z:-p.x*sx+p.z*cx};});
      const selected=interaction.selected<0?0:interaction.selected%CITIES.length;
      for(let j=1;j<=3;j++){
        const a=anchors[selected],b=anchors[(selected+j*7)%CITIES.length];ctx.beginPath();
        for(let k=0;k<=48;k++){const u=k/48,x=mix(a.x,b.x,u),y=mix(a.y,b.y,u),z=mix(a.z,b.z,u),r=(1+Math.sin(u*Math.PI)*.22)/Math.max(.1,Math.hypot(x,y,z));const q=project({x:x*r,y:y*r,z:z*r});k?ctx.lineTo(q.sx,q.sy):ctx.moveTo(q.sx,q.sy);}
        ctx.strokeStyle=`rgba(124,228,244,${sphere*(interaction.selected<0?.22:.65)})`;ctx.lineWidth=1.2;ctx.stroke();
      }
      anchors.forEach((a,i)=>{const q=project(a);if(q.z<-.1)return;const active=interaction.selected===i,r=active?6:3.5;dot(q.sx,q.sy,r+9,'#72d7ee',sphere*.1);dot(q.sx,q.sy,r,'#d7fbff',sphere);if(active){ctx.beginPath();ctx.arc(q.sx,q.sy,13,0,TAU);ctx.strokeStyle='#baf5ff';ctx.lineWidth=1;ctx.stroke();}if(phase>.55&&phase<1.45)hits.push({x:q.sx,y:q.sy,index:i});});
    }
    if(warm>.01){
      for(let i=0;i<6;i++){
        const q=project(narrativePath((t*(.025-i*.002)+i*.153)%1,i,2,t)),active=interaction.selected===i,r=unit*(.022+i*.003)*(active?1.3:1);
        const body=ctx.createRadialGradient(q.sx-r*.35,q.sy-r*.35,r*.08,q.sx,q.sy,r);body.addColorStop(0,'#f4f9f4');body.addColorStop(.35,colors[i]);body.addColorStop(1,'#14253e');ctx.globalAlpha=warm;ctx.fillStyle=body;ctx.beginPath();ctx.arc(q.sx,q.sy,r,0,TAU);ctx.fill();ctx.globalAlpha=1;
        if(i===4||active){ctx.beginPath();ctx.ellipse(q.sx,q.sy,r*1.8,r*.5,-.35,0,TAU);ctx.strokeStyle=active?'#edf6ff':'#cbbde5';ctx.globalAlpha=warm*.7;ctx.stroke();ctx.globalAlpha=1;}
        if(phase>1.45)hits.push({x:q.sx,y:q.sy,index:i});
      }
    }
    // Brighter, textured nucleus; pulse rings are bounded and decay naturally.
    const r=unit*(.018+.084*warm),glow=ctx.createRadialGradient(cx,cy,0,cx,cy,r*5);
    glow.addColorStop(0,`rgba(255,235,175,${.25+.6*warm})`);glow.addColorStop(.22,`rgba(250,177,69,${warm*.5})`);glow.addColorStop(1,'rgba(20,70,90,0)');ctx.fillStyle=glow;ctx.fillRect(cx-r*5,cy-r*5,r*10,r*10);
    const core=ctx.createRadialGradient(cx-r*.3,cy-r*.3,0,cx,cy,r);core.addColorStop(0,'#fffbea');core.addColorStop(.55,'#ffe8a2');core.addColorStop(1,'#d59a48');ctx.fillStyle=core;ctx.globalAlpha=.12+.88*warm+(reduced&&interaction.activated&&phase<.5?.4:0);ctx.beginPath();ctx.arc(cx,cy,r,0,TAU);ctx.fill();ctx.globalAlpha=1;
    if(warm>.5){ctx.strokeStyle='#ffe9a3';ctx.globalAlpha=warm*.28;for(let i=0;i<12;i++){const a=i/12*TAU+t*.08;ctx.beginPath();ctx.moveTo(cx+Math.cos(a)*r,cy+Math.sin(a)*r);ctx.lineTo(cx+Math.cos(a)*r*(1.1+.1*Math.sin(t+i)),cy+Math.sin(a)*r*(1.1+.1*Math.sin(t+i)));ctx.stroke();}ctx.globalAlpha=1;}
    if(!reduced)for(const pulse of interaction.pulses){ctx.beginPath();ctx.arc(cx+pulse.x*unit,cy-pulse.y*unit,Math.max(2,pulse.age*unit*1.5),0,TAU);ctx.strokeStyle=`rgba(167,238,255,${.65*(1-pulse.age/1.8)})`;ctx.lineWidth=1.1;ctx.stroke();}
    }
    if(earthBlend>0){
      ctx.globalAlpha=earthBlend;ctx.fillStyle='#040c18';ctx.fillRect(0,0,w,h);ctx.globalAlpha=1;starDust(ctx,w,h,t,stars,earthBlend*.7);
      const cityHits=earth.render({time:t,yaw:interaction.yaw,pitch:interaction.pitch,selected:Math.round(phase)===1?interaction.selected:-1,opacity:earthBlend,w,h,cx,cy:narrow?mix(cy,h*.59,earthBlend):cy,unit:mix(unit,Math.min(unit,w*(narrow?.35:.245),h*.34),earthBlend),reduced});if(Math.round(phase)===1)hits=cityHits;
    }else earth?.hide();
    const scrim=ctx.createLinearGradient(0,0,w*.48,0);scrim.addColorStop(0,'rgba(4,12,24,.65)');scrim.addColorStop(1,'rgba(4,12,24,0)');ctx.fillStyle=scrim;ctx.fillRect(0,0,w,h);
    if(studioBlend>0){const studioHits=studio.render({p,time:t,state:interaction,aim,w,h,cx,cy,unit,reduced});if(phase>1.5)hits=studioHits;}else studio?.hide();
    canvas.dataset.art=['question-stream','global-cities','experiment-orbits'][Math.round(phase)];canvas.dataset.points=String(dots.length);canvas.dataset.morph=phase.toFixed(4);canvas.dataset.yaw=interaction.yaw.toFixed(3);canvas.dataset.selected=String(interaction.selected);canvas.dataset.actions=String(interaction.actions);canvas.dataset.pulses=String(interaction.pulses.length);
  }
  function select(index){interaction.selected=index;interaction.actions++;}
  function activate(){if(studio?.activate&&Math.round(phase)!==1){studio.activate();interaction.actions++;return;}if(phase<.5)interaction.pulse(0,0);else {const list=[...new Set(hits.map(q=>q.index))];select(list[(list.indexOf(interaction.selected)+1)%Math.max(1,list.length)]??0);}}
  resize();return {render,resize,attachGlobe(globe){earth=globe;},attachReference(value){studio=value;},selectCity(index){if(!CITIES[index])return;select(index);const aim=cityFocus(CITIES[index],interaction.reduced?0:interaction.flow,interaction.yaw);interaction.targetYaw=aim.yaw;interaction.targetPitch=aim.pitch;},pointer(x,y){aim.x=clamp(x,-1,1);aim.y=clamp(y,-1,1);},over(value){interaction.over=value;},hold(value){interaction.held=value;},drag(dx,dy){interaction.drag(dx,dy);},activate,
    tap(x,y){if(studio?.tap&&Math.round(phase)!==1){studio.tap(x,y);interaction.actions++;return;}if(phase<.5)interaction.pulse((x-cx)/unit,(cy-y)/unit);else {const nearest=[...hits].sort((a,b)=>Math.hypot(a.x-x,a.y-y)-Math.hypot(b.x-x,b.y-y))[0];if(nearest&&(Math.round(phase)!==1||Math.hypot(nearest.x-x,nearest.y-y)<Math.max(26,unit*.12)))select(nearest.index);}},
    reset(){interaction.reset();studio?.reset?.();},speed(){interaction.speed=interaction.speed===1?2.5:1;},
    get info(){const stage=Math.round(phase),index=interaction.selected;if(studio?.info&&stage!==1)return {stage,selected:-1,speed:interaction.speed,...studio.info};return {stage,selected:index,speed:interaction.speed,help:['拖动观察光带 · 点击让线索流动','拖动旋转地球 · 点击城市查看位置','拖动观察透镜 · 点击节点拆解研究'][stage],action:['点亮线索','探索下一城市','探索下一层'][stage],selection:stage===0?(interaction.activated?'线索已点亮 · 从问题开始探索':''):index<0?(stage===1?'41 座城市 · 连线为探索示意':''):stage===1?CITIES[index%CITIES.length].name+' · '+CITIES[index%CITIES.length].en+' · '+Math.abs(CITIES[index%CITIES.length].lat).toFixed(1)+'°'+(CITIES[index%CITIES.length].lat<0?'S':'N')+' / '+Math.abs(CITIES[index%CITIES.length].lon).toFixed(1)+'°'+(CITIES[index%CITIES.length].lon<0?'W':'E'):stage===2?experiments[index%6]+' · '+experimentNotes[index%6]:''};},
    dispose(){dead=true;earth?.dispose();studio?.dispose();interaction.pulses=[];canvas.width=canvas.height=1;canvas.hidden=true;}};
}
