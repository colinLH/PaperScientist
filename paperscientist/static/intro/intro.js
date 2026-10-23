import {Journey,clamp} from './motion.mjs';
import {Soundscape} from './audio.js?v=2';

const chapters=[
  {name:'雾中的问题',label:'向未知出发',title:'每一个发现，\n始于一个好问题。',description:'穿过已知的边界，让好奇心带路。'},
  {name:'沿着证据前行',label:'阅读，连接，追问',title:'从一篇论文，\n走向一片可能。',description:'在交错的线索中，找到值得深入的方向。'},
  {name:'抵达观测站',label:'让想法接受检验',title:'把灵感，\n变成可以验证的假设。',description:'设计方法，构建实验，让证据回答问题。'},
  {name:'未知的星图',label:'在探索中保持方向',title:'让每一步探索，\n都有迹可循。',description:'你的判断、实验与发现，连成一张研究星图。'},
  {name:'越过山脊',label:'从结果到表达',title:'看清细节，\n也看见全貌。',description:'把数据、图表与文字，整理成有依据的叙述。'},
  {name:'新的地平线',label:'PaperScientist',title:'接下来，\n是你的发现。',description:'带上一个问题，与科研伙伴一起出发。'}
];
const root=document.querySelector('#journey'),host=document.querySelector('#landscape'),copy=document.querySelector('#copy'),nav=document.querySelector('#chapters');
const previous=document.querySelector('#previous'),next=document.querySelector('#next'),start=document.querySelector('#start'),credits=document.querySelector('#credits');
const reduced=matchMedia('(prefers-reduced-motion: reduce)'),journey=new Journey(5),audio=new Soundscape(document.querySelector('#sound'),document.querySelector('#sound-status'));
let scene=null,frame=0,timer=0,last=0,shown=0,dead=false,leaving=false,drawn=-1,resizeTimer=0;
const buttons=chapters.map((c,i)=>{const b=document.createElement('button');b.setAttribute('aria-label',`${i+1} · ${c.name}`);b.title=c.name;b.addEventListener('click',()=>go(i));nav.append(b);return b;});
function textAt(index){if(index===shown&&drawn!==-1)return;shown=index;const c=chapters[index];document.querySelector('#chapter').textContent=c.label;document.querySelector('#title').replaceChildren(...c.title.split('\n').flatMap((line,i)=>i?[document.createElement('br'),document.createTextNode(line)]:[document.createTextNode(line)]));document.querySelector('#description').textContent=c.description;document.querySelector('#scene-name').textContent=c.name;document.querySelector('#number').textContent=String(index+1).padStart(2,'0');start.hidden=index!==5;copy.classList.remove('reveal');void copy.offsetWidth;copy.classList.add('reveal');}
function controls(){root.dataset.scene=journey.target;previous.disabled=journey.target===0;next.disabled=journey.target===5;document.querySelector('#hint').textContent=journey.target===5?'准备好，开始研究':'滚动，向前探索';buttons.forEach((b,i)=>b.setAttribute('aria-current',String(i===journey.target)));}
function go(index,instant=false){if(leaving)return;journey.go(index,instant||reduced.matches);controls();wake();}
function paint(){
  const p=clamp(journey.value,0,5),near=Math.round(p),distance=Math.abs(p-near);
  textAt(near);copy.style.opacity=String(1-Math.min(1,distance*2.3));copy.style.transform=reduced.matches?'none':`translate3d(0,${(p-near)*-35}px,0)`;copy.style.filter=reduced.matches||distance<.002?'none':`blur(${(distance*16).toFixed(2)}px)`;
  root.dataset.position=p.toFixed(3);root.dataset.moving=String(journey.moving);
  if(scene)scene.render(p,performance.now()/1000);else host.style.background=`radial-gradient(ellipse at ${60+p*3}% ${40-p*3}%,${['#789698','#80979b','#41576d','#162d48','#a19e9b','#e0c391'][near]},#142b3d 75%)`;
  audio.update(p);drawn=p;
}
function tick(now){frame=0;if(dead||document.hidden||credits.open)return;const dt=last?Math.min((now-last)/1000,.08):1/30;last=now;journey.tick(dt);paint();if(journey.moving||ambient())schedule();else{last=0;root.dataset.renderState='idle';}}
function ambient(){return !!scene&&!reduced.matches&&!leaving;}
function schedule(){if(timer||frame||dead||document.hidden)return;root.dataset.renderState=journey.moving?'moving':'ambient';timer=setTimeout(()=>{timer=0;frame=requestAnimationFrame(tick);},1000/30);}
function wake(){if(!dead&&!document.hidden){last=0;schedule();}}
function cancel(){clearTimeout(timer);cancelAnimationFrame(frame);timer=frame=0;last=0;}
root.addEventListener('wheel',e=>{if(credits.open||leaving||e.ctrlKey)return;e.preventDefault();const factor=e.deltaMode===1?20:e.deltaMode===2?innerHeight:1;if(journey.wheel(e.deltaY*factor,performance.now())){audio.arm();if(reduced.matches)journey.go(journey.target,true);controls();wake();}},{passive:false});
previous.onclick=()=>go(journey.target-1);next.onclick=()=>go(journey.target+1);
root.addEventListener('pointermove',e=>{const x=e.clientX/innerWidth,y=e.clientY/innerHeight;root.style.setProperty('--mx',`${(x*100).toFixed(1)}%`);root.style.setProperty('--my',`${(y*100).toFixed(1)}%`);if(!reduced.matches)scene?.pointer(x*2-1,y*2-1);},{passive:true});
document.addEventListener('keydown',e=>{if(credits.open||e.target.closest('input,textarea,select')||e.ctrlKey||e.metaKey||e.altKey)return;const moves={ArrowDown:1,PageDown:1,ArrowUp:-1,PageUp:-1};if(e.key in moves){e.preventDefault();if(!e.repeat)go(journey.target+moves[e.key],true);}else if(e.key==='Home'||e.key==='End'){e.preventDefault();go(e.key==='Home'?0:5,true);}});
let touchY=null;root.addEventListener('touchstart',e=>{if(!credits.open)touchY=e.touches[0].clientY;},{passive:true});root.addEventListener('touchend',e=>{if(touchY===null)return;const delta=touchY-e.changedTouches[0].clientY;touchY=null;if(Math.abs(delta)>45)go(journey.target+Math.sign(delta));},{passive:true});
// Try autoplay immediately; retry when the browser receives an activation gesture.
// Muting before activation stays muted even if a pending play attempt resolves later.
root.addEventListener('pointerdown',e=>{if(!audio.armed&&!e.target.closest('#sound,a,#credits-open'))audio.arm();},{passive:true});
root.addEventListener('touchend',()=>audio.arm(),{passive:true});
document.addEventListener('keydown',e=>{if(!credits.open&&!e.repeat&&!e.target.closest('#sound,a,#credits-open'))audio.arm();});
document.querySelector('#credits-open').onclick=()=>{cancel();credits.showModal();audio.visibility(true);};credits.addEventListener('close',()=>{audio.visibility(document.hidden);wake();});
document.addEventListener('visibilitychange',()=>{audio.visibility(document.hidden);if(document.hidden){cancel();root.dataset.renderState='hidden';}else wake();});
reduced.addEventListener('change',()=>go(journey.target,true));
window.addEventListener('resize',()=>{clearTimeout(resizeTimer);resizeTimer=setTimeout(()=>{scene?.resize();wake();},120);});
function fallback(){scene?.dispose();scene=null;document.querySelector('#fallback').hidden=false;wake();}
host.addEventListener('scene-lost',fallback);
async function enter(e){if(e.button!==0||e.metaKey||e.ctrlKey||e.shiftKey||e.altKey)return;e.preventDefault();if(leaving)return;leaving=true;audio.fadeOut();root.animate([{opacity:1},{opacity:0}],{duration:reduced.matches?180:800,easing:'ease-out',fill:'forwards'});setTimeout(()=>{dispose();location.assign(e.currentTarget?.href||'/?workspace=1');},reduced.matches?200:1000);}
document.querySelectorAll('a[href="/?workspace=1"]').forEach(a=>a.addEventListener('click',enter));
function dispose(){if(dead)return;dead=true;cancel();clearTimeout(resizeTimer);scene?.dispose();scene=null;audio.dispose();root.dataset.renderState='disposed';}
window.addEventListener('pagehide',dispose);window.addEventListener('pageshow',e=>{if(e.persisted)location.reload();});
controls();paint();audio.visibility(document.hidden);audio.arm();
try{const {createScene}=await import('./scene.js?v=3');if(!dead){scene=createScene(host);paint();wake();}}catch(error){console.warn('Intro: using lightweight landscape',error.message);fallback();}
