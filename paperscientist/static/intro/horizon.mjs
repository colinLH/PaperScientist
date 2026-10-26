// A warm research harbor continues the Work portal's circles into the dawn.
// Pure drawing: one existing canvas, no textures, physics or independent timer.
export function drawHorizon(ctx,w,h,time,pointer){
  const narrow=w<900,cx=w*(narrow?.59:.73)+pointer.x*8,cy=h*(narrow?.68:.58),u=Math.min(w*(narrow?.54:.37),h*.4);
  ctx.save();
  const dusk=ctx.createLinearGradient(0,h*.35,0,h);
  dusk.addColorStop(0,'rgba(8,22,36,0)');dusk.addColorStop(1,'rgba(7,22,33,.8)');ctx.fillStyle=dusk;ctx.fillRect(0,0,w,h);
  const shade=ctx.createLinearGradient(0,0,narrow?0:w*.7,narrow?h*.58:0);
  shade.addColorStop(0,'rgba(8,24,38,.72)');if(narrow)shade.addColorStop(.62,'rgba(8,24,38,.48)');shade.addColorStop(1,'rgba(8,24,38,0)');ctx.fillStyle=shade;ctx.fillRect(0,0,w,h);
  const glow=ctx.createRadialGradient(cx,cy-u*.4,0,cx,cy-u*.4,u*1.3);
  glow.addColorStop(0,'rgba(255,228,171,.32)');glow.addColorStop(1,'rgba(255,211,135,0)');ctx.fillStyle=glow;ctx.fillRect(cx-u*1.5,cy-u*1.8,u*3,u*3);
  // Monumental orbital instrument, satellites, and the last travelling beacon.
  for(let i=0;i<3;i++){
    ctx.beginPath();ctx.ellipse(cx,cy-u*.25,u*(.76+i*.09),u*(.26+i*.12),-.36+i*.2,0,Math.PI*2);
    ctx.strokeStyle=i===1?'rgba(255,230,186,.58)':'rgba(169,222,230,.35)';ctx.lineWidth=i===1?1.4:.75;ctx.stroke();
  }
  for(let i=0;i<4;i++){
    const a=time*(.035+i*.008)+i*1.6,x=cx+Math.cos(a)*u*.86,y=cy-u*.25+Math.sin(a)*u*.39;
    ctx.fillStyle='#f9e7bd';ctx.beginPath();ctx.arc(x,y,i===0?4:2,0,Math.PI*2);ctx.fill();
    if(i===0){ctx.strokeStyle='#c3d7db';ctx.strokeRect(x-10,y-3,7,6);ctx.strokeRect(x+3,y-3,7,6);}
  }
  // Terraced platforms and distinct lab silhouettes; windows give a human scale.
  for(let layer=0;layer<3;layer++){
    const y=cy+u*(.34+layer*.17),rx=u*(.68+layer*.13);
    ctx.fillStyle=['#263e48','#1a303c','#102533'][layer];ctx.beginPath();ctx.ellipse(cx,y,rx,u*.18,0,0,Math.PI*2);ctx.fill();
    ctx.strokeStyle='rgba(158,213,218,.38)';ctx.lineWidth=1;ctx.stroke();
    for(let i=0;i<14;i++){const a=i/14*Math.PI,x=cx+Math.cos(a)*rx*.92;ctx.fillStyle=i%3?'#b6bfa477':'#f6d89ca0';ctx.fillRect(x,y+Math.sin(a)*u*.14,2,3);}
  }
  for(let i=0;i<7;i++){
    const x=cx+(i-3)*u*.16,y=cy+u*(.31+Math.abs(i-3)*.018),bw=u*(i===3?.18:.09),bh=u*(.18+(i%3)*.06);
    ctx.fillStyle=i===3?'#364c54':'#203943';ctx.fillRect(x-bw/2,y-bh,bw,bh);
    ctx.strokeStyle='#90bac282';ctx.lineWidth=.8;ctx.strokeRect(x-bw/2,y-bh,bw,bh);
    ctx.beginPath();ctx.moveTo(x+bw/2,y-bh);ctx.lineTo(x+bw*.72,y-bh-u*.025);ctx.lineTo(x+bw*.72,y-u*.025);ctx.lineTo(x+bw/2,y);ctx.closePath();ctx.fillStyle='#102a37';ctx.fill();
    ctx.beginPath();ctx.moveTo(x-bw/2,y-bh);ctx.lineTo(x-bw*.28,y-bh-u*.025);ctx.lineTo(x+bw*.72,y-bh-u*.025);ctx.lineTo(x+bw/2,y-bh);ctx.closePath();ctx.fillStyle='#65838c';ctx.fill();
    if(i===3){ctx.beginPath();ctx.arc(x,y-bh,bw*.52,Math.PI,Math.PI*2);ctx.fillStyle='#93a7a6';ctx.fill();ctx.stroke();}
    else{ctx.beginPath();ctx.moveTo(x,y-bh);ctx.lineTo(x,y-bh-u*.045);ctx.stroke();}
    for(let row=0;row<3;row++)for(let col=0;col<3;col++){ctx.fillStyle=(row+col+i)%3===0?'#ffdf9f':'#86b8be99';ctx.fillRect(x-bw*.32+col*bw*.25,y-bh*.75+row*bh*.23,bw*.12,bh*.08);}
  }
  // Two radio dishes and a glass research spire break the regular skyline.
  for(const side of [-1,1]){const x=cx+side*u*.54,y=cy+u*.38;ctx.strokeStyle='#bcd7d7';ctx.lineWidth=1.2;ctx.beginPath();ctx.moveTo(x,y);ctx.lineTo(x+side*u*.035,y-u*.19);ctx.stroke();ctx.beginPath();ctx.ellipse(x+side*u*.035,y-u*.19,u*.07,u*.022,side*.6,0,Math.PI);ctx.fillStyle='#688b96';ctx.fill();ctx.stroke();}
  // A lit bridge leading toward the next research journey.
  ctx.beginPath();ctx.moveTo(cx-u*.12,cy+u*.85);ctx.bezierCurveTo(cx-u*.7,cy+u*.8,cx-u*.3,cy+u*.55,cx,cy+u*.51);
  ctx.strokeStyle='rgba(197,224,223,.55)';ctx.lineWidth=2;ctx.stroke();
  for(let i=0;i<45;i++){const a=i*2.3999,r=u*(.3+(i%13)/13),x=cx+Math.cos(a)*r,y=cy+Math.sin(a)*r*.55;ctx.globalAlpha=.25+.3*(.5+.5*Math.sin(time*.7+i));ctx.fillStyle='#fff1c6';ctx.fillRect(x,y,1.4,1.4);}
  ctx.restore();
}
