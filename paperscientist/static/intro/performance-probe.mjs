// Opt-in local diagnostics (?profile=1). No observers, timers or DOM exist in
// ordinary visits. Measurements use the intro's existing animation loop.
export function createPerformanceProbe(){
  const panel=document.createElement('aside'),button=document.createElement('button'),output=document.createElement('pre');
  panel.style.cssText='position:fixed;left:12px;bottom:12px;z-index:10000;background:#111e;color:#eee;padding:12px;border-radius:8px;font:12px/1.5 monospace;pointer-events:auto;max-width:430px';
  button.textContent='重新采样';output.style.margin='8px 0 0';output.id='intro-performance';panel.append(button,output);document.body.append(panel);
  let start=0,last=0,lastPaint=0,lastReport=0,raf=[],frames=[],costs=[],samples=0;
  function reset(){start=last=lastPaint=lastReport=0;raf=[];frames=[];costs=[];samples=0;output.textContent='采样中…';}
  button.onclick=reset;reset();
  const stats=values=>{const sorted=values.slice().sort((a,b)=>a-b);return {p95:sorted[Math.floor(sorted.length*.95)]||0,max:sorted.at(-1)||0,mean:values.reduce((a,b)=>a+b,0)/Math.max(1,values.length)};};
  return {
    suspend(){last=lastPaint=0;},
    tick(now){if(!start)start=now;if(last)raf.push(now-last);last=now;if(raf.length>1200)raf.shift();},
    paint(now,cost){if(lastPaint)frames.push(now-lastPaint);lastPaint=now;costs.push(cost);samples++;if(costs.length>600){costs.shift();frames.shift();}
      if(now-lastReport<1000)return;lastReport=now;
      const a=stats(raf),f=stats(frames),c=stats(costs),canvas=document.querySelector('.record-links');
      const result={seconds:+((now-start)/1000).toFixed(1),samples,rafFps:+(1000/a.mean).toFixed(1),paintFps:+(1000/f.mean).toFixed(1),frameP95ms:+f.p95.toFixed(2),paintP95ms:+c.p95.toFixed(2),paintMaxMs:+c.max.toFixed(2),longFrames:frames.filter(x=>x>66.7).length,
        recordMix:document.querySelector('#reference-art')?.dataset.playing||'0',recordDecoders:document.querySelectorAll('audio[data-record-mix]').length,notes:Number(canvas?.dataset.notes||0),fxPixels:canvas&&!canvas.hidden?canvas.width*canvas.height:0,hiddenCosmicSuspended:document.querySelector('#prelude-canvas')?.dataset.suspended==='true',
        heapMB:performance.memory?+(performance.memory.usedJSHeapSize/1048576).toFixed(1):null};
      output.textContent=JSON.stringify(result,null,2);
    },
    dispose(){panel.remove();}
  };
}
