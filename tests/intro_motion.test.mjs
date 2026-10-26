import test from 'node:test';
import assert from 'node:assert/strict';
import {Journey,musicGains} from '../paperscientist/static/intro/motion.mjs';

test('one wheel gesture advances once; inertia cannot skip chapters',()=>{
 const j=new Journey();assert.equal(j.wheel(40,0),true);
 for(let i=1;i<35;i++)j.wheel(20-i/2,i*16);
 assert.equal(j.target,1);for(let i=0;i<100;i++)j.tick(1/60);j.wheel(50,2400);assert.equal(j.target,2);
});

test('fragmented inertia cannot stack pages during travel, and ignored input is not queued',()=>{
 for(const direction of [1,-1]){
  const j=new Journey(10);j.go(3,true);j.wheel(direction*600,0);
  let now=0;for(const next of [220,460,810]){while(now<next){j.tick(.01);now+=10;}j.wheel(direction*120,next);assert.equal(j.target,3+direction);}
  // Keep the same gesture alive across arrival, without a fresh wheel stroke.
  while(now<2100){j.tick(.01);now+=10;if(now%100===0)j.wheel(direction*10,now);}
  assert.equal(j.target,3+direction);assert.equal(j.wheel(direction*80,2500),true);assert.equal(j.target,3+direction*2);
 }
});

test('arrival includes a short boundary pause, but mid-flight reversal is immediate',()=>{
 const j=new Journey(10);j.go(2,true);j.wheel(100,0);
 while(Math.abs(j.value-j.target)>=.035||Math.abs(j.velocity)>=.25)j.tick(.01);
 assert.equal(j.wheel(100,2000),false);assert.equal(j.target,3);
 for(let i=0;i<25;i++)j.tick(.01);
 assert.equal(j.wheel(100,2400),true);assert.equal(j.target,4);
 j.tick(.02);const p=j.value,v=j.velocity;
 assert.equal(j.wheel(-100,2410),true);assert.equal(j.target,3);assert.equal(j.value,p);assert.equal(j.velocity,v);
});

test('reduced-motion snapping preserves gesture consumption and cannot deadlock the page gate',()=>{
 const j=new Journey(10);j.wheel(100,0);j.snapToTarget();
 assert.equal(j.wheel(100,200),false);assert.equal(j.target,1);
 assert.equal(j.wheel(100,600),true);j.snapToTarget();assert.equal(j.value,2);assert.equal(j.moving,false);
});
test('reversal preserves camera position and velocity, then returns smoothly',()=>{
 const j=new Journey();j.go(1);for(let i=0;i<18;i++)j.tick(1/60);
 const p=j.value,v=j.velocity;j.wheel(-40,1000);assert.equal(j.value,p);assert.equal(j.velocity,v);
 j.tick(1/60);assert.ok(Math.abs(j.value-p)<.04);
 for(let i=0;i<500;i++)j.tick(1/60);assert.equal(j.value,0);assert.equal(j.velocity,0);
 j.go(99,true);assert.equal(j.value,5);j.go(-99,true);assert.equal(j.value,0);
});
test('music gains are continuous, reversible, equal power across boundaries',()=>{
 assert.deepEqual(musicGains(0),[0,0,0]);
 for(let p=2;p<=5;p+=.005){const gains=musicGains(p);assert.ok(Math.abs(gains.reduce((s,x)=>s+x*x,0)-1)<1e-10);const next=musicGains(p+.001);assert.ok(next.every((x,i)=>Math.abs(x-gains[i])<.003));}
 assert.deepEqual(musicGains(2),[1,0,0]);assert.deepEqual(musicGains(3),[0,1,0]);assert.deepEqual(musicGains(4),[0,0,1]);
});
