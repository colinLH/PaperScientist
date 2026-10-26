import {clamp,smooth} from './motion.mjs';
import {aurora} from './cosmic-art.mjs';

export function fieldStrength(camera){return 1-smooth((camera.unfold-.12)/.78);}
export function makeGravitySeeds(count=420){
  let seed=142;const random=()=>((seed=(Math.imul(seed,1664525)+1013904223)>>>0)/4294967296);
  return Array.from({length:count},()=>({angle:random()*Math.PI*2,radius:.22+Math.sqrt(random())*.96,depth:random(),phase:random()*Math.PI*2,size:.7+random()*1.6}));
}

// Analytic orbits keep the same phase when resizing, never allocate more
// particles, and tie the inward pull to the reversible portal camera.
export function fieldPoint(seed,time,camera,width,height,pointer={x:0,y:0}){
  const pull=camera.focus*.32+camera.unfold*.45;
  const a=seed.angle+time*(.055+seed.depth*.055)+pull*1.1;
  const radius=seed.radius*(1-pull*.55),stretch=1+camera.focus*.22;
  const x=Math.cos(a)*radius*width*.69*stretch;
  const y=Math.sin(a)*radius*height*.63*stretch;
  return {x:width/2+x+pointer.x*width*.018*seed.depth,y:height/2+y+pointer.y*height*.018*seed.depth,
    alpha:clamp((.2+seed.depth*.65)*(1-pull*.3),0,1),size:seed.size*(1+camera.focus*.3)};
}

// Blue light field combines the 099 aurora and 107 orbital-light references.
// WORK's existing silhouette/camera stay intact; only their environment changes.
export function drawPortalField(ctx,width,height,camera,time,seeds,pointer){
  const opacity=fieldStrength(camera);if(opacity<.001)return;
  ctx.save();ctx.globalAlpha=opacity;
  const cx=width/2,cy=height/2,r=Math.min(width,height)*(.58-camera.focus*.11);
  const glow=ctx.createRadialGradient(cx,cy,r*.1,cx,cy,r*1.25);
  glow.addColorStop(0,'rgba(120,205,224,.38)');glow.addColorStop(.42,'rgba(24,97,133,.3)');glow.addColorStop(1,'rgba(5,13,24,0)');
  ctx.fillStyle=glow;ctx.fillRect(0,0,width,height);
  aurora(ctx,width,height,time,{portal:camera.focus+camera.unfold*.7,pointer,center:.45});
  for(let i=0;i<3;i++){
    ctx.beginPath();ctx.ellipse(cx,cy,r*(.86+i*.22),r*(.59+i*.15),-.35+i*.26+Math.sin(time*.06)*.04,0,Math.PI*2);
    ctx.strokeStyle=`rgba(191,225,239,${.18-i*.045})`;ctx.lineWidth=.8;ctx.stroke();
  }
  for(const seed of seeds){
    const head=fieldPoint(seed,time,camera,width,height,pointer);
    ctx.globalAlpha=opacity*head.alpha*.55;ctx.fillStyle=seed.depth>.82?'#e6f6fa':'#739aaa';
    ctx.fillRect(head.x,head.y,head.size*.7,head.size*.7);
  }
  ctx.restore();
}
