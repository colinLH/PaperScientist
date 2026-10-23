// Run with node --test tests/frontend_effects.test.cjs (no browser/dependencies).
const {test} = require('node:test');
const assert = require('node:assert/strict');
const {readFileSync} = require('node:fs');
const {runInNewContext} = require('node:vm');
const source = readFileSync(require('node:path').join(__dirname, '../paperscientist/static/effects.js'), 'utf8');

function environment() {
  let now=0,id=0,draws=0;
  const jobs=new Map(),elements=[];
  class Events {
    constructor(){this.handlers=new Map();}
    addEventListener(name,fn){if(!this.handlers.has(name))this.handlers.set(name,[]);this.handlers.get(name).push(fn);}
    emit(name,event={}){for(const fn of this.handlers.get(name)||[])fn(event);}
  }
  const document=new Events(),window=new Events(),motion=new Events();motion.matches=false;
  const classes=new Set();
  document.hidden=false;
  document.documentElement={classList:{toggle:(name,value)=>value?classes.add(name):classes.delete(name)}};
  document.body={prepend:element=>elements.push(element)};
  document.querySelector=()=>null;
  document.createElement=()=>{
    const element={dataset:{},setAttribute(){}};
    element.getContext=()=>({setTransform(){},clearRect(){if(element.id==='ps-fx')draws++;},
      drawImage(){},fillRect(){},beginPath(){},moveTo(){},lineTo(){},stroke(){},arc(){},fill(){},
      createRadialGradient(){return {addColorStop(){}}},createLinearGradient(){return {addColorStop(){}}}});
    return element;
  };
  const later=(fn,delay)=>{jobs.set(++id,{time:now+delay,fn});return id;};
  const context={window,document,matchMedia:()=>motion,innerWidth:3840,innerHeight:2160,devicePixelRatio:2,
    performance:{now:()=>now},addEventListener:window.addEventListener.bind(window),
    setTimeout:later,clearTimeout:id=>jobs.delete(id),requestAnimationFrame:fn=>later(()=>fn(now),1000/60),cancelAnimationFrame:id=>jobs.delete(id)};
  runInNewContext(source,context);
  function advance(ms){const until=now+ms;let guard=10000;
    while(jobs.size&&guard--){const [key,job]=[...jobs].sort((a,b)=>a[1].time-b[1].time)[0];if(job.time>until)break;jobs.delete(key);now=job.time;job.fn();}
    assert.ok(guard>0,'scheduler must not spin');now=until;
  }
  return {window,document,motion,advance,canvas:elements[0],draws:()=>draws,classes,jobs};
}
test('HiDPI canvas has a bounded backing store, particle count and draw rate',()=>{
  const e=environment(),initial=e.draws();e.advance(1000);
  assert.ok(e.canvas.width*e.canvas.height<=1200000);
  assert.ok(e.canvas.dataset.particles<=48);
  assert.ok(e.draws()-initial<=24);
  assert.ok(e.draws()-initial>=10,'effects must remain animated');
});
test('scrolling suspends draws until the interaction settles, then resumes',()=>{
  const e=environment();e.advance(100);e.window.emit('wheel');const initial=e.draws();
  e.advance(150);e.document.emit('scroll');e.advance(150);
  assert.equal(e.draws(),initial);assert.ok(e.classes.has('ps-effects-paused'));
  e.advance(120);assert.ok(e.draws()>initial);assert.equal(e.canvas.dataset.state,'animating');
});
test('hidden pages and previews do no decorative work; reduced motion stays static',()=>{
  const e=environment();e.document.hidden=true;e.document.emit('visibilitychange');let initial=e.draws();
  e.advance(10000);assert.equal(e.draws(),initial);assert.equal(e.jobs.size,0);
  e.document.hidden=false;e.document.emit('visibilitychange');e.advance(100);assert.ok(e.draws()>initial);
  e.document.emit('ps:overlay',{detail:true});initial=e.draws();e.advance(1000);assert.equal(e.draws(),initial);
  e.document.emit('ps:overlay',{detail:false});e.advance(100);assert.ok(e.draws()>initial);
  e.motion.matches=true;e.motion.emit('change');initial=e.draws();e.advance(10000);assert.equal(e.draws(),initial);assert.equal(e.canvas.dataset.state,'static');
});
