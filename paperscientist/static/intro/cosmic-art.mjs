import {clamp,smooth} from './motion.mjs';

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

// Satin light curtains: continuous paths, broad translucent bodies, fine crests.
// No shadowBlur/filter or accumulated frames; reversing/resize cannot leave ghosts.
export function aurora(ctx,w,h,time,{portal=0,pointer={x:0,y:0},center=.51}={}){
  ctx.save();ctx.globalCompositeOperation='lighter';
  for(let band=0;band<5;band++){
    const color=band<2?'72,221,199':band<4?'78,145,235':'188,211,247';
    const base=h*(center+band*.034),amp=h*(.12+band*.009),phase=time*(.11+band*.008)+band*.72;
    const y=(u,layer)=>base+Math.sin(u*4.8+phase)*amp+Math.sin(u*9.1-phase*.7)*amp*.24
      +Math.cos(u*2.6+phase*.2)*h*.05+layer*h*.006+pointer.y*h*.022
      +(Math.pow(Math.abs(u-.5)*2,1.8)-.4)*portal*h*.33;
    const glow=ctx.createLinearGradient(0,base-amp-h*.22,0,base+amp);
    glow.addColorStop(0,`rgba(${color},0)`);glow.addColorStop(.25,`rgba(${color},.04)`);
    glow.addColorStop(.68,`rgba(${color},.32)`);glow.addColorStop(.88,`rgba(${color},.22)`);glow.addColorStop(1,`rgba(${color},0)`);
    ctx.beginPath();for(let k=0;k<=100;k++){const u=k/100;k?ctx.lineTo(u*w,y(u,0)):ctx.moveTo(0,y(0,0));}
    for(let k=100;k>=0;k--){const u=k/100;ctx.lineTo(u*w,y(u,0)-h*(.17+.035*Math.sin(u*5+phase)));}
    ctx.closePath();ctx.fillStyle=glow;ctx.fill();
    for(let layer=0;layer<9;layer++){
      ctx.beginPath();for(let k=0;k<=100;k++){const u=k/100;k?ctx.lineTo(u*w,y(u,layer)):ctx.moveTo(0,y(0,layer));}
      ctx.strokeStyle=`rgba(${color},${layer===0?.42:.025+(8-layer)*.005})`;ctx.lineWidth=layer===0?1.2:.65;ctx.stroke();
    }
  }
  ctx.restore();
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
export function globe(ctx,w,h,time,seeds,pointer){
  const fade=ctx.globalAlpha;
  const narrow=w<900,r=Math.min(w*(narrow?.42:.30),h*(narrow?.26:.37)),cx=w*(narrow?.5:.70)+pointer.x*12,cy=h*(narrow?.68:.52)+pointer.y*8;
  const aura=ctx.createRadialGradient(cx,cy,r*.2,cx,cy,r*1.4);aura.addColorStop(0,'#0b2438');aura.addColorStop(.68,'#071927');aura.addColorStop(1,'rgba(5,12,22,0)');ctx.fillStyle=aura;ctx.fillRect(cx-r*1.4,cy-r*1.4,r*2.8,r*2.8);
  ctx.strokeStyle='rgba(164,221,242,.28)';ctx.lineWidth=1;ctx.beginPath();ctx.arc(cx,cy,r,0,TAU);ctx.stroke();
  for(const p of seeds){const q=globePoint(p,time,.18+pointer.y*.12);const alpha=q.z>0?.24+q.z*.65:.07;
    ctx.globalAlpha=fade*alpha*(p.land?1:.24);ctx.fillStyle=p.land?'#b7e5eb':'#6795b6';const size=(p.land?1.8:1)*(.7+.6*Math.max(0,q.z));ctx.fillRect(cx+q.x*r-size/2,cy-q.y*r-size/2,size,size);}
  ctx.globalAlpha=fade;
  // Elevated arcs trace evidence travelling between distant points.
  for(let line=0;line<6;line++){
    const from=seeds[(line*317+83)%seeds.length],to=seeds[(line*193+1134)%seeds.length],phase=(time*.12+line*.163)%1;
    const at=u=>{const x=from.x*(1-u)+to.x*u,y=from.y*(1-u)+to.y*u,z=from.z*(1-u)+to.z*u;const n=Math.hypot(x,y,z),lift=1+Math.sin(u*Math.PI)*.35;return globePoint({x:x/n*lift,y:y/n*lift,z:z/n*lift},time,.18+pointer.y*.12);};
    ctx.beginPath();for(let k=0;k<=60;k++){const q=at(k/60);k?ctx.lineTo(cx+q.x*r,cy-q.y*r):ctx.moveTo(cx+q.x*r,cy-q.y*r);}
    ctx.strokeStyle='rgba(215,194,139,.4)';ctx.lineWidth=1;ctx.stroke();const dot=at(phase);
    ctx.fillStyle='#fff0c4';ctx.beginPath();ctx.arc(cx+dot.x*r,cy-dot.y*r,2.8,0,TAU);ctx.fill();
  }
}

export function orbital(ctx,w,h,time,pointer){
  const narrow=w<900,cx=w*(narrow?.5:.71)+pointer.x*10,cy=h*(narrow?.66:.53),unit=Math.min(w*(narrow?.46:.35),h*(narrow?.26:.41));
  ctx.save();ctx.translate(cx,cy);ctx.rotate(-.27+pointer.y*.05);
  // Tilted fabric depression echoes the user's gravity-well image.
  for(let j=-7;j<=7;j++){
    ctx.beginPath();for(let k=0;k<=100;k++){const x=(k/50-1)*unit*1.45,z=j/7,well=Math.exp(-((x/unit)**2+z*z)*3)*unit*.23;
      const y=z*unit*.64+well;k?ctx.lineTo(x,y):ctx.moveTo(x,y);}
    ctx.strokeStyle='rgba(130,173,198,.11)';ctx.lineWidth=.65;ctx.stroke();
  }
  for(let j=-10;j<=10;j++){
    ctx.beginPath();for(let k=0;k<=60;k++){const z=k/30-1,x=j/10*unit*1.45,well=Math.exp(-((x/unit)**2+z*z)*3)*unit*.23;const y=z*unit*.64+well;k?ctx.lineTo(x,y):ctx.moveTo(x,y);}
    ctx.stroke();
  }
  for(let i=0;i<5;i++){
    const r=unit*(.36+i*.20),angle=time*(.18-i*.022)+i*1.3;
    ctx.beginPath();ctx.ellipse(0,0,r,r*.58,0,0,TAU);ctx.strokeStyle=`rgba(188,210,224,${.28-i*.025})`;ctx.lineWidth=1;ctx.stroke();
    for(let tail=0;tail<12;tail++){ctx.beginPath();ctx.ellipse(0,0,r,r*.58,0,angle-.32+tail*.026,angle-.294+tail*.026);ctx.strokeStyle=`rgba(144,205,239,${.08+tail*.025})`;ctx.lineWidth=2;ctx.stroke();}
    const x=Math.cos(angle)*r,y=Math.sin(angle)*r*.58,rad=unit*(i===3?.035:.018+i*.002);
    const shade=ctx.createRadialGradient(x-rad*.3,y-rad*.4,0,x,y,rad);shade.addColorStop(0,i===3?'#ffedd0':'#def6ff');shade.addColorStop(.45,i===3?'#b78f68':'#80b3cb');shade.addColorStop(1,'#172a3b');
    ctx.fillStyle=shade;ctx.beginPath();ctx.arc(x,y,rad,0,TAU);ctx.fill();
    if(i===3){ctx.beginPath();ctx.ellipse(x,y,rad*1.9,rad*.65,-.4,0,TAU);ctx.strokeStyle='#cdb89a88';ctx.lineWidth=2;ctx.stroke();}
  }
  const sr=unit*.15;const corona=ctx.createRadialGradient(0,0,sr*.5,0,0,sr*3.7);corona.addColorStop(0,'rgba(255,219,153,.7)');corona.addColorStop(.42,'rgba(237,158,61,.14)');corona.addColorStop(1,'rgba(235,153,62,0)');ctx.fillStyle=corona;ctx.fillRect(-sr*4,-sr*4,sr*8,sr*8);
  const core=ctx.createRadialGradient(-sr*.3,-sr*.3,0,0,0,sr);core.addColorStop(0,'#fff7ce');core.addColorStop(.65,'#f4ce78');core.addColorStop(1,'#ba7738');ctx.fillStyle=core;ctx.beginPath();ctx.arc(0,0,sr,0,TAU);ctx.fill();
  ctx.save();ctx.beginPath();ctx.arc(0,0,sr,0,TAU);ctx.clip();ctx.strokeStyle='rgba(255,255,226,.18)';ctx.lineWidth=1;
  for(let i=0;i<12;i++){ctx.beginPath();for(let k=0;k<=40;k++){const x=(k/20-1)*sr,y=-sr+i*sr/6+Math.sin(x/sr*5+time*.32+i)*sr*.07;k?ctx.lineTo(x,y):ctx.moveTo(x,y);}ctx.stroke();}ctx.restore();ctx.restore();
}

export function createPrelude(canvas){
  const ctx=canvas.getContext('2d',{alpha:false}),stars=seededStars(),dots=globeSeeds(),aim={x:0,y:0},lean={x:0,y:0};let w=1,h=1,ratio=1,dead=false;
  function resize(){w=Math.max(1,innerWidth);h=Math.max(1,innerHeight);ratio=artRatio(w,h,devicePixelRatio||1);canvas.width=Math.round(w*ratio);canvas.height=Math.round(h*ratio);}
  function render(p,time,reduced=false){
    if(dead)return;const opacity=preludeOpacity(p);canvas.hidden=opacity<.001;canvas.style.opacity=String(opacity);if(dead||!ctx||opacity<.001)return;
    const t=reduced?0:time;lean.x+=(aim.x-lean.x)*.08;lean.y+=(aim.y-lean.y)*.08;
    ctx.setTransform(ratio,0,0,ratio,0,0);ctx.globalAlpha=1;ctx.fillStyle='#050d18';ctx.fillRect(0,0,w,h);starDust(ctx,w,h,t,stars,.7);
    const progress=clamp(p,0,2),a=Math.floor(progress),blend=smooth(progress-a);
    function layer(index,opacity){if(opacity<.001)return;ctx.save();ctx.globalAlpha=opacity;
      // Each scene is a complete poster. Fade through a dark field, not a
      // stack of expensive fullscreen blur filters.
      if(index===0){aurora(ctx,w,h,t,{pointer:lean,center:w<900?.56:.42});}
      if(index===1)globe(ctx,w,h,t,dots,lean);
      if(index===2)orbital(ctx,w,h,t,lean);ctx.restore();}
    // Nonlinear alpha leaves a brief quiet transition while copy changes.
    layer(a,1-blend);if(a<2)layer(a+1,blend);
    const scrim=ctx.createLinearGradient(0,0,w*.64,0);scrim.addColorStop(0,'rgba(5,13,24,.4)');scrim.addColorStop(1,'rgba(5,13,24,0)');ctx.fillStyle=scrim;ctx.fillRect(0,0,w,h);
    canvas.dataset.art=['aurora','globe','orbits'][Math.round(progress)];canvas.dataset.points=String(dots.length);
  }
  resize();return {render,resize,pointer(x,y){aim.x=clamp(x,-1,1);aim.y=clamp(y,-1,1);},dispose(){dead=true;canvas.width=canvas.height=1;canvas.hidden=true;}};
}
