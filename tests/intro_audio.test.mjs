import test from 'node:test';
import assert from 'node:assert/strict';
import vm from 'node:vm';
import {readFileSync} from 'node:fs';
import {musicGains} from '../paperscientist/static/intro/motion.mjs';
import {RecordMusic} from '../paperscientist/static/intro/record-audio.mjs';

function fixture(){
  let blocked=false,resolvePlay=null;
  const gain=()=>({gain:{value:0,setTargetAtTime(v){this.value=v;},cancelAndHoldAtTime(){}},connect(){return this;},disconnect(){}});
  const button={attrs:{},span:{},addEventListener(_,fn){this.click=fn;},setAttribute(k,v){this.attrs[k]=v;},querySelector(){return this.span;},dataset:{}};
  class Audio {
    constructor(){this.paused=true;this.dataset={};this.currentTime=17;}
    addEventListener(){} pause(){this.paused=true;}
    play(){if(blocked)return Promise.reject(new Error('NotAllowedError'));this.paused=false;return resolvePlay?new Promise(resolve=>resolvePlay.push(resolve)):Promise.resolve();}
    removeAttribute(){} load(){} remove(){}
  }
  class AudioContext {
    constructor(){this.currentTime=1;this.destination={};}
    createGain(){return gain();} createMediaElementSource(){return gain();}
    resume(){return Promise.resolve();} suspend(){} close(){}
  }
  const source=readFileSync(new URL('../paperscientist/static/intro/audio.js',import.meta.url),'utf8').replace(/^import.*\n/gm,'').replace('export class Soundscape','class Soundscape');
  const Soundscape=vm.runInNewContext(source+'\nSoundscape;', {musicGains,RecordMusic,window:{AudioContext},Audio,document:{body:{append(){}}},setTimeout(){return 1;},clearTimeout(){}});
  const sound=new Soundscape(button,{});
  return {sound,button,block(value){blocked=value;},defer(){resolvePlay=[];return ()=>{resolvePlay.forEach(fn=>fn());resolvePlay=null;};}};
}

test('default-on survives autoplay denial and a later gesture starts at the current cue',async()=>{
  const {sound,button,block}=fixture();sound.update(2);block(true);await sound.arm();
  assert.equal(sound.armed,false);assert.equal(button.attrs['aria-pressed'],'true');
  block(false);await sound.arm();assert.equal(sound.armed,true);assert.equal(sound.tracks[0].audio.paused,false);
  assert.equal(sound.master.gain.value,.26);assert.equal(sound.tracks[0].gain.gain.value,1);
});

test('the first sound-button click mutes even before browser activation',async()=>{
  const {sound,button}=fixture();button.click();await sound.arm();
  assert.equal(sound.muted,true);assert.equal(sound.ctx,undefined);assert.equal(button.attrs['aria-pressed'],'false');
});

test('muting while activation is pending is not undone by its completion',async()=>{
  const {sound,button,defer}=fixture();sound.update(2);const finish=defer(),pending=sound.arm();button.click();finish();await pending;
  assert.equal(sound.muted,true);assert.equal(sound.master.gain.value,0);assert.equal(button.attrs['aria-pressed'],'false');
});

test('a paused track resumes without seeking or needing a camera move',async()=>{
  const {sound}=fixture();sound.update(2);await sound.arm();sound.tracks[0].audio.pause();sound.apply();
  assert.equal(sound.tracks[0].audio.paused,false);assert.equal(sound.tracks[0].audio.currentTime,17);
  sound.dispose();assert.equal(sound.dead,true);assert.ok(sound.tracks.every(t=>t.audio.paused));
});
