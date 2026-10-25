// Atmosphere follows camera position, so reversing a scroll never restarts a fade.
export function mistEnvelope(position){
  const t=Math.max(0,Math.min(1,(position-2.1)/.9));
  return 1-t*t*(3-2*t);
}

// A single small, reusable alpha texture; no per-frame noise or blur framebuffer.
export function paintMist(canvas){
  canvas.width=256;canvas.height=128;
  const ctx=canvas.getContext('2d');
  const lobes=[[.18,.55,.29,.30],[.40,.44,.38,.44],[.64,.54,.32,.35],[.81,.47,.24,.26]];
  const pixels=ctx.createImageData(256,128);
  for(let y=0;y<128;y++)for(let x=0;x<256;x++){
    const u=x/255,v=y/127;let a=0;
    for(const [cx,cy,rx,ry] of lobes)a+=Math.exp(-3*((u-cx)**2/rx**2+(v-cy)**2/ry**2));
    const wisps=.76+.14*Math.sin(u*19+v*11)+.10*Math.sin(u*37-v*23);
    const edge=Math.sin(Math.PI*u)**.8*Math.sin(Math.PI*v)**1.2;
    const i=(y*256+x)*4;
    pixels.data[i]=pixels.data[i+1]=pixels.data[i+2]=255;
    pixels.data[i+3]=Math.round(Math.min(.74,a*.42)*wisps*edge*255);
  }
  ctx.putImageData(pixels,0,0);
}
