import {clamp, smooth} from './motion.mjs';
import {workColumn} from './journey-map.mjs';

const pieces = [
  ['从问题到研究地图','atlas.svg','文献与线索'],
  ['让假设接受检验','experiment.svg','实验设计'],
  ['看见系统如何协作','architecture.svg','系统框架'],
  ['每个结论都有来处','evidence.svg','证据与复现'],
  ['把发现写成论文','paper.svg','学术写作'],
  ['让细节成为表达','figures.svg','图表与叙事']
];
// Original condensed letter outlines, rather than a remote font. A fixed set of
// 21 planes describes the concave wall; all motion uses the journey's clock.
const glyphs = `<svg viewBox="0 0 72 400" preserveAspectRatio="none" aria-hidden="true"><g fill="currentColor">
<path d="M2 0H16L21 58 28 0H43L51 58 56 0H70L60 94H44L36 40 28 94H12Z"/>
<path fill-rule="evenodd" d="M36 102Q62 102 62 124V174Q62 196 36 196Q10 196 10 174V124Q10 102 36 102ZM36 119Q28 119 28 128V170Q28 179 36 179Q44 179 44 170V128Q44 119 36 119Z"/>
<path fill-rule="evenodd" d="M10 204H37Q63 204 63 228V241Q63 257 51 263L66 298H46L33 267H28V298H10ZM28 221V250H36Q45 250 45 241V230Q45 221 36 221Z"/>
<path d="M10 306H29V343L48 306H68L44 350 70 400H48L29 361V400H10Z"/></g></svg>`;

export function createWork(root, wake) {
  const wall=root.querySelector('.work-wall'),portal=root.querySelector('.work-portal'),grid=root.querySelector('.work-grid');
  const trail=root.querySelector('.work-trail'),nav=root.querySelector('.work-picker'),caption=root.querySelector('.work-caption');
  const columns=Array.from({length:21},()=>{const el=document.createElement('div');el.className='work-column';el.innerHTML=glyphs;wall.append(el);return el;});
  const slots=Array.from({length:5},()=>{const el=document.createElement('figure');el.className='work-preview';el.hidden=true;const img=document.createElement('img');img.draggable=false;const label=document.createElement('figcaption');el.append(img,label);trail.append(el);return {el,img,label,born:0,x:0,y:0,rotation:0,index:0};});
  let width=1,height=1,active=false,reduced=false,pointerX=0,pointerY=0,aimX=0,aimY=0,lastX=-1000,lastY=-1000,lastSpawn=0,cursor=0,piece=0,beat=-1,visible=false,held=false;
  const buttons=pieces.map((p,i)=>{const b=document.createElement('button');b.type='button';b.textContent=String(i+1).padStart(2,'0');b.title=p[0];b.setAttribute('aria-label',p[0]);b.onclick=()=>show(i,width*.5,height*.5,true);b.onfocus=()=>show(i,width*.5,height*.5,true);nav.append(b);return b;});
  function resize(){
    const previousWidth=width,previousHeight=height;width=Math.max(1,innerWidth);height=Math.max(1,innerHeight);
    wall.style.perspective=`${width*.85}px`;const columnWidth=width/(width<700?7.5:18.5);
    for(const el of columns){el.style.width=`${columnWidth}px`;el.style.marginLeft=`${-columnWidth/2}px`;el.style.height=`${height*.76}px`;}
    for(const s of slots){if(s.el.hidden)continue;s.x=s.x/previousWidth*width;s.y=s.y/previousHeight*height;s.el.style.left=`${s.x}px`;s.el.style.top=`${s.y}px`;}
    buildGrid();
  }
  function buildGrid(){
    // A bowed perspective grid recedes toward the capsule, matching the
    // reference's corridor. It is regenerated only on resize.
    const ns='http://www.w3.org/2000/svg',paths=[];grid.setAttribute('viewBox',`0 0 ${width} ${height}`);
    for(let i=-10;i<=10;i++){const x=width*.5+i*width/18,center=width*.5+i*width/25;paths.push(`M${x} 0 C${center} ${height*.25},${center} ${height*.75},${x} ${height}`);}
    for(let i=-6;i<=6;i++){const y=height*.5+i*height/10,bend=(y-height*.5)*.34;paths.push(`M0 ${y+bend} Q${width*.5} ${y-bend},${width} ${y+bend}`);}
    grid.replaceChildren(...paths.map(d=>{const p=document.createElementNS(ns,'path');p.setAttribute('d',d);return p;}));
  }
  function show(index,x,y,persist=false){
    if(!active)return;
    const now=performance.now()/1000,s=slots[cursor++%slots.length];piece=(index+pieces.length)%pieces.length;held=persist;
    if(persist||reduced)for(const other of slots)other.el.hidden=true;
    s.index=piece;s.born=now;s.x=clamp(x,width*.2,width*.8);s.y=clamp(y,height*.26,height*.73);s.rotation=reduced?0:((cursor%3)-1)*2.5;
    s.img.src=`/intro-assets/work/${pieces[piece][1]}`;s.img.alt=pieces[piece][0]+' · 研究能力示意';s.label.textContent=pieces[piece][2];s.el.hidden=false;s.el.style.zIndex=String(cursor%100+1);
    s.el.style.left=`${s.x}px`;s.el.style.top=`${s.y}px`;
    caption.textContent=pieces[piece][0];buttons.forEach((b,i)=>b.setAttribute('aria-pressed',String(i===piece)));
    lastSpawn=now;lastX=x;lastY=y;wake();
  }
  function pointer(x,y){aimX=x-.5;aimY=y-.5;if(!active||reduced)return;const px=x*width,py=y*height,now=performance.now()/1000;
    if(now-lastSpawn>.19&&Math.hypot(px-lastX,py-lastY)>Math.min(width*.1,125))show(piece+1,px,py);
  }
  function render(state,time,dt,reduce){
    reduced=reduce;root.hidden=state.work<.001;root.style.opacity=String(state.work);
    active=state.gallery&&state.work>.99;nav.inert=!active;root.dataset.open=String(active);
    if(root.hidden){if(visible)for(const s of slots)s.el.hidden=true;visible=false;beat=-1;return;}
    visible=true;const a=state.aperture;
    const insetX=43*(1-a),insetY=15*(1-a);portal.style.clipPath=`inset(${insetY}% ${insetX}% round ${Math.min(width*.07,height*.2)*(1-a)}px)`;
    portal.style.transform=`translate3d(0,${-smooth((state.p-9)/.8)*height*.2}px,0)`;
    grid.style.transform=`scale(${1+.35*a}) translate3d(0,${-smooth((state.p-9)/.8)*10}%,0)`;
    pointerX+=(aimX-pointerX)*(1-Math.exp(-dt*5));pointerY+=(aimY-pointerY)*(1-Math.exp(-dt*5));
    columns.forEach((el,i)=>{const c=workColumn(i,columns.length,width,height,a,pointerX,time,reduced);
      el.style.transform=`translate3d(${c.x}px,${c.y+(reduced?0:pointerY*height*.025)*a}px,${c.z}px) rotateY(${c.angle}deg) scale3d(${.88+.12*a},${.62+.38*a},1)`;
      el.style.opacity=String(width<700&&Math.abs(i-10)>4?0:i===10?1:smooth(a*2));
    });
    if(active&&beat!==state.preview){beat=state.preview;show(beat,width*(.45+(beat%3)*.08),height*.49,reduced);}
    for(const s of slots){if(s.el.hidden)continue;const age=Math.max(0,time-s.born),entry=reduced?1:smooth(age/.28),exit=held||reduced?0:smooth((age-1.05)/.55);
      if(exit===1){s.el.hidden=true;continue;}
      s.el.style.opacity=String(Math.min(1,state.aperture*3));s.el.style.clipPath=`inset(${exit*100}% 0 0 0)`;
      s.el.style.transform=`translate3d(-50%,calc(-50% + ${(1-entry)*22-exit*12}px),0) rotate(${s.rotation}deg) scale(${.94+.06*entry})`;
      s.img.style.opacity=String(entry);s.el.style.filter='none';
    }
  }
  resize();return {render,resize,pointer,dispose(){columns.forEach(x=>x.remove());slots.forEach(s=>s.el.remove());buttons.forEach(b=>b.remove());root.hidden=true;}};
}
