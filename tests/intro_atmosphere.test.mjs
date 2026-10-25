import test from 'node:test';
import assert from 'node:assert/strict';
import {mistEnvelope} from '../paperscientist/static/intro/atmosphere.mjs';

test('mist stays strong before the star scene and reverses smoothly', () => {
  assert.equal(mistEnvelope(0),1);
  assert.equal(mistEnvelope(2),1);
  assert.equal(mistEnvelope(3),0);
  assert.equal(mistEnvelope(4),0);
  for(let p=2.1;p<3;p+=.01) {
    assert(mistEnvelope(p)>=mistEnvelope(p+.01));
    assert(Math.abs(mistEnvelope(p+.001)-mistEnvelope(p))<.003);
  }
  const path=[2,2.3,2.8,3,2.8,2.3,2];
  assert.deepEqual(path.map(mistEnvelope),path.toReversed().map(mistEnvelope));
});
