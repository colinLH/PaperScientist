import {clamp,smooth} from './motion.mjs';

// Stylised lensing, in normalised coordinates. A finite core prevents runaway
// displacement at the lens centre; shared by projected stars and their tails.
export function lensPoint(x,y,strength=1){
  const r2=x*x+y*y,falloff=Math.exp(-r2*1.8),turn=strength*.46*falloff;
  const magnify=1+strength*.065/(r2+.12),c=Math.cos(turn),s=Math.sin(turn);
  return {x:(x*c-y*s)*magnify,y:(x*s+y*c)*magnify};
}

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

export function drawGravityField(ctx,width,height,camera,time,seeds,pointer){
  const opacity=fieldStrength(camera);if(opacity<.001)return;
  ctx.save();ctx.globalAlpha=opacity;
  const glow=ctx.createRadialGradient(width/2,height/2,width*.06,width/2,height/2,width*.72);
  glow.addColorStop(0,'rgba(18,0,24,.9)');glow.addColorStop(.35,'rgba(52,0,37,.36)');glow.addColorStop(1,'rgba(20,0,32,0)');
  ctx.fillStyle=glow;ctx.fillRect(0,0,width,height);
  // Elliptic equipotential contours contract into the WORK opening.
  for(let ring=0;ring<9;ring++){
    const radius=.23+ring*.10,shrink=1-camera.focus*.2-camera.unfold*.36;
    ctx.beginPath();ctx.ellipse(width/2,height/2,width*radius*.78*shrink,height*radius*.85*shrink,-.22+ring*.045,0,Math.PI*2);
    ctx.strokeStyle=ring%3===0?'rgba(255,193,211,.34)':'rgba(34,0,27,.46)';ctx.lineWidth=ring%3===0?1:.7;ctx.stroke();
  }
  for(const seed of seeds){
    const head=fieldPoint(seed,time,camera,width,height,pointer),tail=fieldPoint(seed,time-.7-camera.focus*.65,camera,width,height,pointer);
    ctx.globalAlpha=opacity*head.alpha;
    ctx.strokeStyle=seed.depth>.75?'#ffccd9':'#570626';ctx.lineWidth=seed.size*.65;
    ctx.beginPath();ctx.moveTo(tail.x,tail.y);ctx.lineTo(head.x,head.y);ctx.stroke();
    ctx.fillStyle=seed.depth>.82?'#fff0e6':seed.depth>.4?'#ff6d94':'#310825';
    ctx.beginPath();ctx.arc(head.x,head.y,head.size,0,Math.PI*2);ctx.fill();
  }
  ctx.restore();
}
