import {musicGains} from './motion.mjs';
import {RecordMusic} from './record-audio.mjs';

export class Soundscape {
  constructor(button, status) {
    this.button=button;this.status=status;this.position=0;this.muted=false;this.armed=false;this.dead=false;this.hidden=false;
    this.names=['Hiraeth','Solace','Aurora'];this.target=[0,0,0];this.sleepTimers=[];this.recordMask=0;this.recordActive=false;
    button.addEventListener('click',()=>{this.muted=!this.muted;this.updateButton();if(!this.muted&&!this.armed)this.arm();else this.apply();});
    this.updateButton();
  }
  updateButton(){this.button.setAttribute('aria-pressed',String(!this.muted));this.button.querySelector('span').textContent=this.muted?'声音已关闭':'声音已开启';}
  async arm() {
    if(this.dead||this.muted||this.hidden||this.armed)return;
    const attempt=this.attempt=(this.attempt||0)+1;
    if(!this.ctx){
      const AudioContext=window.AudioContext||window.webkitAudioContext;
      if(!AudioContext){this.status.textContent='当前浏览器不支持场景音乐';return;}
      this.ctx=new AudioContext();this.master=this.ctx.createGain();this.master.gain.value=0;this.master.connect(this.ctx.destination);
      let storage;try{storage=window.localStorage;}catch{}
      this.records=new RecordMusic(this.ctx,this.master,{storage,notify:(state,track,seconds)=>{
        if(!this.recordActive||!this.recordMask)return;
        const message=state==='error'?'唱片音乐加载失败，关闭再开启声音可重试':state==='loading'?`正在加载 ${track.title}`:`${track.title} · Scott Buckley`;
        if(this.status.textContent!==message)this.status.textContent=message;
        this.button.dataset.recordState=state;this.button.dataset.recordTitle=track.title;
        if(seconds!==undefined)this.button.dataset.recordTime=seconds.toFixed(2);
        const feedback=document.querySelector?.('#record-audio-status');
        if(feedback)feedback.textContent=state==='error'?'音乐加载失败 · 关闭再开启声音可重试':state==='loading'?'正在加载音乐…':'Scott Buckley'+(seconds===undefined?'':` · ${Math.floor(seconds/60)}:${String(Math.floor(seconds%60)).padStart(2,'0')}`);
      }});
      this.tracks=this.names.map(name=>{
        const audio=new Audio(`/intro-assets/audio/${name.toLowerCase()}.mp3`);audio.preload='metadata';audio.loop=true;audio.dataset.track=name;audio.hidden=true;document.body.append(audio);
        const source=this.ctx.createMediaElementSource(audio),gain=this.ctx.createGain();gain.gain.value=0;source.connect(gain).connect(this.master);
        audio.addEventListener('error',()=>{this.status.textContent=`${name} 加载失败，可静音继续探索`;});
        return {audio,source,gain};
      });
    }
    try{
      // Default-on is the user's preference. Autoplay may be denied, so retry
      // from real pointer/key/touch gestures without silently changing that preference.
      const resume=this.ctx.resume(),gains=musicGains(this.position);
      const plays=this.tracks.filter((_,i)=>gains[i]>.001&&!(this.recordActive&&this.recordMask)).map(t=>t.audio.play());
      await Promise.all([resume,...plays]);if(this.dead||attempt!==this.attempt)return;
      this.armed=true;this.apply();
    }catch{if(this.dead||attempt!==this.attempt)return;this.tracks.forEach(t=>t.audio.pause());this.status.textContent='声音已开启，首次点击或按键后播放';}
  }
  ramp(param,value,seconds=.9){const now=this.ctx.currentTime;if(param.cancelAndHoldAtTime)param.cancelAndHoldAtTime(now);else{const v=param.value;param.cancelScheduledValues(now);param.setValueAtTime(v,now);}param.setTargetAtTime(value,now,seconds);}
  update(position){this.position=position;if(this.armed)this.apply();}
  setRecords(mask,active){if(this.recordMask===mask&&this.recordActive===active)return;this.recordMask=mask;this.recordActive=active;this.button.dataset.recordMix=String(active?mask:0);if(this.armed)this.apply();}
  apply(){
    if(!this.armed||this.dead)return;
    const recordsPlaying=this.recordActive&&this.recordMask,desired=recordsPlaying?[0,0,0]:musicGains(this.position),volume=this.muted||this.hidden?0:.26;
    this.records?.set(this.recordMask,Boolean(recordsPlaying&&!this.muted&&!this.hidden));
    if(volume!==this.volume){this.volume=volume;this.ramp(this.master.gain,volume,.3);}
    desired.forEach((gain,i)=>{
      const needsStart=gain>.001&&this.tracks[i].audio.paused&&!this.muted&&!this.hidden;
      if(Math.abs(gain-this.target[i])<.008&&!(gain===0&&this.target[i]!==0)&&!needsStart)return;
      this.target[i]=gain;const t=this.tracks[i];clearTimeout(this.sleepTimers[i]);
      if(gain>.001&&t.audio.paused)t.audio.play().catch(()=>{if(this.dead)return;this.status.textContent='首次点击或按键后继续播放';this.armed=false;});
      this.ramp(t.gain.gain,gain);
      if(gain===0)this.sleepTimers[i]=setTimeout(()=>{if(this.target[i]===0)t.audio.pause();},6000);
    });
    // Tracks retain currentTime when paused. Reversing a journey never seeks them.
    this.tracks.forEach((t,i)=>{if(!desired[i]&&t.gain.gain.value<.001)t.audio.pause();});
    this.updateButton();
    const index=desired.indexOf(Math.max(...desired));
    if(!recordsPlaying||this.muted)this.status.textContent=this.muted||Math.max(...desired)<.01?'':`${this.names[index]} · Scott Buckley`;
    this.button.dataset.mix=this.target.map(x=>x.toFixed(2)).join(',');
  }
  async visibility(hidden){this.hidden=hidden;if(!this.ctx)return;if(hidden){this.apply();this.visibilityTimer=setTimeout(()=>{if(this.hidden)this.ctx.suspend();},1500);}else{clearTimeout(this.visibilityTimer);if(this.armed){await this.ctx.resume();this.apply();}}}
  fadeOut(){if(this.ctx&&this.master)this.ramp(this.master.gain,0,.22);}
  dispose(){this.dead=true;this.records?.dispose();clearTimeout(this.visibilityTimer);this.sleepTimers.forEach(clearTimeout);this.tracks?.forEach(t=>{t.audio.pause();t.audio.removeAttribute('src');t.audio.load();t.audio.remove();t.source.disconnect();t.gain.disconnect();});this.ctx?.close();}
}
