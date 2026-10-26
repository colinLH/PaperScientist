import {clamp} from './motion.mjs';
import {warpDepth} from './journey-map.mjs';

// Adapted from the user's 095-starfield-warp reference: 400 projected stars,
// colored rounded trails, a mouse-steered vanishing point and five speeds.
// One shared journey clock replaces its permanent requestAnimationFrame loop.
export function createWarp(canvas) {
  const ctx = canvas.getContext('2d', {alpha:true});
  const colors = ['#ffffff','#ffffff','#dbe9ff','#a5f3fc','#f0abfc','#bfdbfe'];
  let seed = 95, w = 1, h = 1, ratio = 1, aim = 0, steer = 0, travel = 0, lastPosition = 3, level = 3, active = false, flow = 0, direction = 1;
  const random = () => { seed = (seed * 1664525 + 1013904223) >>> 0; return seed / 4294967296; };
  const stars = Array.from({length:400}, () => ({x:(random()*2-1)*1.15,y:(random()*2-1)*1.15,z:random(),color:colors[Math.floor(random()*colors.length)]}));
  function resize() {
    w = Math.max(1,innerWidth); h = Math.max(1,innerHeight);
    ratio = Math.min(devicePixelRatio || 1, 1.5, Math.sqrt(2600000 / (w*h)));
    canvas.width = Math.round(w*ratio); canvas.height = Math.round(h*ratio);
    canvas.dataset.particles = stars.length;
  }
  function render(position, alpha, dt, reduced = false) {
    canvas.hidden = alpha < .001;
    canvas.style.opacity = String(alpha);
    if (!ctx || alpha < .001) { active = false; lastPosition = position; flow=0; return; }
    const delta = active ? position - lastPosition : 0;
    active = true; lastPosition = position;
    const speed = [0,.25,.51,.93,1.5,2.28][level];
    // Retain travel direction at rest and ease velocity through zero when the
    // user reverses. Both steering and speed changes are frame-rate independent.
    if(Math.abs(delta)>.0002)direction=Math.sign(delta);
    const desired=Math.abs(delta)>.0002?delta/Math.max(dt,.001)*1.8:speed*.35*direction;
    flow+=(desired-flow)*(1-Math.exp(-dt*8));
    const motion = reduced ? 0 : flow*dt;
    travel += motion; steer += (aim-steer)*(1-Math.exp(-dt*7));
    ctx.setTransform(ratio,0,0,ratio,0,0);
    ctx.clearRect(0,0,w,h); ctx.fillStyle='#02030a'; ctx.fillRect(0,0,w,h);
    const cx = w*(.5+steer*.24), cy = h*.5, scale = Math.min(w,h)*.55;
    const haze = ctx.createRadialGradient(cx,cy,0,cx,cy,Math.min(w,h)*.75);
    haze.addColorStop(0,'#142146'); haze.addColorStop(.25,'#080d25'); haze.addColorStop(1,'#02030a');
    ctx.fillStyle=haze; ctx.fillRect(0,0,w,h); ctx.lineCap='round';
    for (const s of stars) {
      const z = warpDepth(s.z,travel), tail = clamp(z+motion*.9,.055,1);
      const x = cx+s.x*scale/z, y=cy+s.y*scale/z;
      if(x < -80 || x > w+80 || y < -80 || y > h+80) continue;
      const t=1-z; ctx.globalAlpha=Math.min(1,.15+t*1.15); ctx.strokeStyle=s.color;
      ctx.lineWidth=Math.min(2.6,.35+t*2.3);
      ctx.beginPath();ctx.moveTo(cx+s.x*scale/tail,cy+s.y*scale/tail);ctx.lineTo(x+.1,y+.1);ctx.stroke();
    }
    ctx.globalAlpha=1;canvas.dataset.direction=motion<0?'reverse':'forward';
  }
  resize();
  return {render,resize,pointer(x){aim=clamp(x,-.5,.5);},speed(value){level=clamp(value,1,5);},dispose(){canvas.width=canvas.height=1;canvas.hidden=true;}};
}
