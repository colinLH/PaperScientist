import * as THREE from './vendor/three.module.min.js';
import {smooth} from './motion.mjs';

// A strip of evidence becomes an optical bench. Both use the journey's clock.
export function sculptureOpacity(p){return p<1?1-smooth((p-.12)/.65):smooth((p-1.18)/.66)*(1-smooth((p-2.28)/.5));}
export function ribbonGeometry(steps=320,sides=16){
  const points=[],indices=[];
  for(let i=0;i<=steps;i++){
    const u=i/steps,a=-.82*Math.PI+u*2.25*Math.PI,r=.8+.38*u;
    const center=new THREE.Vector3(Math.cos(a)*r,Math.sin(a)*r*1.13,Math.sin(a*1.15)*.24);
    const tangent=new THREE.Vector3(-Math.sin(a)*r+.38/(2.25*Math.PI)*Math.cos(a),(Math.cos(a)*r+.38/(2.25*Math.PI)*Math.sin(a))*1.13,Math.cos(a*1.15)*.276).normalize();
    const across=new THREE.Vector3().crossVectors(tangent,new THREE.Vector3(0,0,1)).normalize();
    const normal=new THREE.Vector3().crossVectors(tangent,across).normalize();
    const twist=a*.65+.4,width=.12+.18*Math.sin(Math.PI*u)**.65;
    for(let j=0;j<=sides;j++){
      const b=j/sides*Math.PI*2,c=Math.cos(b),s=Math.sin(b);
      // A soft rectangular cross-section gives broad satin faces and a rounded edge.
      const x=Math.sign(c)*Math.abs(c)**.32*width,y=Math.sign(s)*Math.abs(s)**.32*.018;
      const xx=x*Math.cos(twist)-y*Math.sin(twist),yy=x*Math.sin(twist)+y*Math.cos(twist);
      const q=center.clone().addScaledVector(across,xx).addScaledVector(normal,yy);points.push(q.x,q.y,q.z);
      if(i<steps&&j<sides){const n=i*(sides+1)+j;indices.push(n,n+sides+1,n+1,n+1,n+sides+1,n+sides+2);}
    }
  }
  const g=new THREE.BufferGeometry();g.setAttribute('position',new THREE.Float32BufferAttribute(points,3));g.setIndex(indices);g.computeVertexNormals();return g;
}
export function lensOffsets(selected=-1,spread=0){return Array.from({length:6},(_,i)=>(i-2.5)*(.39+spread*.10)+(selected<0?0:(i<selected?-.12:i>selected?.12:0)));}

export function createSculpture(host){
  const renderer=new THREE.WebGLRenderer({alpha:true,antialias:true,powerPreference:'low-power'});
  renderer.outputColorSpace=THREE.SRGBColorSpace;renderer.toneMapping=THREE.ACESFilmicToneMapping;renderer.toneMappingExposure=1.15;renderer.setClearColor(0,0);host.append(renderer.domElement);
  const scene=new THREE.Scene(),camera=new THREE.OrthographicCamera(-1,1,1,-1,1,10000);camera.position.z=5000;
  const root=new THREE.Group();scene.add(root);const ribbon=new THREE.Group(),bench=new THREE.Group();root.add(ribbon,bench);
  const resources=new Set(),keep=x=>(resources.add(x),x),mesh=(g,m,parent)=>{const n=new THREE.Mesh(keep(g),keep(m));parent.add(n);return n;};
  let dead=false,lost=false,key='',last=-1,selected=-2,spread=0;
  const abort=new AbortController();renderer.domElement.addEventListener('webglcontextlost',e=>{e.preventDefault();lost=true;host.hidden=true;},{signal:abort.signal});renderer.domElement.addEventListener('webglcontextrestored',()=>{lost=false;},{signal:abort.signal});
  // Original studio reflection map: large softboxes, not a downloaded HDRI.
  const room=new THREE.Scene();room.background=new THREE.Color('#11151b');
  const panels=[];
  for(const [x,y,z,sx,sy,rotation,color,intensity] of [[-3,2,1,2,5,1.1,'#e5edf4',5],[2,3,0,1,5,-1,'#fff4dc',4],[0,-2,3,5,.25,0,'#adcde3',2],[0,1,-3,5,2,Math.PI,'#ffffff',3]]){
    const g=new THREE.PlaneGeometry(sx,sy),m=new THREE.MeshBasicMaterial({color:new THREE.Color(color).multiplyScalar(intensity),side:THREE.DoubleSide}),p=new THREE.Mesh(g,m);p.position.set(x,y,z);p.rotation.y=rotation;room.add(p);panels.push(g,m);
  }
  const pmrem=new THREE.PMREMGenerator(renderer);const environment=keep(pmrem.fromScene(room,0));scene.environment=environment.texture;pmrem.dispose();panels.forEach(x=>x.dispose());
  scene.add(new THREE.HemisphereLight('#e8f1ff','#25201d',2));
  const light=new THREE.DirectionalLight('#fff4df',4);light.position.set(-3,5,4);scene.add(light);
  const rim=new THREE.DirectionalLight('#a8c7dd',3);rim.position.set(3,-1,2);scene.add(rim);
  const silver=keep(new THREE.MeshStandardMaterial({color:'#b7c0c8',metalness:1,roughness:.22,envMapIntensity:1.2,side:THREE.DoubleSide}));
  const dark=keep(new THREE.MeshStandardMaterial({color:'#343c47',metalness:.92,roughness:.26,envMapIntensity:1.1}));
  const gold=keep(new THREE.MeshStandardMaterial({color:'#c3ac80',metalness:.9,roughness:.26,envMapIntensity:1}));
  const strip=mesh(ribbonGeometry(),silver,ribbon);strip.rotation.z=-.35;
  // Hairline etching follows the same physical surface, rather than orbiting particles.
  const threadPoints=[];for(let i=0;i<=240;i++){const a=-.82*Math.PI+i/240*2.25*Math.PI,r=.8+.38*i/240;threadPoints.push(new THREE.Vector3(Math.cos(a)*r,Math.sin(a)*r*1.13,Math.sin(a*1.15)*.24+.022));}
  const thread=mesh(new THREE.TubeGeometry(new THREE.CatmullRomCurve3(threadPoints),240,.003,4,false),gold,ribbon);thread.rotation.z=-.35;
  const signal=mesh(new THREE.SphereGeometry(.022,12,8),new THREE.MeshBasicMaterial({color:'#fff0d0'}),ribbon);
  const curve=new THREE.CatmullRomCurve3(threadPoints);
  const stages=[],targets=[],offsets=lensOffsets();
  const lensGeo=keep(new THREE.SphereGeometry(1,64,32));
  for(let i=0;i<6;i++){
    const stage=new THREE.Group();stage.position.x=offsets[i];bench.add(stage);stages.push(stage);
    const radius=.78-Math.abs(i-2.5)*.055;
    const ring=mesh(new THREE.TorusGeometry(radius,.023,12,128),i===5?gold:silver,stage);ring.rotation.y=Math.PI/2;
    const housing=mesh(new THREE.TorusGeometry(radius+.055,.018,8,128),dark,stage);housing.rotation.y=Math.PI/2;
    const glass=mesh(lensGeo,new THREE.MeshPhysicalMaterial({color:i===5?'#dfcda5':'#b8d1d7',metalness:.12,roughness:.12,transparent:true,opacity:.2,clearcoat:1,clearcoatRoughness:.09,side:THREE.FrontSide,depthWrite:false,envMapIntensity:1.4}),stage);glass.scale.set(.065,radius*.96,radius*.96);
    // Instrument graduations / sparse radial supports, each lens is an actual selectable stage.
    const marks=[];for(let k=0;k<48;k++){const a=k/48*Math.PI*2,r0=radius+.085,r1=r0+(k%4===0?.033:.012);marks.push(0,Math.sin(a)*r0,Math.cos(a)*r0,0,Math.sin(a)*r1,Math.cos(a)*r1);}
    const g=keep(new THREE.BufferGeometry());g.setAttribute('position',new THREE.Float32BufferAttribute(marks,3));stage.add(new THREE.LineSegments(g,keep(new THREE.LineBasicMaterial({color:'#9dabb6',transparent:true,opacity:.55}))));
    const marker=mesh(new THREE.SphereGeometry(.032,12,8),gold,stage);marker.position.set(0,radius+.13,0);targets.push(marker);
    stage.userData.glass=glass;stage.userData.ring=ring;
  }
  // Converging ray bundle makes the instrument's explanatory purpose visible.
  const rays=[];for(let i=0;i<7;i++){const a=i/7*Math.PI*2;const pts=[new THREE.Vector3(-1.8,Math.cos(a)*.43,Math.sin(a)*.43),new THREE.Vector3(.75,Math.cos(a)*.14,Math.sin(a)*.14),new THREE.Vector3(1.65,0,0)];const g=keep(new THREE.BufferGeometry().setFromPoints(pts));const line=new THREE.Line(g,keep(new THREE.LineBasicMaterial({color:'#d1b783',transparent:true,opacity:.3})));bench.add(line);rays.push(line);}
  const focus=mesh(new THREE.SphereGeometry(.045,24,12),gold,bench);focus.position.x=1.65;
  const focusRing=mesh(new THREE.TorusGeometry(.11,.006,6,64),silver,bench);focusRing.rotation.y=Math.PI/2;focusRing.position.x=1.65;
  function hide(){host.hidden=true;last=-1;}
  const point=new THREE.Vector3();
  const labels=['问题','方法','数据','实验','评估','表达'].map(text=>{const el=document.createElement('span');el.className='optical-label';el.textContent=text;host.append(el);return el;});
  return {get available(){return !dead&&!lost;},hide,
    render({p,time,state,aim,w,h,cx,cy,unit,reduced}){
      if(dead||lost)return [];const opacity=sculptureOpacity(p);if(opacity<.001){hide();return [];}
      host.hidden=false;host.style.opacity=String(opacity);host.dataset.art=p<1?'evidence-ribbon':'optical-bench';
      const ratio=Math.min(devicePixelRatio||1,1.5,Math.sqrt(2200000/(w*h))),next=w+':'+h+':'+ratio;
      if(key!==next){key=next;renderer.setPixelRatio(ratio);renderer.setSize(w,h,false);camera.left=-w/2;camera.right=w/2;camera.top=h/2;camera.bottom=-h/2;camera.updateProjectionMatrix();}
      const dt=last<0?0:Math.min(.05,Math.max(0,time-last));last=time;
      root.position.set(cx-w/2,h/2-(w<900?cy:h*.46),0);root.scale.setScalar(unit*(p<1?.74:(w<900?.60:.68)));ribbon.visible=p<1;bench.visible=p>=1;
      const motion=reduced?0:time;
      const turn=reduced?0:aim.x*.10,tilt=reduced?0:aim.y*.08;
      if(p<1){
        ribbon.rotation.set(.08+tilt+state.pitch*.25,-.35+turn+state.yaw*.35+Math.sin(motion*.13)*.1,-.12);
        const pulse=reduced?0:Math.min(.07,state.pulses.reduce((sum,v)=>sum+Math.sin(Math.min(1,v.age/1.8)*Math.PI)*.055,0));
        strip.scale.set(1+pulse,1-pulse*.35,1+pulse);thread.scale.copy(strip.scale);
        signal.position.copy(curve.getPoint((motion*.045)%1)).applyAxisAngle(new THREE.Vector3(0,0,1),-.35);signal.visible=!reduced;
      }else{
        if(selected!==state.selected){selected=state.selected;host.dataset.selected=String(selected);}
        const target=selected<0?0:1;spread+=(target-spread)*(reduced?1:1-Math.exp(-dt*10));
        const xs=lensOffsets(selected,spread);
        bench.rotation.set(.28+tilt+state.pitch*.3,-.55+turn+state.yaw*.38,-.24+Math.sin(motion*.1)*.018);
        stages.forEach((stage,i)=>{stage.position.x=xs[i];stage.userData.glass.material.opacity=i===selected?.46:.18;stage.userData.ring.material=i===selected?gold:silver;});
        rays.forEach((line,i)=>line.material.opacity=reduced?.3:.22+.09*Math.sin(motion*.9+i*.25));
      }
      scene.updateMatrixWorld(true);renderer.render(scene,camera);
      host.dataset.drawCalls=String(renderer.info.render.calls);host.dataset.pixels=String(renderer.domElement.width*renderer.domElement.height);host.dataset.motion=motion.toFixed(3);host.dataset.yaw=(p<1?ribbon.rotation.y:bench.rotation.y).toFixed(3);
      const hits=targets.map((marker,index)=>{marker.getWorldPosition(point).project(camera);const x=(point.x+1)*w/2,y=(1-point.y)*h/2;labels[index].hidden=p<1||(w<900&&index!==state.selected);labels[index].style.transform=`translate3d(${x}px,${y-28}px,0) translateX(-50%)`;labels[index].dataset.selected=String(index===state.selected);return {index,x,y};});return p<1?[]:hits;
    },
    dispose(){if(dead)return;dead=true;abort.abort();resources.forEach(x=>x.dispose());renderer.dispose();renderer.forceContextLoss();renderer.domElement.remove();labels.forEach(el=>el.remove());host.hidden=true;}
  };
}
