import {clamp,smooth} from './motion.mjs';
import {recordIndices} from './record-score.mjs';

const mix=(a,b,t)=>a+(b-a)*t;
const style=(el,key,value)=>{if(el.style[key]!==value)el.style[key]=value;};
export class RecordChoreography {
  constructor(){this.mask=0;this.items=Array.from({length:4},()=>({p:0,v:0,spin:0}));}
  step(dt,reduced=false){
    dt=clamp(dt,0,.05);
    this.items.forEach((item,i)=>{
      const target=this.mask>>i&1;
      if(reduced){item.p=target;item.v=0;item.spin=0;return;}
      // A small physical spring keeps velocity when a click reverses mid-flight.
      for(let n=0;n<4;n++){item.v+=((target-item.p)*100-item.v*10)*dt/4;item.p+=item.v*dt/4;}
      if(Math.abs(item.p-target)<.0005&&Math.abs(item.v)<.002){item.p=target;item.v=0;}
      if(target)item.spin+=24*dt*smooth((item.p-.82)/.18);
      else item.spin+=(Math.round(item.spin/360)*360-item.spin)*(1-Math.exp(-dt*8));
    });
    return this.items;
  }
}

export function deckLayout(pose,w,h,index){
  const edge=pose.d*.37,step=(w-edge*2)/3,bw=Math.min(step*.88,pose.d*.80),bh=bw*1122/1402;
  // Whole machines stay visible; the large idle records can still peek out.
  const x=clamp(pose.x-bw*.5,8,w-bw-8),y=h*.61-bh*.478;
  return {x,y,w:bw,h:bh,cx:x+bw*.423,cy:y+bh*.478,d:bw*.604,index};
}

export function recordPlacement(pose,deck,p,state,aim){
  const u=smooth(clamp(p,0,1));
  return {x:mix(pose.x,deck.cx,u),y:mix(pose.y,deck.cy,u)-Math.sin(u*Math.PI)*pose.d*.22,
    d:mix(pose.d,deck.d,u),z:mix(pose.angle,0,u),
    ry:mix(24+clamp(state.yaw,-1.8,1.8)*10+aim.x*3,0,u),
    rx:mix(-9+clamp(state.pitch,-.85,.85)*18+aim.y*2,24,u)};
}

// Piecewise cubic routing: bypass stays below every skipped, idle record.
// Sampled arc length keeps note spacing consistent through the bend.
export function recordLink(a,b,poses,h){
  const y=a.y+a.h*.82,from={x:a.x+a.w*.94,y},to={x:b.x+b.w*.06,y:b.y+b.h*.82};
  const skipped=b.index-a.index>1,points=[];
  const addCurve=(p0,p1,p2,p3)=>{for(let i=points.length?1:0;i<=24;i++){const t=i/24,u=1-t;points.push({x:u*u*u*p0.x+3*u*u*t*p1.x+3*u*t*t*p2.x+t*t*t*p3.x,y:u*u*u*p0.y+3*u*u*t*p1.y+3*u*t*t*p2.y+t*t*t*p3.y});}};
  if(!skipped)points.push(from,to);
  else{
    const bottom=Math.max(...poses.slice(a.index+1,b.index).map(p=>p.y+p.d*.53));
    const bypass=Math.min(h*.955,bottom+Math.min(28,h*.055));
    const first=poses[a.index+1],last=poses[b.index-1];
    const leftBend=Math.max(8,Math.min(a.w*.45,first.x-first.d*.53-from.x-5));
    const rightBend=Math.max(8,Math.min(b.w*.45,to.x-last.x-last.d*.53-5));
    const c={x:from.x+leftBend,y:bypass},d={x:to.x-rightBend,y:bypass};
    addCurve(from,{x:from.x+leftBend*.5,y:from.y},{x:from.x+leftBend*.4,y:bypass},c);
    points.push(d);addCurve(d,{x:to.x-rightBend*.4,y:bypass},{x:to.x-rightBend*.5,y:to.y},to);
  }
  let length=0;points.forEach((p,i)=>{if(i)length+=Math.hypot(p.x-points[i-1].x,p.y-points[i-1].y);p.distance=length;});
  return {from:a.index,to:b.index,points,length,skipped};
}
export function linkPoint(link,distance){
  const d=clamp(distance,0,link.length),ps=link.points;let i=1;while(i<ps.length-1&&ps[i].distance<d)i++;
  const a=ps[i-1],b=ps[i],t=(d-a.distance)/Math.max(.001,b.distance-a.distance);return {x:mix(a.x,b.x,t),y:mix(a.y,b.y,t)};
}

export function createRecordPlayers(field,discs,prints){
  const choreography=new RecordChoreography(),canvas=document.createElement('canvas');canvas.className='record-links';canvas.setAttribute('aria-hidden','true');field.prepend(canvas);
  const ctx=canvas.getContext('2d',{alpha:true}),decks=discs.map(()=>{
    const el=document.createElement('div');el.className='record-deck';el.setAttribute('aria-hidden','true');
    el.innerHTML='<img alt="" draggable="false"/><span class="record-arm"><i class="arm-counterweight"></i><i class="arm-shaft"></i><i class="arm-head"></i></span><span class="record-lamp"></span>';
    field.insertBefore(el,discs[0]);return el;
  });
  const arms=decks.map(deck=>{const el=document.createElement('div');el.className='record-arm-plane';el.setAttribute('aria-hidden','true');el.append(deck.querySelector('.record-arm'));field.append(el);return el;});
  const shafts=arms.map(a=>a.querySelector('.record-arm')),lamps=decks.map(d=>d.querySelector('.record-lamp'));
  let loaded=false,lastSize='',linkKey='',links=[],deckPoses=[],dead=false;
  return {
    get animating(){return Boolean(choreography.mask)||choreography.items.some(i=>Math.abs(i.p)>.0005||Math.abs(i.v)>.002||Math.abs(i.spin-Math.round(i.spin/360)*360)>.01);},
    set(mask){choreography.mask=mask;if(mask&&!loaded){decks.forEach(d=>d.querySelector('img').src='/intro-assets/textures/record-player-walnut.png');loaded=true;}},
    render(poses,w,h,dt,time,state,aim,reduced){
      if(dead)return;const states=choreography.step(dt,reduced);deckPoses=poses.map((p,i)=>deckLayout(p,w,h,i));
      states.forEach((item,i)=>{
        const deck=decks[i],d=deckPoses[i],p=clamp(item.p,0,1),v=recordPlacement(poses[i],d,p,state,reduced?{x:0,y:0}:aim);
        deck.hidden=p<.001;style(deck,'width',d.w+'px');style(deck,'height',d.h+'px');style(deck,'opacity',String(smooth(p/.48)));
        style(deck,'transform',`translate3d(${d.x}px,${d.y+(1-p)*16}px,0) perspective(1600px) rotateX(24deg) scale(${.95+.05*p})`);
        const arm=arms[i];arm.hidden=deck.hidden;for(const key of ['width','height','transform','opacity'])style(arm,key,deck.style[key]);
        style(shafts[i],'transform',`rotate(${mix(-6,28,smooth((p-.72)/.28))}deg)`);
        style(lamps[i],'opacity',String(smooth((p-.8)/.2)));
        const button=discs[i];style(button,'width',poses[i].d+'px');style(button,'height',poses[i].d+'px');
        style(button,'transform',`translate3d(${v.x-poses[i].d/2}px,${v.y-poses[i].d/2}px,0) perspective(1600px) rotateZ(${v.z}deg) rotateY(${v.ry}deg) rotateX(${v.rx}deg) scale(${v.d/poses[i].d})`);
        style(prints[i],'transform',`rotate(${item.spin}deg)`);button.dataset.deployed=p.toFixed(3);button.dataset.spindle=item.spin.toFixed(3);
      });
      const key=`${choreography.mask}:${w}:${h}:${poses.map(p=>p.x).join(',')}`;
      if(key!==linkKey){linkKey=key;const active=recordIndices(choreography.mask);links=active.slice(1).map((id,i)=>recordLink(deckPoses[active[i]],deckPoses[id],poses,h));}
      canvas.hidden=links.length===0;canvas.dataset.edges=links.map(l=>`${l.from+1}-${l.to+1}${l.skipped?':curve':':straight'}`).join(',');
      if(!ctx||!links.length){canvas.dataset.notes='0';return;}
      const ratio=Math.min(1.5,typeof devicePixelRatio==='number'?devicePixelRatio:1,Math.sqrt(1400000/(w*h))),size=`${w}:${h}:${ratio}`;
      if(size!==lastSize){lastSize=size;canvas.width=Math.round(w*ratio);canvas.height=Math.round(h*ratio);canvas.style.width=w+'px';canvas.style.height=h+'px';}
      ctx.setTransform(ratio,0,0,ratio,0,0);ctx.clearRect(0,0,w,h);
      const font=clamp(w/95,11,19),glyphs=['♪','♬','♩','♫'];let total=0;
      for(const link of links){
        const opacity=smooth(Math.min(states[link.from].p,states[link.to].p));ctx.globalAlpha=opacity;
        ctx.beginPath();link.points.forEach((p,i)=>i?ctx.lineTo(p.x,p.y):ctx.moveTo(p.x,p.y));
        for(const [width,color] of [[12,'#e8c76f2b'],[5,'#dcc58188'],[1.4,'#b18c3e']]){ctx.lineWidth=width;ctx.strokeStyle=color;ctx.stroke();}
        const count=Math.max(4,Math.min(64,Math.ceil(link.length/(font*1.45)/4)*4)),spacing=link.length/count;
        ctx.font=`${font}px Georgia,serif`;ctx.textAlign='center';ctx.textBaseline='middle';
        // Phase progresses strictly from the left endpoint to the right one.
        for(let n=0;n<count&&total<128;n++,total++){
          const distance=(n*spacing+(reduced?0:time*34))%link.length,p=linkPoint(link,distance),alpha=Math.min(1,distance/12,(link.length-distance)/12);
          ctx.globalAlpha=opacity*alpha;ctx.fillStyle='#f9f6e7';ctx.lineWidth=3;ctx.strokeStyle='#f5f1dacc';ctx.strokeText(glyphs[n%4],p.x,p.y);ctx.fillStyle='#675333';ctx.fillText(glyphs[n%4],p.x,p.y);
        }
      }ctx.globalAlpha=1;canvas.dataset.notes=String(total);
    },
    hit(x,y){const rect=field.getBoundingClientRect();x-=rect.left;y-=rect.top;return deckPoses.find(d=>(choreography.mask>>d.index&1)&&x>=d.x&&x<=d.x+d.w&&y>=d.y&&y<=d.y+d.h)?.index;},
    dispose(){dead=true;decks.forEach(d=>{d.querySelector('img').removeAttribute('src');d.remove();});arms.forEach(a=>a.remove());canvas.width=canvas.height=1;canvas.remove();}
  };
}
