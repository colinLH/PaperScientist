import test from 'node:test';
import assert from 'node:assert/strict';
import {scenePixelRatio} from '../paperscientist/static/intro/render-quality.mjs';

test('settled UHD and retina scenes reach 3840x2160 without exceeding the cap',()=>{
  for(const [w,h,dpr] of [[3840,2160,1],[1920,1080,2],[2560,1440,2],[7680,4320,1]]){
    const ratio=scenePixelRatio(w,h,dpr,true);assert.equal(Math.round(w*ratio),3840);assert.equal(Math.round(h*ratio),2160);
  }
});
test('moving scenes retain their 1.4 MP budget; small screens are not oversampled',()=>{
  for(const [w,h,dpr] of [[3840,2160,1],[1920,1080,2],[390,844,3]]){
    const ratio=scenePixelRatio(w,h,dpr,false);assert.ok(w*h*ratio*ratio<=1400000.01);assert.ok(ratio<=1.25);
  }
  assert.equal(scenePixelRatio(1280,720,1,true),1);assert.ok(Number.isFinite(scenePixelRatio(0,0,1,true)));
});
