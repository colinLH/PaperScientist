import {clamp,smooth} from './motion.mjs';

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


// Nested orbital architecture: stars from the atlas converge into a portal;
// its exit warms toward the harbor. No repeated aurora motif from chapter one.
export function drawPortalField(ctx,width,height,camera,time,seeds,pointer,arrival=0){
  const opacity=fieldStrength(camera);if(opacity<.001)return;
  ctx.save();ctx.globalAlpha=opacity;
  const cx=width/2+pointer.x*width*.012,cy=height*(.49+arrival*.08),unit=Math.min(width*.7,height*.68),warm=clamp(arrival,0,1);
  const halo=ctx.createRadialGradient(cx,cy,unit*.06,cx,cy,unit*1.2);
  halo.addColorStop(0,`rgba(${90+warm*90},${115+warm*45},${175-warm*40},.35)`);
  halo.addColorStop(.5,`rgba(${20+warm*35},35,65,.2)`);halo.addColorStop(1,'rgba(5,13,24,0)');ctx.fillStyle=halo;ctx.fillRect(0,0,width,height);
  // Thin architectural bands orbit on different planes. Focus draws them inward.
  for(let ring=0;ring<14;ring++){
    const radius=unit*(.22+ring*.073)*(1-camera.focus*.18),tilt=-.43+ring*.063+Math.sin(time*.06)*.05;
    ctx.beginPath();ctx.ellipse(cx,cy,radius,radius*(.52+ring*.018),tilt,0,Math.PI*2);
    ctx.strokeStyle=ring%4===0?`rgba(${177+warm*60},${207+warm*12},${241-warm*90},.38)`:'rgba(104,138,192,.13)';ctx.lineWidth=ring%4===0?1.1:.6;ctx.stroke();
    const a=time*(.045+(ring%3)*.012)+ring*.71;
    ctx.beginPath();ctx.ellipse(cx,cy,radius,radius*(.52+ring*.018),tilt,a,a+.18);
    ctx.strokeStyle=`rgba(${172+warm*83},${222-warm*3},${255-warm*100},${.8+warm*.05})`;ctx.lineWidth=1.5;ctx.stroke();
  }
  // Perspective meridians fan out from the central aperture, then recede.
  for(let i=0;i<28;i++){
    const a=i/28*Math.PI*2+time*.012,r=unit*(1.2-camera.focus*.24);
    ctx.beginPath();ctx.moveTo(cx+Math.cos(a)*unit*.23,cy+Math.sin(a)*unit*.17);
    ctx.lineTo(cx+Math.cos(a)*r,cy+Math.sin(a)*r*.78);ctx.strokeStyle='rgba(138,164,207,.08)';ctx.lineWidth=.6;ctx.stroke();
  }
  for(const seed of seeds){const head=fieldPoint(seed,time,camera,width,height,pointer);ctx.globalAlpha=opacity*head.alpha*.7;ctx.fillStyle=seed.depth>.8?`rgb(${224+warm*31},${236-warm*9},${255-warm*84})`:'#8aa3c6';ctx.fillRect(head.x,head.y,head.size*.7,head.size*.7);}
  ctx.restore();
}
