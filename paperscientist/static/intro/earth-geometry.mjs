import {clamp,smooth} from './motion.mjs';
export const EARTH_YAW=2.88;
export const EARTH_SPEED=.075;
export const earthOpacity=p=>smooth((p-.38)/.5)*(1-smooth((p-1.12)/.5));
export function geoPoint(lon,lat,r=1){
  const a=lon*Math.PI/180,b=lat*Math.PI/180,c=Math.cos(b);
  return {x:r*c*Math.cos(a),y:r*Math.sin(b),z:-r*c*Math.sin(a)};
}
// Great-circle interpolation keeps every route outside the surface, including
// dateline crossings. Antipodal endpoints use a stable perpendicular direction.
export function flightPoint(a,b,t,height=.22){
  const d=clamp(a.x*b.x+a.y*b.y+a.z*b.z,-1,1),angle=Math.acos(d);let x,y,z;
  if(d<-.9999){const axis=Math.abs(a.y)<.8?{x:0,y:1,z:0}:{x:1,y:0,z:0};const dot=a.x*axis.x+a.y*axis.y;let q={x:axis.x-a.x*dot,y:axis.y-a.y*dot,z:axis.z-a.z*dot};const l=Math.hypot(q.x,q.y,q.z);q={x:q.x/l,y:q.y/l,z:q.z/l};const c=Math.cos(Math.PI*t),s=Math.sin(Math.PI*t);x=a.x*c+q.x*s;y=a.y*c+q.y*s;z=a.z*c+q.z*s;}
  else {const s=Math.sin(angle),u=s<1e-6?1-t:Math.sin((1-t)*angle)/s,v=s<1e-6?t:Math.sin(t*angle)/s;x=a.x*u+b.x*v;y=a.y*u+b.y*v;z=a.z*u+b.z*v;}
  const r=(1.008+Math.sin(Math.PI*t)*height)/Math.hypot(x,y,z);return {x:x*r,y:y*r,z:z*r};
}
export function cityFocus(city,time,currentYaw=0){
  const raw=-Math.PI/2-city.lon*Math.PI/180-EARTH_YAW-time*EARTH_SPEED;
  return {yaw:currentYaw+Math.atan2(Math.sin(raw-currentYaw),Math.cos(raw-currentYaw)),pitch:clamp(city.lat*Math.PI/180,-.85,.85)};
}
// Front-side labels only; selected city wins and label rectangles never collide.
export function cityLabels(points,{width,height,selected=-1,limit=8}){
  const result=[];
  const candidates=points.filter(p=>p.z>.12).sort((a,b)=>(b.index===selected)-(a.index===selected)||b.z-a.z);
  for(const p of candidates){
    if(result.length>=limit)break;
    const labelWidth=p.name.length*12+22,labelHeight=25;
    for(const side of [1,-1]){
      const x=p.x+(side===1?12:-labelWidth-12),y=p.y-12;
      if(x<8||x+labelWidth>width-38||y<70||y+labelHeight>height*.83)continue;
      const box={...p,left:x,top:y,width:labelWidth,height:labelHeight};
      if(result.some(q=>x<q.left+q.width+8&&x+labelWidth+8>q.left&&y<q.top+q.height+7&&y+labelHeight+7>q.top))continue;
      result.push(box);break;
    }
  }return result;
}
