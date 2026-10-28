import {clamp,smooth} from './motion.mjs';
import {createGardenAtmosphere,createGardenCanopy} from './garden-atmosphere.mjs?v=3';

export const referenceOpacity=p=>p<1?1-smooth((p-.12)/.65):smooth((p-1.18)/.66)*(1-smooth((p-2.28)/.5));
export const records=[
  {name:'观察',title:'Begin with\na question',line:'从好奇心开始',note:'留意尚未被解释的现象。',image:'disc-pastoral.webp',style:'landscape'},
  {name:'文献',title:'The shape\nof an idea',line:'沿着线索阅读',note:'阅读文献，找到问题之间的联系。',image:'nebula-4k.webp',style:'night'},
  {name:'方向',title:'Every idea\nbegins here',line:'找到值得追问的方向',note:'比较不同解释，留下值得验证的假设。',image:'disc-watertown-4k.webp',style:'garden'},
  {name:'探索',title:'Beyond',line:'向未知展开',note:'把问题带入更广阔的知识世界。',image:'disc-milky-way-4k.webp',style:'milky-way'},
];
export function discLayout(w,h,index,yaw=0,time=0,reduced=false){
  const narrow=w<700,positions=narrow?[0,.38,.94,1.68]:[0,.24,.55,.98];
  const centers=narrow?[.68,.60,.50,.18]:[.73,.65,.49,.18];
  const sizes=narrow?[.44,.60,.78,1.02]:[.33,.40,.48,.63];
  const d=Math.min(w*sizes[index],h*(narrow?[.40,.46,.54,.72][index]:[.44,.56,.70,.98][index]));
  return {x:w*positions[index]+clamp(yaw,-1.8,1.8)*w*.13,y:h*centers[index]+(reduced?0:Math.sin(time*.18+index*.9)*h*.006),d,angle:[-24,-26,25,-26][index]};
}
export function discTransforms(pose,state,aim,time,reduced=false){
  const y=(pose.central?-24:24)+clamp(state.yaw,-1.8,1.8)*10+(reduced?0:aim.x*3);
  const x=(pose.central?12:-9)+clamp(state.pitch,-.85,.85)*18+(reduced?0:aim.y*2);
  return {plane:`translate3d(${pose.x-pose.d/2}px,${pose.y-pose.d/2}px,0) perspective(1600px) rotateZ(${pose.angle}deg) rotateY(${y}deg) rotateX(${x}deg)`,
    // Spin the print inside the tilted plane, never around the screen's Z axis.
    spindle:`rotate(${reduced?0:(time*3)%360}deg)`};
}
export function imageCover(iw,ih,w,h,focus=.5){const scale=Math.max(w/iw,h/ih);return {x:(iw-w/scale)*clamp(focus,0,1),y:(ih-h/scale)/2,w:w/scale,h:h/scale};}
export class WaterRipples{
  constructor(){this.items=[];}
  add(x,y){this.items.push({x:clamp(x,0,1),y:clamp(y,.72,.97),age:0});this.items=this.items.slice(-4);}
  tick(dt,reduced){if(reduced){this.items=[];return;}this.items.forEach(p=>p.age+=clamp(dt,0,.1));this.items=this.items.filter(p=>p.age<2.5);}
}

export function createReferenceArt(host,wake){
  host.innerHTML=`<section class="disc-gallery" aria-label="研究灵感唱片集">
    <div class="disc-record"><h1>从一个问题<br>走向多种可能。</h1><dl><div><dt>研究起点</dt><dd>你的好奇心</dd></div><div><dt>正在浏览</dt><dd data-record-name>方向</dd></div><div><dt>下一步</dt><dd data-record-note>比较不同解释，留下值得验证的假设。</dd></div></dl></div>
    <div class="disc-field"></div><div class="disc-editorial"><p><small>阅读与关联</small>“沿着线索，<br>发现新的联系。”</p><p><small>提问与判断</small>“让值得追问的问题，<br>成为研究的起点。”</p></div>
  </section><section class="garden-scene" aria-label="山水研究庭院" hidden><div class="garden-plate"><img src="/intro-assets/textures/garden-reference-4k.webp" alt="红色古塔与庭院、拱桥、秋色树林和山间溪水的绘画"/><div class="garden-canopy" aria-hidden="true"></div><canvas aria-hidden="true"></canvas></div></section>`;
  const gallery=host.querySelector('.disc-gallery'),field=host.querySelector('.disc-field'),garden=host.querySelector('.garden-scene'),plate=host.querySelector('.garden-plate'),img=plate.querySelector('img'),canvas=plate.querySelector('canvas'),ctx=canvas.getContext('2d',{alpha:true});
  const atmosphere=createGardenAtmosphere(),canopy=createGardenCanopy(plate.querySelector('.garden-canopy'),img),name=host.querySelector('[data-record-name]'),note=host.querySelector('[data-record-note]'),ripples=new WaterRipples(),abort=new AbortController();
  let dead=false,stage=0,selected=2,w=1,h=1,lastTime=null,lastRatio='',frames=0,waterFeedback=false;
  const discs=records.map((record,index)=>{
    const button=document.createElement('button');button.className='research-disc';button.dataset.print=record.style;button.setAttribute('aria-label','选择'+record.name+'唱片');button.setAttribute('aria-pressed',String(index===selected));
    button.innerHTML=`<span class="disc-print" style="background-image:url('/intro-assets/textures/${record.image}')"><span class="disc-label">${record.title.replace('\n','<br>')}</span><span class="disc-edition">PaperScientist / ${record.name}</span></span><span class="disc-hub"></span>`;
    // Pointer selection is handled by the shared drag/tap surface; keyboard clicks
    // retain a normal button action without turning a drag into an accidental click.
    button.addEventListener('click',e=>{if(e.detail===0)choose(index);},{signal:abort.signal});field.append(button);return button;
  });
  const prints=discs.map(d=>d.querySelector('.disc-print'));
  img.addEventListener('load',wake,{signal:abort.signal});img.addEventListener('error',()=>{garden.dataset.unavailable='true';wake();},{signal:abort.signal});
  function choose(i){selected=i;name.textContent=records[i].name;note.textContent=records[i].note;discs.forEach((d,j)=>d.setAttribute('aria-pressed',String(j===i)));wake();}
  function water(x=.62,y=.84){ripples.add(x,y);waterFeedback=true;wake();}
  function hide(){host.hidden=true;lastTime=null;ripples.items=[];}
  return {get available(){return !dead;},hide,
    render({p,time,state,aim,w:width,h:height,reduced}){
      if(dead)return [];const alpha=referenceOpacity(p);if(alpha<.001){hide();return [];}
      w=width;h=height;stage=p<1?0:2;host.hidden=false;host.style.opacity=String(alpha);host.dataset.art=stage===0?'printed-disc-gallery':'painted-garden';gallery.hidden=stage!==0;garden.hidden=stage!==2;
      const dt=lastTime===null?0:Math.min(.1,Math.max(0,time-lastTime));lastTime=time;const t=reduced?0:time;
      if(stage===0){
        const fw=w*.90,fh=h*.78;
        discs.forEach((disc,i)=>{const v=discLayout(fw,fh,i,state.yaw,t,reduced),transform=discTransforms({...v,central:i===2},state,aim,t,reduced);if(disc.style.width!==v.d+'px')disc.style.width=disc.style.height=v.d+'px';disc.style.transform=transform.plane;prints[i].style.transform=transform.spindle;});
      }else{
        const ratio=Math.min(devicePixelRatio||1,1.5,Math.sqrt(1400000/(w*h))),key=w+':'+h+':'+ratio;
        if(key!==lastRatio){lastRatio=key;canvas.width=Math.round(w*ratio);canvas.height=Math.round(h*ratio);}
        const dx=reduced?0:aim.x*5+clamp(state.yaw,-1,1)*6,dy=reduced?0:aim.y*3;
        plate.style.transform=`translate3d(${dx}px,${dy}px,0) scale(1.025)`;
        ripples.tick(dt,reduced);
        let airCrop;
        if(ctx){ctx.setTransform(ratio,0,0,ratio,0,0);ctx.clearRect(0,0,w,h);
          if(img.complete&&img.naturalWidth){
            const crop=imageCover(img.naturalWidth,img.naturalHeight,w,h,w<=700?.62:.5);
            canopy.render(crop,w,h,t,reduced);
            airCrop={x:crop.x/img.naturalWidth,y:crop.y/img.naturalHeight,w:crop.w/img.naturalWidth,h:crop.h/img.naturalHeight};
            // Preserve native 4K detail: only light glints overlay the water,
            // never repaint the photograph through the lower-resolution FX canvas.
            ctx.globalAlpha=1;atmosphere.shimmer(ctx,crop,w,h,t,reduced,img.naturalWidth,img.naturalHeight);
          }
          ctx.globalAlpha=1;for(const r of ripples.items)for(let i=0;i<3;i++){const radius=(r.age*50+i*16);ctx.beginPath();ctx.ellipse(r.x*w,r.y*h,radius,radius*.22,0,0,Math.PI*2);ctx.strokeStyle=`rgba(253,250,226,${(1-r.age/2.5)*.38})`;ctx.lineWidth=1;ctx.stroke();}
          atmosphere.air(ctx,w,h,t,reduced,airCrop);
        }
      }
      frames++;host.dataset.frames=String(frames);host.dataset.selected=String(selected);host.dataset.ripples=String(ripples.items.length);host.dataset.motion=t.toFixed(3);host.dataset.yaw=state.yaw.toFixed(3);return [];
    },
    tap(x,y){if(stage===2){if(y/h>=.70)water(x/w,y/h);return;}const available=discs.map((el,i)=>({i,rect:el.getBoundingClientRect()}));const inside=available.filter(({rect:r})=>x>=r.left&&x<=r.right&&y>=r.top&&y<=r.bottom);if(inside.length)choose(inside.at(-1).i);},
    activate(){if(stage===0)choose((selected+1)%records.length);else water();},
    reset(){choose(2);ripples.items=[];waterFeedback=false;},
    get info(){return stage===0?{help:'拖动唱片集 · 点击切换研究线索',action:'浏览下一张',selection:records[selected].line}:{help:'移动欣赏园林 · 点击水面泛起涟漪',action:'轻点水面',selection:waterFeedback?'涟漪渐息，让想法慢慢沉淀。':''};},
    dispose(){dead=true;abort.abort();ripples.items=[];atmosphere.dispose();canopy.dispose();img.removeAttribute('src');canvas.width=canvas.height=1;host.replaceChildren();host.hidden=true;}
  };
}
