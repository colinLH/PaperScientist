import {clamp} from './motion.mjs';

export const WORK_RANGE={start:6,end:8,sensitivity:1/900};
export const wrap=(n,span)=>((n%span)+span)%span;

// Solve the existing --ease-in-out (.77,0,.175,1) rather than adding a second
// clock. The same aperture is obtained when travelling back over any position.
export function portalEase(value){
  const x=clamp(value,0,1);let lo=0,hi=1,t=x;
  for(let i=0;i<14;i++){t=(lo+hi)/2;const bx=3*(1-t)*(1-t)*t*.77+3*(1-t)*t*t*.175+t*t*t;if(bx<x)lo=t;else hi=t;}
  return x===0||x===1?x:3*(1-t)*t*t+t*t*t;
}
export function railLayout(width,height){
  const top=clamp(height*.15,80,144),bottom=clamp(height*.2,132,180),gapY=clamp(height*.05,22,62);
  const cardHeight=Math.max(70,(height-top-bottom-gapY)/2);
  const cardWidth=Math.min(width*(width<700?.76:.36),cardHeight*1.82,560);
  // Even a sliver counts as visible: one full viewport plus one card between
  // successive leading edges keeps each rail to one curtain at all times.
  const gapX=clamp(width*.075,28,160),stride=width+cardWidth+gapX,cycle=stride*3;
  const offset=Math.max(0,Math.min(width*.14,(width-cardWidth)/2-20));
  return {width,height,top,gapY,cardWidth,cardHeight,gapX,stride,cycle,offset,travel:stride*2+offset};
}
export function railCard(index,progress,layout){
  const {width,top,gapY,cardWidth,cardHeight,gapX,stride,cycle,travel,offset}=layout;
  const row=index%2,column=Math.floor(index/2),leftBoundary=-cardWidth-gapX/2;
  const base=(width-cardWidth)/2+column*stride+(row?offset:-offset);
  const x=wrap(base-clamp(progress,0,1)*travel-leftBoundary,cycle)+leftBoundary;
  const y=top+row*(cardHeight+gapY);
  return {index,row,x,y,width:cardWidth,height:cardHeight,visible:x+cardWidth>0&&x<width};
}
export function progressForCard(index,layout){
  const distance=Math.floor(index/2)*layout.stride+(index%2?layout.offset:-layout.offset);
  return clamp(distance/layout.travel,0,1);
}
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
  const offset=wrap(index-count/2-clamp(progress,0,1)*14+count/2,count)-count/2;
  const angle=offset*(width<700?.24:.105);
  if(Math.abs(angle)>1.23)return null;
  const radius=width*.71,depth=1-(1-Math.cos(angle))*radius*aperture/(width*.85);
  const w=width/(width<700?7.5:18.5)*Math.cos(angle)/depth;
  const h=height*.78/depth;
  const x=width/2+Math.sin(angle)*radius*aperture/depth-w/2;
  return {x,y:(height-h)/2,width:w,height:h,alpha:aperture};
}
export function workPixelRatio(width,height,dpr=1){return Math.min(dpr,1.5,Math.sqrt(2200000/Math.max(1,width*height)));}
