import {clamp} from './motion.mjs';

const COLORS=['#df477c','#eb9a23','#268eaa','#8263d3','#4d9c72','#d76436'];
// A single fixed burst, not an emitter. Repeated toggles cannot accumulate it.
export class RecordFireworks {
  constructor(){this.mask=0;this.age=5;this.cooldown=0;this.pending=false;this.bursts=0;}
  get active(){return this.age<3.8;}
  select(mask){if(mask!==15)this.pending=false;else if(this.mask!==15&&this.cooldown<=0)this.pending=true;this.mask=mask;}
  step(dt,reduced=false){
    dt=clamp(dt,0,.1);this.cooldown=Math.max(0,this.cooldown-dt);
    if(this.pending){this.pending=false;if(!reduced){this.age=0;this.cooldown=4.5;this.bursts++;}}
    this.age=Math.min(5,this.age+dt);if(reduced)this.age=5;
  }
  draw(ctx,w,h){
    if(!this.active)return;
    const n=w<700?40:80,s=Math.min(w*.19,h*.30),centers=[[.20,.30,0],[.76,.27,.36],[.49,.19,.70]];
    ctx.save();ctx.lineCap='round';
    centers.forEach(([cx,cy,delay],j)=>{
      const t=this.age-delay;if(t<0||t>3.1)return;
      // A rising comet blooms into a damped radial spray.
      if(t<.45){const q=t/.45,y=h*(.76+(cy-.76)*q);ctx.strokeStyle=COLORS[j*2];ctx.lineWidth=2;ctx.globalAlpha=1;ctx.beginPath();ctx.moveTo(w*cx,y+14);ctx.lineTo(w*cx,y);ctx.stroke();return;}
      const age=t-.45,alpha=Math.pow(Math.max(0,1-age/2.65),1.4);
      for(let i=0;i<n;i++){
        const angle=i*2.399963+ j*.7,speed=.45+.55*((i*37%79)/79),radius=s*speed*(1-Math.exp(-age*2.4)),prev=s*speed*(1-Math.exp(-Math.max(0,age-.045)*2.4));
        const fall=age*age*h*.037,x=w*cx+Math.cos(angle)*radius,y=h*cy+Math.sin(angle)*radius+fall;
        ctx.globalAlpha=alpha;ctx.strokeStyle=COLORS[(i+j)%COLORS.length];ctx.lineWidth=(i%3===0?2:1.1)*Math.min(1.6,w/1100+.5);
        ctx.beginPath();ctx.moveTo(w*cx+Math.cos(angle)*prev,h*cy+Math.sin(angle)*prev+Math.max(0,age-.045)**2*h*.037);ctx.lineTo(x,y);ctx.stroke();
      }
    });ctx.restore();
  }
  dispose(){this.age=5;this.pending=false;}
}
