// One camera, one worker and at most one in-flight frame. Dependencies are
// injectable so permission races and shutdown can be tested without a camera.
export class HandTracker{
  constructor({video,onStatus=()=>{},onResult=()=>{},media=constraints=>navigator.mediaDevices.getUserMedia(constraints),
    worker=()=>new Worker(new URL('./hand-worker.js',import.meta.url)),bitmap=video=>{const scale=384/Math.max(video.videoWidth,video.videoHeight);return createImageBitmap(video,{resizeWidth:Math.max(1,Math.round(video.videoWidth*scale)),resizeHeight:Math.max(1,Math.round(video.videoHeight*scale))});},
    now=()=>performance.now(),interval=70}={}){
    Object.assign(this,{video,onStatus,onResult,media,makeWorker:worker,bitmap,now,interval,active:false,enabled:false,dead:false,epoch:0,worker:null,stream:null,busy:false,ready:false,last:0,lastVideo:-1,timer:0,watchdog:0});
  }
  status(state,text){this.state=state;this.onStatus(state,text);}
  async start(){
    if(this.dead||this.enabled)return;
    this.enabled=true;const epoch=++this.epoch;this.status('requesting','请允许使用摄像头');
    try{
      const stream=await this.media({audio:false,video:{facingMode:'user',width:{ideal:640},height:{ideal:480},frameRate:{ideal:24,max:30}}});
      if(this.dead||epoch!==this.epoch){stream.getTracks().forEach(t=>t.stop());return;}
      this.stream=stream;stream.getVideoTracks().forEach(track=>track.addEventListener?.('ended',()=>{if(epoch===this.epoch)this.fail('摄像头已断开，请重新连接后重试');},{once:true}));
      this.video.srcObject=stream;await this.video.play();
      if(this.dead||epoch!==this.epoch)return;
      this.status('camera','摄像头已就绪 · 第四幕开启手势');this.setActive(this.active);
    }catch(error){if(epoch!==this.epoch||this.dead)return;this.stop();
      const text={NotAllowedError:'未获摄像头权限，可稍后重试',NotFoundError:'未找到摄像头',NotReadableError:'摄像头正被占用，请关闭其他应用后重试',SecurityError:'当前浏览器不允许摄像头访问'}[error.name]||'摄像头无法启动，请重试';
      this.status('unavailable',text);
    }
  }
  setActive(active){
    this.active=active;
    if(this.stream)this.stream.getVideoTracks().forEach(t=>{t.enabled=active;});
    clearTimeout(this.timer);this.timer=0;
    if(!active||!this.stream||this.dead)return;
    if(!this.worker){
      this.status('loading','正在准备手势识别…');const epoch=this.epoch;
      try{
        const worker=this.makeWorker();this.worker=worker;
        this.watchdog=setTimeout(()=>this.fail('手势模型加载超时，请重试'),45000);
        worker.onmessage=({data})=>{
          if(epoch!==this.epoch||this.dead)return;
          clearTimeout(this.watchdog);this.watchdog=0;
          if(data.type==='ready'){this.ready=true;this.status('ready','张开手掌，让星光随你移动');this.schedule();}
          else if(data.type==='result'){
            this.busy=false;
            // Include inference time in the cadence; don't add a full frame
            // period after every result. Keep some CPU idle time on slow devices.
            this.interval=Math.max(16,70-data.ms,Math.min(80,data.ms*.35));
            if(this.active)this.onResult(data.landmarks,data.ms,data.timestamp);this.schedule();
          }
          else if(data.type==='error')this.fail('手势识别暂不可用，请重试');
        };
        worker.onerror=()=>{if(epoch===this.epoch)this.fail('手势识别未能启动，请重试');};
        worker.postMessage({type:'init'});
      }catch{this.fail('当前浏览器不支持后台手势识别');}
    }else this.schedule();
  }
  schedule(){clearTimeout(this.timer);if(this.active&&this.ready&&!this.dead)this.timer=setTimeout(()=>this.capture(),this.interval);}
  async capture(){
    this.timer=0;if(this.busy||!this.active||!this.ready||this.dead)return;
    if(this.video.readyState<2||this.lastVideo===this.video.currentTime){this.schedule();return;}
    this.busy=true;this.lastVideo=this.video.currentTime;const epoch=this.epoch;let frame=null;
    try{
      frame=await this.bitmap(this.video);
      if(epoch!==this.epoch||this.dead||!this.active){frame.close();if(epoch===this.epoch){this.busy=false;this.schedule();}return;}
      this.watchdog=setTimeout(()=>this.fail('手势识别响应超时，请重试'),10000);
      this.worker.postMessage({type:'frame',bitmap:frame,timestamp:this.now()},[frame]);
      frame=null; // Ownership was transferred; the worker closes it after inference.
    }catch{frame?.close();if(epoch===this.epoch){this.busy=false;clearTimeout(this.watchdog);this.fail('摄像头画面读取失败，请重试');}}
  }
  fail(text){this.stop();this.status('unavailable',text);}
  stop(){
    ++this.epoch;this.enabled=false;clearTimeout(this.timer);clearTimeout(this.watchdog);this.timer=this.watchdog=0;
    this.worker?.terminate();this.worker=null;this.ready=false;this.busy=false;this.lastVideo=-1;
    this.stream?.getTracks().forEach(t=>t.stop());this.stream=null;this.video.srcObject=null;
    this.onResult([],0);
  }
  dispose(){this.dead=true;this.stop();}
}
