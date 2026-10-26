// Pure navigation/mixing math, shared by the scene and regression tests.
export const clamp = (x, a, b) => Math.max(a, Math.min(b, x));
export const smooth = x => { x = clamp(x, 0, 1); return x * x * (3 - 2 * x); };
const PAGE_GESTURE_GAP=320, BOUNDARY_PAUSE=.18;
export class Journey {
  constructor(last = 5) { this.last = last; this.target = 0; this.value = 0; this.velocity = 0; this.lastWheel = -Infinity; this.direction = 0; this.used = false; this.delta = 0; this.scrubbing=false; this.boundaryTime=BOUNDARY_PAUSE; this.travelDirection=0; }
  go(target, instant = false) { this.target = clamp(target, 0, this.last); this.travelDirection=Math.sign(this.target-this.value); this.scrubbing=false; this.boundaryTime=0; if (instant) this.snapToTarget(); }
  snapToTarget(){this.value=this.target;this.velocity=0;this.boundaryTime=BOUNDARY_PAUSE;}
  wheel(delta, now, range=null) {
    const direction = Math.sign(delta);
    if (!direction) return false;
    const inWork=range&&this.target>=range.start&&this.target<=range.end;
    const fresh=now-this.lastWheel>(inWork?180:PAGE_GESTURE_GAP)||direction!==this.direction;
    if (fresh) { this.used = false; this.delta = 0; }
    this.lastWheel = now; this.direction = direction; this.delta += delta;
    const ready=this.boundaryTime>=BOUNDARY_PAUSE;
    // Retraction remains immediate. Forward input cannot stack destinations
    // before the current page has arrived and had a short breathing space.
    const reversing=!this.scrubbing&&this.moving&&direction===-this.travelDirection;
    if(inWork){
      // Do not let the inertia of the entrance gesture skip through the work.
      if(this.used&&!this.scrubbing&&!fresh)return false;
      const outside=this.target===range.start&&direction<0||this.target===range.end&&direction>0;
      if(outside){if(!fresh||(!ready&&!reversing)||Math.abs(this.delta)<18)return false;this.used=true;this.go(this.target+direction);return true;}
      if(!this.scrubbing&&!ready){this.used=true;return false;}
      // A wheel/trackpad gesture owns one column. Its large initial delta and
      // trailing inertia cannot race several previews across the viewport.
      if(this.used&&!fresh||Math.abs(this.delta)<18)return false;
      const next=clamp(this.target+direction*range.step,range.start,range.end);
      this.used=true;this.scrubbing=true;const changed=next!==this.target;this.target=next;if(changed)this.boundaryTime=0;return changed;
    }
    if (this.used || Math.abs(this.delta) < 18) return false;
    if(!ready&&!reversing){this.used=true;return false;}
    this.used = true; this.go(this.target + direction); return true;
  }
  tick(dt, omega=5) {
    // Exact critically damped spring. Retargeting preserves both position and
    // velocity, including a reversal halfway through a camera move.
    const x = this.value - this.target, b = this.velocity + omega * x;
    const decay = Math.exp(-omega * Math.min(dt, .08));
    this.value = this.target + (x + b * Math.min(dt, .08)) * decay;
    this.velocity = (this.velocity - omega * b * Math.min(dt, .08)) * decay;
    this.boundaryTime=Math.abs(this.value-this.target)<.035&&Math.abs(this.velocity)<.25?Math.min(BOUNDARY_PAUSE,this.boundaryTime+Math.min(dt,.08)):0;
    if (Math.abs(this.value - this.target) < .0002 && Math.abs(this.velocity) < .001) { this.value = this.target; this.velocity = 0; }
    return this.value;
  }
  get moving() { return this.value !== this.target || this.velocity !== 0; }
}
export function musicGains(position) {
  const fade = smooth((position - 1.35) / .65);
  if (position <= 2) return [fade, 0, 0];
  if (position < 3) { const t = smooth(position - 2) * Math.PI / 2; return [Math.cos(t), Math.sin(t), 0]; }
  if (position >= 4) return [0, 0, 1];
  const t = smooth(position - 3) * Math.PI / 2;
  return [0, Math.cos(t), Math.sin(t)];
}
