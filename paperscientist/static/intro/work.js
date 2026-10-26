import {smooth} from './motion.mjs';
import {railLayout,railCard,progressForCard,playingCards,wallTile,workPixelRatio} from './work-layout.mjs';
import {papers,createPreviewPlayback} from './paper-previews.mjs';

const outlines=[
 'M2 0H16L21 58 28 0H43L51 58 56 0H70L60 94H44L36 40 28 94H12Z',
 'M36 102Q62 102 62 124V174Q62 196 36 196Q10 196 10 174V124Q10 102 36 102ZM36 119Q28 119 28 128V170Q28 179 36 179Q44 179 44 170V128Q44 119 36 119Z',
 'M10 204H37Q63 204 63 228V241Q63 257 51 263L66 298H46L33 267H28V298H10ZM28 221V250H36Q45 250 45 241V230Q45 221 36 221Z',
 'M10 306H29V343L48 306H68L44 350 70 400H48L29 361V400H10Z'
];
const style=(el,key,value)=>{if(el.style[key]!==value)el.style[key]=value;};
const data=(el,key,value)=>{if(el.dataset[key]!==value)el.dataset[key]=value;};

export function createWork(root,wake,navigate=()=>{}){
  const wall=root.querySelector('.work-wall'),grid=root.querySelector('.work-grid'),trail=root.querySelector('.work-trail');
  const nav=root.querySelector('.work-picker'),caption=root.querySelector('.work-caption'),playButton=root.querySelector('.work-playback');
  const canvas=document.createElement('canvas');canvas.className='work-canvas';canvas.setAttribute('aria-hidden','true');wall.append(canvas);
  const ctx=canvas.getContext('2d',{alpha:true}),sprite=document.createElement('canvas');sprite.width=192;sprite.height=1067;
  const ink=sprite.getContext('2d');if(ink){ink.scale(sprite.width/72,sprite.height/400);ink.fillStyle='#ed003d';for(const d of outlines)ink.fill(new Path2D(d),'evenodd');}
  let width=1,height=1,ratio=1,layout=null,lastKey='',lastState=null,reduced=false,visible=false,paused=false,enabled=true,explicitPlayback=false,selected=-1;
  const cards=papers.map((paper,index)=>{
    const element=document.createElement('a');element.className='work-preview';element.href=paper.url;element.target='_blank';element.rel='noopener noreferrer';element.setAttribute('aria-label',`打开 ${paper.name} 论文项目页`);element.dataset.index=String(index);
    const bar=document.createElement('div');bar.className='paper-browser';const dots=document.createElement('span');dots.textContent='● ● ●';const address=document.createElement('span');address.textContent=new URL(paper.url).host;bar.append(dots,address);
    const heading=document.createElement('div');heading.className='paper-heading';const title=document.createElement('strong');title.textContent=paper.name;const subtitle=document.createElement('span');subtitle.textContent=paper.title;heading.append(title,subtitle);
    const demo=document.createElement('div');demo.className='paper-demo';const poster=document.createElement('img');poster.alt=paper.name+' 官方项目页预览';poster.decoding='async';poster.loading='lazy';poster.onerror=()=>{poster.hidden=true;element.dataset.poster='unavailable';};
    const video=document.createElement('video');video.setAttribute('aria-hidden','true');const unavailable=document.createElement('span');unavailable.className='paper-unavailable';unavailable.textContent='预览暂不可用，点击打开原站';demo.append(poster,video,unavailable);
    const footer=document.createElement('div');footer.className='paper-footer';const venue=document.createElement('span');venue.textContent=paper.venue;const link=document.createElement('span');link.textContent='项目页 ↗';footer.append(venue,link);
    element.append(bar,heading,demo,footer);trail.append(element);
    return {index,element,video,poster,source:paper.video,posterSource:paper.poster,posterLoaded:false};
  });
  const playback=createPreviewPlayback(cards);
  const buttons=papers.map((paper,i)=>{const b=document.createElement('button');b.type='button';b.textContent=String(i+1).padStart(2,'0');b.title=paper.name;b.setAttribute('aria-label',`定位 ${paper.name}`);b.onclick=e=>navigate(6+progressForCard(i,layout)*2,e.detail===0);nav.append(b);return b;});
  if(playButton)playButton.onclick=()=>{enabled=!enabled;explicitPlayback=true;playback.retry();updatePlayback();};

  function buildGrid(){
    const ns='http://www.w3.org/2000/svg',paths=[];grid.setAttribute('viewBox',`0 0 ${width} ${height}`);
    for(let i=-10;i<=10;i++){const x=width*.5+i*width/18,center=width*.5+i*width/25;paths.push(`M${x} 0 C${center} ${height*.25},${center} ${height*.75},${x} ${height}`);}
    for(let i=-6;i<=6;i++){const y=height*.5+i*height/10,bend=(y-height*.5)*.34;paths.push(`M0 ${y+bend} Q${width*.5} ${y-bend},${width} ${y+bend}`);}
    grid.replaceChildren(...paths.map(d=>{const p=document.createElementNS(ns,'path');p.setAttribute('d',d);return p;}));
  }
  function resize(){
    width=Math.max(1,innerWidth);height=Math.max(1,innerHeight);ratio=workPixelRatio(width,height,devicePixelRatio||1);layout=railLayout(width,height);
    canvas.width=Math.round(width*ratio);canvas.height=Math.round(height*ratio);
    for(const card of cards){card.element.style.width=`${layout.cardWidth}px`;card.element.style.height=`${layout.cardHeight}px`;}
    buildGrid();lastKey='';
  }
  function draw(state){
    if(!ctx)return;const a=state.aperture,exit=smooth((state.p-9)/.8),insetX=width*.43*(1-a),insetY=height*.15*(1-a);
    ctx.setTransform(ratio,0,0,ratio,0,0);ctx.clearRect(0,0,width,height);ctx.save();ctx.translate(0,-exit*height*.2);
    ctx.beginPath();ctx.roundRect(insetX,insetY,width-insetX*2,height-insetY*2,Math.min(width*.07,height*.2)*(1-a));ctx.fillStyle='#080406';ctx.fill();ctx.clip();
    if(a<1){const h=height*.48,w=width/(width<700?7.5:18.5)*.88;ctx.globalAlpha=1-a;ctx.drawImage(sprite,(width-w)/2,(height-h)/2,w,h);}
    if(a>0){ctx.globalAlpha=a;for(let i=0;i<25;i++){const tile=wallTile(i,25,width,height,a,state.workProgress);if(tile&&tile.x+tile.width>=0&&tile.x<=width)ctx.drawImage(sprite,tile.x,tile.y,tile.width,tile.height);}}
    ctx.restore();
  }
  function updatePlayback(rects=null){
    if(!lastState)return;
    const allow=enabled&&(!reduced||explicitPlayback)&&lastState.gallery&&!paused&&!document.hidden;
    rects??=cards.map(c=>railCard(c.index,lastState.workProgress,layout));
    playback.sync(allow?playingCards(rects,width,playback.active):[]);
    if(playButton){playButton.setAttribute('aria-pressed',String(enabled&&(!reduced||explicitPlayback)));playButton.textContent=enabled&&(!reduced||explicitPlayback)?'暂停预览':'播放预览';}
    data(root,'playing',String(playback.active.length));
  }
  function render(state,time,dt,reduce){
    lastState=state;reduced=reduce;
    if(state.work<.001){if(visible){root.hidden=true;playback.sync([]);data(root,'playing','0');}visible=false;lastKey='';return;}
    if(!visible){root.hidden=false;visible=true;lastKey='';}
    const key=`${state.p.toFixed(6)}:${reduce}`;if(key===lastKey)return;lastKey=key;
    style(root,'opacity',String(state.work));data(root,'open',String(state.gallery));nav.inert=!state.gallery;
    // No time-driven movement: pausing the wheel preserves every card and
    // letter position. Reversing it retraces precisely the same coordinates.
    draw(state);style(grid,'transform',`scale(${1+.35*state.aperture}) translate3d(0,${-smooth((state.p-9)/.8)*10}%,0)`);
    style(grid,'opacity',String(.38*(1-state.aperture)));
    style(trail,'opacity',String(smooth((state.aperture-.76)/.24)));trail.inert=!state.gallery;
    const rects=cards.map(card=>{
      const r=railCard(card.index,state.workProgress,layout);style(card.element,'transform',`translate3d(${r.x.toFixed(3)}px,${r.y.toFixed(3)}px,0)`);
      card.element.hidden=!r.visible;card.element.tabIndex=r.visible&&state.gallery?0:-1;
      if(r.visible&&state.gallery&&!card.posterLoaded){card.poster.src=card.posterSource;card.posterLoaded=true;}
      return r;
    });
    const focused=playingCards(rects,width)[0];if(focused!==selected&&focused!==undefined){selected=focused;caption.textContent='滚动浏览论文项目 · 点击预览打开原站';buttons.forEach((b,i)=>b.setAttribute('aria-pressed',String(i===selected)));}
    updatePlayback(rects);
  }
  resize();
  return {render,resize,pointer(){},pause(value){paused=value;updatePlayback();},dispose(){playback.dispose();canvas.width=canvas.height=sprite.width=sprite.height=1;canvas.remove();cards.forEach(c=>c.element.remove());buttons.forEach(b=>b.remove());if(playButton)playButton.onclick=null;root.hidden=true;}};
}
