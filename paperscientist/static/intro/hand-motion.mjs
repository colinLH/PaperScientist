// Pure hand-particle math shared by the overlay, the tracker and regression tests.
import {clamp} from './motion.mjs';

export const BONES=[[0,1],[1,2],[2,3],[3,4],[0,5],[5,6],[6,7],[7,8],[5,9],[9,10],[10,11],[11,12],[9,13],[13,14],[14,15],[15,16],[13,17],[17,18],[18,19],[19,20],[0,17]];
// Palm triangles [a,b,c,share] and finger capsules [from,to,radius in palm lengths,share].
const PALM=[[0,1,5,.2],[0,5,9,.26],[0,9,13,.24],[0,13,17,.2],[1,2,5,.1]].map(([a,b,c,s])=>[a,b,c,s*.42]);
const FINGERS=[[1,2,.15,.06],[2,3,.13,.045],[3,4,.115,.035],[5,6,.11,.05],[6,7,.1,.032],[7,8,.09,.026],[9,10,.115,.055],[10,11,.105,.036],[11,12,.095,.028],
  [13,14,.11,.05],[14,15,.1,.033],[15,16,.09,.025],[17,18,.095,.038],[18,19,.088,.024],[19,20,.08,.02]];
const TIPS=[8,12,16,20],CENTER=[0,5,9,13,17];

// Fixed for the page lifetime so resizes never reallocate or change the count.
export function particleBudget({cores=4,memory=4,coarse=false}={}){
  return clamp(cores<=2||memory<=2||coarse?1200:cores<=4||memory<=4?2000:3000,1000,3000);
}

// Each particle is bound to joints by weights, so it stays inside the hand outline
// as landmarks move. Even indices belong to the first hand, odd to the second.
export function sampleHand(count,seed=7){
  let state=seed>>>0||1;const random=()=>(state=(Math.imul(state,1664525)+1013904223)>>>0)/4294967296;
  const regions=[...PALM.map(([a,b,c,share])=>({tri:[a,b,c],share})),...FINGERS.map(([a,b,radius,share])=>({bone:[a,b],radius,share}))];
  const total=regions.reduce((s,r)=>s+r.share,0);
  const out={slot:new Float32Array(count),index:new Float32Array(count*3),weight:new Float32Array(count*3),offset:new Float32Array(count*2),seed:new Float32Array(count*4)};
  for(let i=0;i<count;i++){
    let pick=random()*total,r=regions[regions.length-1];
    for(const region of regions){if((pick-=region.share)<0){r=region;break;}}
    out.slot[i]=i%2;
    if(r.tri){let u=random(),v=random();if(u+v>1){u=1-u;v=1-v;}out.index.set(r.tri,i*3);out.weight.set([1-u-v,u,v],i*3);}
    else{const t=random();out.index.set([r.bone[0],r.bone[1],r.bone[1]],i*3);out.weight.set([1-t,t,0],i*3);out.offset.set([random()*2-1,r.radius],i*2);}
    for(let k=0;k<4;k++)out.seed[i*4+k]=Math.min(random(),.99999);
  }
  return out;
}

// 0 = fist, 1 = open palm. Fingertip spread relative to palm length, so it is
// independent of hand size, distance and position. Points are flat [x,y,z]*21.
export function openness(p){
  let cx=0,cy=0,cz=0;for(const k of CENTER){cx+=p[k*3];cy+=p[k*3+1];cz+=p[k*3+2];}cx/=5;cy/=5;cz/=5;
  const palm=Math.max(Math.hypot(p[0]-p[27],p[1]-p[28],p[2]-p[29]),1e-6);let r=0;
  for(const k of TIPS)r+=Math.hypot(p[k*3]-cx,p[k*3+1]-cy,p[k*3+2]-cz);
  return clamp((r/TIPS.length/palm-.55)/.45,0,1);
}

// Short grace period hides single dropped detections; full fade finishes ~0.7 s after loss.
export class HandPresence{
  constructor({grace=.12,fade=.55,rise=.25}={}){Object.assign(this,{grace,fade,rise,alpha:0,seen:-Infinity,born:-Infinity,last:null,reborn:false});}
  update(now,detected){
    const dt=this.last===null?0:clamp(now-this.last,0,.1);this.last=now;this.reborn=false;
    if(detected){if(this.alpha<=.02){this.reborn=true;this.born=now;this.alpha=1;}else this.alpha=Math.min(1,this.alpha+dt/this.rise);this.seen=now;}
    else if(now-this.seen>this.grace)this.alpha=Math.max(0,this.alpha-dt/this.fade);
    return this;
  }
}

// Keeps particle groups attached to the same physical hand across frames.
export function assignSlots(centers,previous){
  const dist=(c,s)=>Math.hypot(c[0]-previous[s].x,c[1]-previous[s].y);
  if(!centers.length)return [];
  if(centers.length===1){
    const live=[0,1].filter(s=>previous[s].alpha>0);
    return [live.length?live.reduce((a,b)=>dist(centers[0],b)<dist(centers[0],a)?b:a):0];
  }
  return dist(centers[0],1)+dist(centers[1],0)<dist(centers[0],0)+dist(centers[1],1)?[1,0]:[0,1];
}

export function coverFit(sw,sh,dw,dh){const scale=Math.max(dw/Math.max(sw,1),dh/Math.max(sh,1));return {scale,x:(dw-sw*scale)/2,y:(dh-sh*scale)/2};}
