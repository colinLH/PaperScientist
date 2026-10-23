import {musicGains} from './motion.mjs';

export class Soundscape {
  constructor(button, status) {
    this.button=button;this.status=status;this.position=0;this.muted=false;this.armed=false;this.dead=false;this.hidden=false;
    this.names=['Hiraeth','Solace','Aurora'];this.target=[0,0,0];this.sleepTimers=[];
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
      const resume=this.ctx.resume();const plays=this.tracks.map(t=>t.audio.play());
      await Promise.all([resume,...plays]);if(this.dead||attempt!==this.attempt)return;
      this.armed=true;this.apply();
    }catch{if(this.dead||attempt!==this.attempt)return;this.tracks.forEach(t=>t.audio.pause());this.status.textContent='声音已开启，首次点击或按键后播放';}
  }
  ramp(param,value,seconds=.9){const now=this.ctx.currentTime;if(param.cancelAndHoldAtTime)param.cancelAndHoldAtTime(now);else{const v=param.value;param.cancelScheduledValues(now);param.setValueAtTime(v,now);}param.setTargetAtTime(value,now,seconds);}
  update(position){this.position=position;if(this.armed)this.apply();}
  apply(){
    if(!this.armed||this.dead)return;
    const desired=musicGains(this.position),volume=this.muted||this.hidden?0:.26;
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
    this.status.textContent=this.muted||Math.max(...desired)<.01?'':`${this.names[index]} · Scott Buckley`;
    this.button.dataset.mix=this.target.map(x=>x.toFixed(2)).join(',');
  }
  async visibility(hidden){this.hidden=hidden;if(!this.ctx)return;if(hidden){this.apply();this.visibilityTimer=setTimeout(()=>{if(this.hidden)this.ctx.suspend();},1500);}else{clearTimeout(this.visibilityTimer);if(this.armed){await this.ctx.resume();this.apply();}}}
  fadeOut(){if(this.ctx&&this.master)this.ramp(this.master.gain,0,.22);}
  dispose(){this.dead=true;clearTimeout(this.visibilityTimer);this.sleepTimers.forEach(clearTimeout);this.tracks?.forEach(t=>{t.audio.pause();t.audio.removeAttribute('src');t.audio.load();t.audio.remove();t.source.disconnect();t.gain.disconnect();});this.ctx?.close();}
}
