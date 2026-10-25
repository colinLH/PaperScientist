// Classic worker intentionally: MediaPipe's WASM loader uses importScripts.
// Camera pixels and landmarks never leave this browser.
let detector=null;
self.onmessage=async ({data})=>{
  try{
    if(data.type==='init'){
      const {FilesetResolver,HandLandmarker}=await import('./vendor/mediapipe/vision_bundle.mjs');
      const files=await FilesetResolver.forVisionTasks(new URL('./vendor/mediapipe/wasm',self.location.href).href);
      detector=await HandLandmarker.createFromOptions(files,{
        baseOptions:{modelAssetPath:new URL('./vendor/mediapipe/hand_landmarker.task',self.location.href).href,delegate:'CPU'},
        runningMode:'VIDEO',numHands:2,minHandDetectionConfidence:.55,minHandPresenceConfidence:.55,minTrackingConfidence:.5
      });
      self.postMessage({type:'ready'});
    }else if(data.type==='frame'){
      const start=performance.now();let result;
      try{result=detector.detectForVideo(data.bitmap,data.timestamp);}finally{data.bitmap.close();}
      self.postMessage({type:'result',landmarks:result.landmarks,ms:performance.now()-start,timestamp:data.timestamp});
    }
  }catch(error){self.postMessage({type:'error',message:error.message});}
};
