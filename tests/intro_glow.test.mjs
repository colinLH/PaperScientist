import test from 'node:test';
import assert from 'node:assert/strict';
import {Vector3} from '../paperscientist/static/intro/vendor/three.module.min.js';
import {createGlowPath,circlePath} from '../paperscientist/static/intro/glow-path.js';

test('closed orbit joins both ends exactly, with finite neighbors and continuous distance',()=>{
  const path=createGlowPath([circlePath(19)],{closed:true}),g=path.geometry,p=g.getAttribute('position'),d=g.getAttribute('distance');
  assert.equal(p.count,514);assert.equal(g.index.count,256*6);
  for(let axis=0;axis<3;axis++)assert.equal(p.array[axis],p.array[256*6+axis]);
  assert.ok([...g.getAttribute('previous').array,...g.getAttribute('next').array].every(Number.isFinite));
  assert.ok(Math.abs(d.array.at(-1)-2*Math.PI*19)<.02);
  g.dispose();path.material.dispose();
});
test('separate star-map links have independent indices and DPR changes allocate no geometry',()=>{
  const links=[[new Vector3(0,0,0),new Vector3(1,1,0)],[new Vector3(4,3,0),new Vector3(5,6,0)]];
  const path=createGlowPath(links),g=path.geometry,index=g.index.array;
  assert.equal(index.length,12);assert.ok([...index.slice(0,6)].every(i=>i<4));assert.ok([...index.slice(6)].every(i=>i>=4));
  const before=g.getAttribute('position').array;path.resize(3840,2160,.4);assert.equal(before,g.getAttribute('position').array);
  assert.deepEqual(path.uniforms.viewport.value.toArray(),[1536,864]);assert.equal(path.uniforms.pixelRatio.value,.4);
  g.dispose();path.material.dispose();
});
