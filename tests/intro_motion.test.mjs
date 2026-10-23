import test from 'node:test';
import assert from 'node:assert/strict';
import {Journey,musicGains} from '../paperscientist/static/intro/motion.mjs';

test('one wheel gesture advances once; inertia cannot skip chapters',()=>{
 const j=new Journey();assert.equal(j.wheel(40,0),true);
 for(let i=1;i<35;i++)j.wheel(20-i/2,i*16);
 assert.equal(j.target,1);j.wheel(50,1000);assert.equal(j.target,2);
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
