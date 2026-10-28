import {Journey} from './motion.mjs';
import {Soundscape} from './audio.js?v=3';
import {createPrelude,preludeOpacity} from './cosmic-art.mjs?v=16';
import {CITIES} from './earth-data.mjs';
import {bindPreludeInput} from './prelude-interaction.mjs?v=3';
import {LAST_STOP,chapterStops,journeyFrame} from './journey-map.mjs';
import {createWarp} from './warp.js';
import {createWork} from './work.js?v=2';
import {workSpring} from './work-layout.mjs?v=2';
import {createClosingLandscape} from './closing-landscape.mjs?v=4';
import {RECORD_SCORE,recordIndices} from './record-score.mjs';

const chapters=[
  {name:'研究灵感集',label:'从一个问题出发',title:'从一个问题，\n走向多种可能。',description:'观察、阅读、判断，让每一个线索都有继续探索的可能。'},
  {name:'全球城市',label:'跨越城市，连接灵感',title:'让世界相连，\n看见新的方向。',description:'从北京到纽约，从伦敦到悉尼，让探索与全球的灵感相遇。'},
  {name:'研究庭院',label:'让灵感慢慢沉淀',title:'把想法，\n沉淀成研究。',description:'走过知识的广阔天地，再回到一个值得专注的问题。让阅读、思考与验证，在这里慢慢生长。'},
  {name:'星际穿梭',label:'穿过已知的边界',title:'向更远的\n问题出发。',description:'让好奇心，带你穿过这片星海。'},
  {name:'未知的星图',label:'在探索中保持方向',title:'让每一步探索，\n都有迹可循。',description:'你的判断、实验与发现，连成一张研究星图。'},
  {name:'研究作品',label:'从探索到表达',title:'让发现，\n成为作品。',description:'文献、方法、实验与表达，在这里相遇。'},
  {name:'新的地平线',label:'PaperScientist',title:'接下来，\n是你的发现。',description:'带上一个问题，与科研伙伴一起出发。'}
];
const root=document.querySelector('#journey'),host=document.querySelector('#landscape'),copy=document.querySelector('#copy'),nav=document.querySelector('#chapters'),veil=document.querySelector('#valley-mist');
const previous=document.querySelector('#previous'),next=document.querySelector('#next'),start=document.querySelector('#start'),credits=document.querySelector('#credits');
const recordCredits=document.querySelector('#record-credits');
for(const track of RECORD_SCORE.filter(Boolean)){const li=document.createElement('li'),link=document.createElement('a');li.append(recordIndices(track.mask).map(i=>i+1).join(' + ')+'：');link.href=track.page;link.textContent=track.title;link.target='_blank';link.rel='noopener';li.append(link);recordCredits.append(li);}
// Full-motion diagnostics are explicit and never change the visitor's preference.
const reduced=new URLSearchParams(location.search).get('profile')==='motion'?{matches:false,addEventListener(){}}:matchMedia('(prefers-reduced-motion: reduce)'),journey=new Journey(LAST_STOP),audio=new Soundscape(document.querySelector('#sound'),document.querySelector('#sound-status'));
let scene=null,hands=null,frame=0,last=0,shown=0,dead=false,leaving=false,drawn=-1,resizeTimer=0,nextPaint=0,lastLandscapePaint=0;
let profiler=null;
if(new URLSearchParams(location.search).has('profile'))import('./performance-probe.mjs').then(({createPerformanceProbe})=>{if(!dead)profiler=createPerformanceProbe();});
const prelude=createPrelude(document.querySelector('#prelude-canvas'));
const closing=createClosingLandscape(document.querySelector('#closing-landscape'),wake);
const interactionSurface=document.querySelector('#prelude-interaction'),interactionTools=document.querySelector('#prelude-tools');
const cityPicker=document.querySelector('#earth-city');
CITIES.forEach((c,i)=>{const option=document.createElement('option');option.value=i;option.textContent=c.name+' · '+c.en;cityPicker.append(option);});
cityPicker.onchange=()=>{if(cityPicker.value!==''){prelude.selectCity(Number(cityPicker.value));wake();}};
const preludeInput=bindPreludeInput(interactionSurface,prelude,wake);
const referenceInput=bindPreludeInput(document.querySelector('#reference-art'),prelude,wake);
const interactionHelp=document.querySelector('#prelude-help'),interactionAction=document.querySelector('#prelude-action'),interactionSelection=document.querySelector('#prelude-selection'),interactionSpeed=document.querySelector('#prelude-speed');
interactionAction.onclick=()=>{prelude.activate();wake();};document.querySelector('#prelude-reset').onclick=()=>{prelude.reset();wake();};interactionSpeed.onclick=()=>{prelude.speed();wake();};
const warp=createWarp(document.querySelector('#warp-canvas')),work=createWork(document.querySelector('#work-scene'),wake,go),warpControls=document.querySelector('#warp-controls');
warpControls.querySelectorAll('button').forEach((b,i)=>b.onclick=()=>{warp.speed(i+1);warpControls.querySelectorAll('button').forEach(x=>x.setAttribute('aria-pressed',String(x===b)));wake();});
const buttons=chapters.map((c,i)=>{const b=document.createElement('button');b.setAttribute('aria-label',`${i+1} · ${c.name}`);b.title=c.name;b.addEventListener('click',e=>go(chapterStops[i],e.detail===0));nav.append(b);return b;});
const style=(el,key,value)=>{if(el.style[key]!==value)el.style[key]=value;};
const data=(el,key,value)=>{if(el.dataset[key]!==value)el.dataset[key]=value;};
function textAt(index){if(index===shown&&drawn!==-1)return;shown=index;const c=chapters[index];document.querySelector('#chapter').textContent=c.label;document.querySelector('#title').replaceChildren(...c.title.split('\n').flatMap((line,i)=>i?[document.createElement('br'),document.createTextNode(line)]:[document.createTextNode(line)]));document.querySelector('#description').textContent=c.description;document.querySelector('#scene-name').textContent=c.name;document.querySelector('#number').textContent=String(index+1).padStart(2,'0');start.hidden=index!==chapters.length-1;copy.classList.remove('reveal');void copy.offsetWidth;copy.classList.add('reveal');}
function controls(){previous.disabled=journey.target===0;next.disabled=journey.target===LAST_STOP;document.querySelector('#hint').textContent=journey.target===LAST_STOP?'准备好，开始研究':journey.target===5?'滚动，进入作品':journey.target>=6&&journey.target<=8?'滚动，继续看作品':journey.target===9?'滚动，走向新的发现':'滚动，向前探索';buttons.forEach((b,i)=>b.setAttribute('aria-current',String(i===journeyFrame(journey.target).chapter)));}
function go(index,instant=false){if(leaving)return;journey.go(index,instant||reduced.matches);controls();wake();}
function paint(now=performance.now(),dt=1/30){
  const state=journeyFrame(journey.value),p=state.p,near=Math.round(p),distance=Math.abs(p-near);
  textAt(state.chapter);style(copy,'opacity',String(state.copy));style(copy,'transform',reduced.matches||state.chapter===5?'none':`translate3d(0,${(p-near)*-35}px,0)`);style(copy,'filter',reduced.matches||distance<.002||state.chapter===5?'none':`blur(${(distance*16).toFixed(2)}px)`);
  data(root,'scene',String([0,1,2,'warp',3,'work',5][state.chapter]));data(root,'immersive',String(state.warp>.5||state.work>.5));data(root,'work',String(state.work>.5));data(root,'warp',String(state.warp>.5));
  data(root,'position',p.toFixed(5));data(root,'moving',String(journey.moving));
  if(veil)veil.hidden=true;
  const opening=preludeOpacity(p),ending=closing.render(p,now/1000,innerWidth,innerHeight,reduced.matches);style(host,'visibility',p<3.3||ending>.999?'hidden':'visible');data(root,'prelude',String(p<2.5));data(root,'ending',String(ending>.001));prelude.render(p,now/1000,reduced.matches);
  const interactive=p<2.28&&!leaving;interactionTools.hidden=!interactive;interactionSurface.hidden=!interactive||!document.querySelector('#reference-art').hidden;
  if(!interactive){preludeInput.cancel();referenceInput.cancel();}else{const info=prelude.info;for(const [el,text] of [[interactionHelp,info.help],[interactionAction,info.action],[interactionSelection,info.selection]])if(el.textContent!==text)el.textContent=text;cityPicker.hidden=info.stage!==1;cityPicker.value=info.stage===1&&info.selected>=0?String(info.selected):'';interactionSpeed.hidden=info.stage!==2;interactionSpeed.setAttribute('aria-pressed',String(info.speed>1));interactionSpeed.textContent=info.speed>1?'恢复水波':'加快水波';}
  if(scene){if(scene.setDetail(!journey.moving&&Math.abs(p-4)<.025))hands?.resize();if(p>=3.3&&Math.max(opening,state.warp,state.work,ending)<.999&&(now-lastLandscapePaint>=32||!journey.moving)){scene.render(state.landscape,reduced.matches?0:now/1000);lastLandscapePaint=now;}}else style(host,'background',`radial-gradient(ellipse at 65% 40%,${['#789698','#80979b','#41576d','#162d48','#a19e9b','#e0c391'][Math.round(state.landscape)]},#142b3d 75%)`);
  hands?.setActive(Math.abs(p-4)<.45&&!credits.open&&!document.hidden&&!leaving);
  hands?.render(now/1000,state.star);
  warp.render(p,state.warp,dt,reduced.matches);work.render(state,now/1000,dt,reduced.matches);warpControls.hidden=state.warp<.9;
  audio.setRecords(Number(document.querySelector('#reference-art').dataset.playing||0),p<.6);audio.update(state.music);drawn=p;
}
function fastWork(){return journey.value>4.6&&journey.value<9.7||journey.target>=5&&journey.target<=9;}
function tick(now){profiler?.tick(now);frame=0;if(dead||document.hidden||credits.open)return;const fast=fastWork(),interval=1000/(fast&&journey.moving?60:30);if(now+.25<nextPaint){frame=requestAnimationFrame(tick);return;}nextPaint=nextPaint&&now-nextPaint<50?nextPaint+interval:now+interval;const dt=last?Math.min((now-last)/1000,.08):1/60;last=now;journey.tick(dt,fast?workSpring(journey.value,journey.target):5);const paintStart=profiler?performance.now():0;paint(now,dt);profiler?.paint(now,performance.now()-paintStart);if(journey.moving||ambient())schedule();else{last=nextPaint=0;profiler?.suspend();data(root,'renderState','idle');}}
function ambient(){if(journey.value<.001&&!prelude.animating)return false;return !leaving&&(journeyFrame(journey.value).work<.999&&!reduced.matches||hands?.moving||work.animating);}
function schedule(){if(frame||dead||document.hidden)return;data(root,'renderState',journey.moving?'moving':'ambient');frame=requestAnimationFrame(tick);}
function wake(){if(!dead&&!document.hidden){if(!frame)last=0;schedule();}}
function cancel(){cancelAnimationFrame(frame);frame=0;last=nextPaint=0;}
function scrollJourney(delta){if(journey.wheel(delta,performance.now(),work.scrollRange())){audio.arm();if(reduced.matches)journey.snapToTarget();controls();wake();}}
root.addEventListener('wheel',e=>{if(credits.open||leaving||e.ctrlKey)return;e.preventDefault();const factor=e.deltaMode===1?20:e.deltaMode===2?innerHeight:1;scrollJourney((Math.abs(e.deltaX)>Math.abs(e.deltaY)?e.deltaX:e.deltaY)*factor);},{passive:false});
previous.onclick=()=>go(Math.ceil(journey.target-.001)-1);next.onclick=()=>go(Math.floor(journey.target+.001)+1);
root.addEventListener('pointermove',e=>{const x=e.clientX/innerWidth,y=e.clientY/innerHeight;if(journeyFrame(journey.value).work>.99){if(!reduced.matches&&work.animating)work.pointer(x*2-1,y*2-1);return;}root.style.setProperty('--mx',`${(x*100).toFixed(1)}%`);root.style.setProperty('--my',`${(y*100).toFixed(1)}%`);if(!reduced.matches){prelude.pointer(x*2-1,y*2-1);closing.pointer(x*2-1,y*2-1);scene?.pointer(x*2-1,y*2-1);warp.pointer(x-.5);if(journey.value<.12)wake();}},{passive:true});
root.addEventListener('pointerdown',e=>{if(journey.value>9.7&&!e.target.closest('button,a'))closing.tap(e.clientX/innerWidth,e.clientY/innerHeight);},{passive:true});
document.addEventListener('keydown',e=>{if(credits.open||e.target.closest('input,textarea,select')||e.ctrlKey||e.metaKey||e.altKey)return;const moves={ArrowDown:1,PageDown:1,ArrowUp:-1,PageUp:-1};if(e.key in moves){e.preventDefault();if(!e.repeat)go(moves[e.key]>0?Math.floor(journey.target+.001)+1:Math.ceil(journey.target-.001)-1,true);}else if(e.key==='Home'||e.key==='End'){e.preventDefault();go(e.key==='Home'?0:LAST_STOP,true);}});
let touchY=null,touchScrub=false;root.addEventListener('touchstart',e=>{if(credits.open||leaving)return;touchY=e.touches[0].clientY;touchScrub=journey.target>=6&&journey.target<=8;journey.lastWheel=-Infinity;},{passive:true});
root.addEventListener('touchmove',e=>{if(touchY===null||!touchScrub)return;const y=e.touches[0].clientY;scrollJourney((touchY-y)*2);touchY=y;},{passive:true});
root.addEventListener('touchend',e=>{if(touchY===null)return;const delta=touchY-e.changedTouches[0].clientY;touchY=null;if(!touchScrub&&Math.abs(delta)>45)go(journey.target+Math.sign(delta));},{passive:true});
root.addEventListener('touchcancel',()=>{touchY=null;},{passive:true});
// Try autoplay immediately; retry when the browser receives an activation gesture.
// Muting before activation stays muted even if a pending play attempt resolves later.
root.addEventListener('pointerdown',e=>{if(!audio.armed&&!e.target.closest('#sound,a,#credits-open'))audio.arm();},{passive:true});
root.addEventListener('touchend',()=>audio.arm(),{passive:true});
document.addEventListener('keydown',e=>{if(!credits.open&&!e.repeat&&!e.target.closest('#sound,a,#credits-open'))audio.arm();});
document.querySelector('#credits-open').onclick=()=>{cancel();credits.showModal();audio.visibility(true);hands?.setActive(false);preludeInput.cancel();referenceInput.cancel();work.pause(true);};credits.addEventListener('close',()=>{audio.visibility(document.hidden);work.pause(document.hidden);wake();});
document.addEventListener('visibilitychange',()=>{audio.visibility(document.hidden);hands?.visibility(document.hidden);work.pause(document.hidden);if(document.hidden){preludeInput.cancel();referenceInput.cancel();cancel();root.dataset.renderState='hidden';}else wake();});
reduced.addEventListener('change',()=>go(journey.target,true));
window.addEventListener('resize',()=>{clearTimeout(resizeTimer);resizeTimer=setTimeout(()=>{scene?.resize();hands?.resize();prelude.resize();warp.resize();work.resize();wake();},120);});
function fallback(){hands?.dispose();hands=null;scene?.dispose();scene=null;document.querySelector('#fallback').hidden=false;wake();}
host.addEventListener('scene-lost',fallback);
host.addEventListener('scene-ready',wake);
async function enter(e){if(e.button!==0||e.metaKey||e.ctrlKey||e.shiftKey||e.altKey)return;e.preventDefault();if(leaving)return;leaving=true;audio.fadeOut();root.animate([{opacity:1},{opacity:0}],{duration:reduced.matches?180:800,easing:'ease-out',fill:'forwards'});setTimeout(()=>{dispose();location.assign(e.currentTarget?.href||'/?workspace=1');},reduced.matches?200:1000);}
document.querySelectorAll('a[href="/?workspace=1"]').forEach(a=>a.addEventListener('click',enter));
function dispose(){if(dead)return;dead=true;profiler?.dispose();cancel();clearTimeout(resizeTimer);hands?.dispose();hands=null;preludeInput.dispose();referenceInput.dispose();prelude.dispose();closing.dispose();warp.dispose();work.dispose();scene?.dispose();scene=null;audio.dispose();root.dataset.renderState='disposed';}
window.addEventListener('pagehide',dispose);window.addEventListener('pageshow',e=>{if(e.persisted)location.reload();});
import('./earth-globe.mjs?v=4').then(({createEarth})=>{if(!dead){try{prelude.attachGlobe(createEarth(document.querySelector('#earth-scene')));wake();}catch(error){console.warn('Earth: using projected city fallback',error.message);}}}).catch(error=>console.warn('Earth unavailable',error.message));
import('./reference-art.mjs?v=7').then(({createReferenceArt})=>{if(!dead){prelude.attachReference(createReferenceArt(document.querySelector('#reference-art'),wake,{onPlaybackChange(mask){audio.setRecords(mask,true);audio.arm();}}));wake();}}).catch(error=>console.warn('Reference artwork unavailable',error.message));
controls();paint();audio.visibility(document.hidden);audio.arm();
try{const {createScene}=await import('./scene.js?v=9');if(!dead){scene=createScene(host);paint();wake();}}catch(error){console.warn('Intro: using lightweight landscape',error.message);fallback();}
if(scene&&!dead){try{const {createHands}=await import('./hands.js?v=4');if(!dead){hands=createHands({renderer:scene.renderer,panel:document.querySelector('#hand-camera'),button:document.querySelector('#hand-toggle'),wake});paint();wake();}}catch(error){console.warn('Hand controls unavailable',error.message);document.querySelector('#hand-toggle').textContent='手势暂不可用';}}
