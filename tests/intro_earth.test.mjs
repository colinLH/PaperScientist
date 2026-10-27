import test from 'node:test';
import assert from 'node:assert/strict';
import {Vector3,Euler} from '../paperscientist/static/intro/vendor/three.module.min.js';
import {CITIES,LAND} from '../paperscientist/static/intro/earth-data.mjs';
import {geoPoint,flightPoint,cityFocus,cityLabels,earthOpacity,EARTH_YAW,EARTH_SPEED} from '../paperscientist/static/intro/earth-geometry.mjs';

test('city atlas covers six inhabited continents with distinct geographic locations',()=>{
  assert.equal(CITIES.length,41);assert.equal(new Set(CITIES.map(c=>c.id)).size,41);
  assert.equal(new Set(CITIES.map(c=>c.region)).size,6);
  for(const c of CITIES){assert.ok(Math.abs(c.lat)<=90&&Math.abs(c.lon)<=180);const p=geoPoint(c.lon,c.lat);assert.ok(Math.abs(Math.hypot(p.x,p.y,p.z)-1)<1e-12);}
  for(const [name,lat,lon] of [['北京',39.9,116.4],['纽约',40.7,-74],['伦敦',51.5,-.1],['悉尼',-33.9,151.2]]){
    const c=CITIES.find(x=>x.name===name);assert.ok(c);assert.ok(Math.abs(c.lat-lat)<.2&&Math.abs(c.lon-lon)<.2);
  }
  assert.equal(LAND.length,127);assert.ok(LAND.reduce((s,p)=>s+p[0].length,0)>4000);
  for(const polygon of LAND)for(const ring of polygon){assert.deepEqual(ring[0],ring.at(-1));for(const [lon,lat] of ring)assert.ok(Math.abs(lat)<=90&&Math.abs(lon)<=180);}
});

test('all city pairs have finite above-surface flight paths and exact endpoints',()=>{
  for(let i=0;i<CITIES.length;i+=4)for(let j=0;j<CITIES.length;j+=3){
    const a=geoPoint(CITIES[i].lon,CITIES[i].lat),b=geoPoint(CITIES[j].lon,CITIES[j].lat);
    for(let k=0;k<=20;k++){const p=flightPoint(a,b,k/20);assert.ok(Object.values(p).every(Number.isFinite));assert.ok(Math.hypot(p.x,p.y,p.z)>=1.007999);}
    const end=flightPoint(a,b,1);assert.ok(Math.hypot(end.x/1.008-b.x,end.y/1.008-b.y,end.z/1.008-b.z)<1e-10);
  }
  for(const b of [{x:1,y:0,z:0},{x:-1,y:0,z:0}])for(const t of [0,.5,1])assert.ok(Object.values(flightPoint({x:1,y:0,z:0},b,t)).every(Number.isFinite));
});

test('city selection faces the requested city without reversing its longitude or teleporting a full revolution',()=>{
  for(const time of [0,21,10000])for(const city of CITIES){
    const focus=cityFocus(city,time,1.4),p=geoPoint(city.lon,city.lat);
    const q=new Vector3(p.x,p.y,p.z).applyEuler(new Euler(focus.pitch,EARTH_YAW+time*EARTH_SPEED+focus.yaw,0,'XYZ'));
    assert.ok(q.z>.98,city.name);assert.ok(Math.abs(q.x)<1e-10);assert.ok(Math.abs(focus.yaw-1.4)<=Math.PI);
  }
});

test('visible labels avoid collisions and back-face labels at desktop and phone widths',()=>{
  for(const [width,height,limit] of [[390,844,4],[1280,800,8],[3840,2160,8]]){
    const points=CITIES.map((c,index)=>({x:width*.7+(index%4)*9,y:height*.5+Math.floor(index/4)*9,z:index===3?-1:.8,index,name:c.name}));
    const labels=cityLabels(points,{width,height,limit,selected:2});assert.ok(labels.length<=limit);assert.equal(labels[0].index,2);assert.ok(!labels.some(p=>p.index===3));
    for(const a of labels){assert.ok(a.left>=8&&a.left+a.width<=width-38);for(const b of labels){if(a===b)continue;assert.ok(a.left+a.width<=b.left||b.left+b.width<=a.left||a.top+a.height<=b.top||b.top+b.height<=a.top);}}
  }
});

test('the earth appears only in chapter two and has continuous reversible fade boundaries',()=>{
  for(const p of [0,.2,2,3,6,10])assert.equal(earthOpacity(p),0);assert.equal(earthOpacity(1),1);
  for(let p=0;p<2;p+=.005){assert.ok(earthOpacity(p)>=0&&earthOpacity(p)<=1);assert.ok(Math.abs(earthOpacity(p+.001)-earthOpacity(p))<.004);assert.ok(Math.abs(earthOpacity(p)-earthOpacity(p+.2-.2))<1e-12);}
});
