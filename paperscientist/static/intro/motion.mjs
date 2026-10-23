// Pure navigation/mixing math, shared by the scene and regression tests.
export const clamp = (x, a, b) => Math.max(a, Math.min(b, x));
export const smooth = x => { x = clamp(x, 0, 1); return x * x * (3 - 2 * x); };
export class Journey {
  constructor(last = 5) { this.last = last; this.target = 0; this.value = 0; this.velocity = 0; this.lastWheel = -Infinity; this.direction = 0; this.used = false; this.delta = 0; }
  go(target, instant = false) { this.target = clamp(target, 0, this.last); if (instant) { this.value = this.target; this.velocity = 0; } }
  wheel(delta, now) {
    const direction = Math.sign(delta);
    if (!direction) return false;
    if (now - this.lastWheel > 180 || direction !== this.direction) { this.used = false; this.delta = 0; }
    this.lastWheel = now; this.direction = direction; this.delta += delta;
    if (this.used || Math.abs(this.delta) < 18) return false;
    this.used = true; this.go(this.target + direction); return true;
  }
  tick(dt) {
    // Exact critically damped spring. Retargeting preserves both position and
    // velocity, including a reversal halfway through a camera move.
    const omega = 5, x = this.value - this.target, b = this.velocity + omega * x;
    const decay = Math.exp(-omega * Math.min(dt, .08));
    this.value = this.target + (x + b * Math.min(dt, .08)) * decay;
    this.velocity = (this.velocity - omega * b * Math.min(dt, .08)) * decay;
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
