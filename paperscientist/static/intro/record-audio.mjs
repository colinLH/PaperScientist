import {RECORD_SCORE} from './record-score.mjs';

const STORAGE_KEY='paperscientist.record-progress.v2';
// Only an incoming and outgoing decoder may exist. Fifteen combinations do
// not mean fifteen simultaneous downloads, media elements or decoded buffers.
export class RecordMusic {
  constructor(ctx,destination,{createAudio=url=>new Audio(url),storage,notify=()=>{},schedule=(fn,ms)=>setTimeout(fn,ms),cancel=id=>clearTimeout(id)}={}){
    this.ctx=ctx;this.destination=destination;this.createAudio=createAudio;this.storage=storage;this.notify=notify;this.schedule=schedule;this.cancel=cancel;
    this.voices=new Map();this.positions={};this.mask=0;this.enabled=false;this.dead=false;
    try {const saved=JSON.parse(storage?.getItem(STORAGE_KEY)||'{}'),legacy=JSON.parse(storage?.getItem('paperscientist.record-progress.v1')||'{}');for(let i=1;i<16;i++){const value=saved[RECORD_SCORE[i].slug]??(i<15?legacy[i]:undefined);if(Number.isFinite(value)&&value>=0)this.positions[i]=value;}}catch{}
  }
  persist(){try{this.storage?.setItem(STORAGE_KEY,JSON.stringify(Object.fromEntries(Object.entries(this.positions).map(([mask,value])=>[RECORD_SCORE[mask].slug,value]))));}catch{}}
  save(v){if(v.ready&&Number.isFinite(v.audio.currentTime))this.positions[v.mask]=v.audio.currentTime;this.persist();}
  fade(v,value){const p=v.gain.gain,now=this.ctx.currentTime;if(p.cancelAndHoldAtTime)p.cancelAndHoldAtTime(now);else {p.cancelScheduledValues(now);p.setValueAtTime(p.value,now);}p.linearRampToValueAtTime(value,now+.38);}
  release(v){this.cancel(v.timer);this.save(v);v.audio.pause();v.abort.abort();v.source.disconnect();v.gain.disconnect();v.audio.removeAttribute('src');v.audio.load();v.audio.remove();this.voices.delete(v.mask);}
  stop(v){this.fade(v,0);this.cancel(v.timer);v.timer=this.schedule(()=>{if(this.voices.get(v.mask)===v&&(v.mask!==this.mask||!this.enabled))this.release(v);},420);}
  set(mask,enabled=true){
    mask=RECORD_SCORE[mask]?mask:0;enabled=Boolean(enabled&&mask);
    if(this.dead||mask===this.mask&&enabled===this.enabled)return;
    this.mask=mask;this.enabled=enabled;
    // Evict any older fading voice before creating another one.
    const previous=[...this.voices.values()];
    for(const v of previous)if(v.mask!==mask&&previous.length>1&&v.fading)this.release(v);
    for(const v of this.voices.values())if(v.mask!==mask||!enabled){v.fading=true;this.stop(v);}
    if(!enabled)return;
    let v=this.voices.get(mask);
    if(v){this.cancel(v.timer);v.fading=false;this.fade(v,1);this.notify(v.ready?'playing':'loading',RECORD_SCORE[mask]);return;}
    const track=RECORD_SCORE[mask],audio=this.createAudio(track.url),gain=this.ctx.createGain(),source=this.ctx.createMediaElementSource(audio),abort=new AbortController();
    gain.gain.value=0;source.connect(gain).connect(this.destination);
    v={mask,audio,gain,source,abort,ready:false,fading:false,lastSave:0};this.voices.set(mask,v);
    audio.preload='auto';audio.loop=true;audio.hidden=true;audio.dataset.recordMix=String(mask);
    if(typeof document!=='undefined')document.body.append(audio);
    const options={signal:abort.signal},current=()=>!this.dead&&this.enabled&&this.mask===mask&&this.voices.get(mask)===v;
    audio.addEventListener('loadedmetadata',()=>{v.ready=true;const position=this.positions[mask]||0;audio.currentTime=Number.isFinite(audio.duration)&&audio.duration>0?position%audio.duration:position;},{...options,once:true});
    audio.addEventListener('timeupdate',()=>{if(Math.abs(audio.currentTime-v.lastSave)>4){v.lastSave=audio.currentTime;this.save(v);}if(current())this.notify('playing',track,audio.currentTime);},options);
    const failed=()=>{if(!current())return;this.notify('error',track);this.release(v);};
    audio.addEventListener('error',failed,options);this.notify('loading',track);
    audio.play().then(()=>{if(current()){this.fade(v,1);this.notify('playing',track,audio.currentTime);}}).catch(failed);
  }
  flush(){for(const v of this.voices.values())this.save(v);}
  dispose(){this.dead=true;for(const v of [...this.voices.values()])this.release(v);}
}
