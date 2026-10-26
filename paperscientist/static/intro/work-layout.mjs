import {clamp} from './motion.mjs';
import {papers} from './paper-previews.mjs';

export const WORK_RANGE={start:6,end:8,step:.02};
export const CURTAIN_START=.04,CURTAIN_END=.96,CURTAIN_COUNT=papers.length;
export const wrap=(n,span)=>((n%span)+span)%span;

// Solve the existing --ease-in-out (.77,0,.175,1) rather than adding a second
// clock. The same aperture is obtained when travelling back over any position.
export function portalEase(value){
  const x=clamp(value,0,1);let lo=0,hi=1,t=x;
  for(let i=0;i<32;i++){t=(lo+hi)/2;const bx=3*(1-t)*(1-t)*t*.77+3*(1-t)*t*t*.175+t*t*t;if(bx<x)lo=t;else hi=t;}
  return x===0||x===1?x:3*(1-t)*t*t+t*t*t;
}
// One reversible camera path: push into the capsule before unrolling the
// letters. On exit, the letters fold first and only then does the view widen.
export function workCamera(position){
  const phase=clamp(Math.min(position-5,9-position),0,1);
  const focus=portalEase(phase/.42),unfold=portalEase((phase-.36)/.64),letters=portalEase((phase-.44)/.56);
  return {phase,focus,unfold,zoom:1+.62*focus,spread:letters+.018*focus*(1-letters)};
}
export function portalBounds(width,height,camera){
  const a=camera.unfold,w=width*(.14*camera.zoom*(1-a)+1.04*a),h=height*(.72*camera.zoom*(1-a)+1.04*a);
  return {x:(width-w)/2,y:(height-h)/2,width:w,height:h,radius:Math.min(w/2,height*.2*camera.zoom)*(1-camera.unfold)};
}
export function workSpring(value,target){return value>4.95&&value<6||value>8&&value<9.05||target===5||target===9?6:11;}
export function railLayout(width,height){
  const top=clamp(height*.15,80,144),bottom=clamp(height*.2,132,180),gapY=clamp(height*.05,22,62);
  const cardHeight=Math.max(70,(height-top-bottom-gapY)/2);
  const cardWidth=Math.min(width*(width<700?.76:.36),cardHeight*1.82,560);
  // The opposite rail enters with one third of a viewport still to travel.
  // Two handoffs exceed a full crossing, so a rail cannot overlap itself.
  const handoff=width*2/3+cardWidth,travel=(CURTAIN_COUNT-1)*handoff+width+cardWidth;
  return {width,height,top,gapY,cardWidth,cardHeight,handoff,travel};
}
export const columnPitch=width=>width*.71*(width<700?.24:.105);
export function workDistance(progress,layout){return (clamp(progress,0,1)-CURTAIN_START)/(CURTAIN_END-CURTAIN_START)*layout.travel;}
export function workScrollRange(width,height){
  const layout=railLayout(width,height);
  return {...WORK_RANGE,step:2*(width/3)*(CURTAIN_END-CURTAIN_START)/layout.travel};
}
export function railCard(index,progress,layout){
  const {width,top,gapY,cardWidth,cardHeight,handoff}=layout;
  const row=(index+1)%2,distance=workDistance(progress,layout);
  const x=width+index*handoff-distance;
  const y=top+row*(cardHeight+gapY);
  return {index,row,x,y,width:cardWidth,height:cardHeight,visible:x+cardWidth>0&&x<width};
}
export function progressForCard(index,layout){
  const distance=index*layout.handoff+(layout.width+layout.cardWidth)/2;
  return CURTAIN_START+distance/layout.travel*(CURTAIN_END-CURTAIN_START);
}
export function entryForCard(index,layout){return CURTAIN_START+index*layout.handoff/layout.travel*(CURTAIN_END-CURTAIN_START);}
export function playingCards(rects,width,current=[]){
  return [0,1].flatMap(row=>{
    const visible=rects.filter(r=>r.row===row&&r.visible);
    if(!visible.length)return [];
    const distance=r=>Math.abs(r.x+r.width/2-width/2);
    visible.sort((a,b)=>distance(a)-distance(b));
    const old=visible.find(r=>current.includes(r.index));
    return [(old&&distance(old)<distance(visible[0])+width*.08?old:visible[0]).index];
  });
}

export function wallTile(index,count,width,height,aperture,progress){
  const offset=wrap(index-count/2-workDistance(progress,railLayout(width,height))/columnPitch(width)+count/2,count)-count/2;
  const angle=offset*(width<700?.24:.105);
  if(Math.abs(angle)>1.23)return null;
  const radius=width*.71,depth=1-(1-Math.cos(angle))*radius*aperture/(width*.85);
  const w=width/(width<700?7.5:18.5)*Math.cos(angle)/depth;
  const h=height*.78/depth;
  const x=width/2+Math.sin(angle)*radius*aperture/depth-w/2;
  return {x,y:(height-h)/2,width:w,height:h,alpha:aperture};
}
export function cameraTile(index,count,width,height,camera,progress){
  const closedW=width/(width<700?7.5:18.5)*.88*(1+.25*camera.focus),closedH=height*(.52+.12*camera.focus);
  // The closed portal is always central, independent of offscreen wall columns.
  // In particular, a narrow resize must not cull its only WORK glyph.
  if(camera.phase===0)return {x:(width-closedW)/2,y:(height-closedH)/2,width:closedW,height:closedH};
  const tile=wallTile(index,count,width,height,1,progress);if(!tile)return null;
  // Individual columns become slim as they separate; retaining the capsule's
  // full glyph width here would smear the middle into a solid red rectangle.
  const w=closedW*(1-portalEase(camera.unfold/.5))+tile.width*Math.sqrt(camera.spread);
  const h=closedH+(tile.height-closedH)*camera.spread;
  return {x:width/2+(tile.x+tile.width/2-width/2)*camera.spread-w/2,y:(height-h)/2,width:w,height:h};
}
export function workPixelRatio(width,height,dpr=1){return Math.min(dpr,1.5,Math.sqrt(2200000/Math.max(1,width*height)));}
