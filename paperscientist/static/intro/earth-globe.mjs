import * as THREE from './vendor/three.module.min.js';
import {CITIES,LAND} from './earth-data.mjs';
import {geoPoint,flightPoint,cityLabels,EARTH_YAW,EARTH_SPEED} from './earth-geometry.mjs';

// Same clock as the welcome sequence; no RAF, CDN, image downloads or bloom pass.
export function createEarth(host){
  const renderer=new THREE.WebGLRenderer({alpha:true,antialias:true,powerPreference:'low-power'});
  renderer.setClearColor(0,0);renderer.outputColorSpace=THREE.SRGBColorSpace;
  host.append(renderer.domElement);const labels=document.createElement('div');labels.className='earth-labels';host.append(labels);
  const scene=new THREE.Scene(),camera=new THREE.OrthographicCamera(-1,1,1,-1,.1,10000);camera.position.z=5000;
  const root=new THREE.Group(),globe=new THREE.Group();scene.add(root);root.add(globe);
  const resources=new Set(),keep=x=>(resources.add(x),x),mesh=(g,m,parent=globe)=>{const n=new THREE.Mesh(keep(g),keep(m));parent.add(n);return n;};
  let dead=false,lost=false,viewKey='',selectedBefore=-2;
  const abort=new AbortController();
  renderer.domElement.addEventListener('webglcontextlost',e=>{e.preventDefault();lost=true;host.hidden=true;},{signal:abort.signal});
  renderer.domElement.addEventListener('webglcontextrestored',()=>{lost=false;},{signal:abort.signal});

  const map=document.createElement('canvas');map.width=2048;map.height=1024;const ctx=map.getContext('2d');
  ctx.fillStyle='#000';ctx.fillRect(0,0,2048,1024);ctx.fillStyle='#759396';ctx.strokeStyle='#fff';ctx.lineWidth=.9;
  for(const polygon of LAND){ctx.beginPath();for(const ring of polygon){ring.forEach(([lon,lat],i)=>{const x=(lon+180)/360*2048,y=(90-lat)/180*1024;i?ctx.lineTo(x,y):ctx.moveTo(x,y);});ctx.closePath();}ctx.fill('evenodd');ctx.stroke();}
  const texture=keep(new THREE.CanvasTexture(map));texture.wrapS=THREE.RepeatWrapping;texture.anisotropy=Math.min(4,renderer.capabilities.getMaxAnisotropy());
  const uniforms={land:{value:texture},time:{value:0}};
  const vertex=`varying vec2 tex; varying vec3 n; varying vec3 objectN;
    void main(){tex=uv;n=normalize(normalMatrix*normal);objectN=normal;gl_Position=projectionMatrix*modelViewMatrix*vec4(position,1.);}`;
  mesh(new THREE.SphereGeometry(1,96,64),new THREE.ShaderMaterial({uniforms,vertexShader:vertex,fragmentShader:`
    uniform sampler2D land;uniform float time;varying vec2 tex;varying vec3 n;varying vec3 objectN;
    void main(){
      float mask=texture2D(land,tex).r;float daylight=.40+.60*max(0.,dot(normalize(n),normalize(vec3(-.5,.5,1.))));
      vec3 ocean=vec3(.012,.047,.10),continent=vec3(.035,.22,.30);
      vec3 color=mix(ocean,continent,smoothstep(.08,.4,mask))*daylight;
      color+=vec3(.10,.42,.52)*smoothstep(.64,.95,mask)*.66;
      vec2 g=abs(fract(tex*vec2(36.,18.)+.5)-.5);float grid=1.-smoothstep(.008,.021,min(g.x,g.y));
      color+=vec3(.035,.14,.21)*grid*.6;
      float scan=pow(max(0.,cos(tex.x*6.283185-time*.24)),72.);color+=vec3(.09,.48,.6)*scan*(.18+mask*.38);
      float rim=pow(1.-max(0.,n.z),3.);color+=vec3(.045,.32,.48)*rim*.7;
      gl_FragColor=vec4(color,1.);
    }` }));
  // A thin moving cloud veil uses inexpensive analytic noise; it is not weather data.
  const clouds=mesh(new THREE.SphereGeometry(1.006,64,40),new THREE.ShaderMaterial({uniforms:{time:uniforms.time},transparent:true,depthWrite:false,vertexShader:vertex,fragmentShader:`
    uniform float time;varying vec2 tex;varying vec3 n;varying vec3 objectN;
    void main(){vec3 p=objectN;float wave=sin(p.x*17.+sin(p.y*12.)*2.+time*.07)*sin(p.z*19.+p.y*7.)+sin(p.x*36.+p.z*27.)*.35;
    float a=smoothstep(.55,1.1,wave)*.045*(.25+max(0.,n.z));gl_FragColor=vec4(.55,.76,.83,a);}` }));
  mesh(new THREE.SphereGeometry(1.065,64,40),new THREE.ShaderMaterial({transparent:true,depthWrite:false,side:THREE.BackSide,blending:THREE.AdditiveBlending,vertexShader:vertex,fragmentShader:`varying vec3 n;void main(){float a=pow(max(0.,1.-abs(n.z)),4.)*.55;gl_FragColor=vec4(.12,.53,.80,a);}`}));

  const cityVectors=CITIES.map(c=>{const p=geoPoint(c.lon,c.lat);return new THREE.Vector3(p.x,p.y,p.z);});
  const labelEls=CITIES.map(c=>{const el=document.createElement('span');el.className='earth-city';el.textContent=c.name;labels.append(el);return el;});
  const pointGeometry=keep(new THREE.SphereGeometry(.0075,10,8)),pinGeometry=keep(new THREE.CylinderGeometry(.0012,.004,.065,5));
  const pinMat=keep(new THREE.MeshBasicMaterial({color:'#76dfff',transparent:true,opacity:.78}));
  const pointMat=keep(new THREE.MeshBasicMaterial({color:'#c6f9ff'})),ringGeo=keep(new THREE.RingGeometry(.014,.019,32));
  const pointInstances=new THREE.InstancedMesh(pointGeometry,pointMat,CITIES.length),pinInstances=new THREE.InstancedMesh(pinGeometry,pinMat,CITIES.length);
  ringGeo.setAttribute('phase',new THREE.InstancedBufferAttribute(new Float32Array(CITIES.map((_,i)=>i*.137)),1));
  const ringUniforms={time:uniforms.time,reduced:{value:0}};
  const ringMat=keep(new THREE.ShaderMaterial({uniforms:ringUniforms,transparent:true,depthWrite:false,side:THREE.DoubleSide,
    vertexShader:`attribute float phase;uniform float time;uniform float reduced;varying float alpha;void main(){float p=mix(fract(time*.38+phase),.3,reduced);alpha=(1.-p)*.65;gl_Position=projectionMatrix*modelViewMatrix*instanceMatrix*vec4(position*(1.+p*2.6),1.);}`,
    fragmentShader:`varying float alpha;void main(){gl_FragColor=vec4(.27,.75,1.,alpha);}`}));
  const ringInstances=new THREE.InstancedMesh(ringGeo,ringMat,CITIES.length);globe.add(pointInstances,pinInstances,ringInstances);keep(pointInstances);keep(pinInstances);keep(ringInstances);
  const dummy=new THREE.Object3D();
  cityVectors.forEach((p,i)=>{
    dummy.position.copy(p).multiplyScalar(1.012);dummy.updateMatrix();pointInstances.setMatrixAt(i,dummy.matrix);
    dummy.position.copy(p).multiplyScalar(1.044);dummy.quaternion.setFromUnitVectors(new THREE.Vector3(0,1,0),p);dummy.updateMatrix();pinInstances.setMatrixAt(i,dummy.matrix);
    dummy.position.copy(p).multiplyScalar(1.01);dummy.quaternion.setFromUnitVectors(new THREE.Vector3(0,0,1),p);dummy.updateMatrix();ringInstances.setMatrixAt(i,dummy.matrix);
    dummy.quaternion.identity();
  });
  const selectedDot=mesh(new THREE.SphereGeometry(.013,12,8),new THREE.MeshBasicMaterial({color:'#ffdb91'}));selectedDot.visible=false;
  // Selected city has five intercontinental links; other links provide context.
  const routesGroup=new THREE.Group();globe.add(routesGroup);let routes=[],routeResources=[],signals=null;
  const hubs=[0,12,20,27,33,38];
  function setRoutes(selected){
    signals?.dispose();routesGroup.clear();routeResources.forEach(x=>x.dispose());routeResources=[];routes=[];
    const add=x=>(routeResources.push(x),x),origin=selected<0?1:selected;
    const destinations=[...new Set([...hubs,6,9,4])].filter(x=>x!==origin);
    const pairs=destinations.map(i=>[origin,i]);pairs.push([12,20],[20,27],[33,38]);
    signals=new THREE.InstancedMesh(pointGeometry,pointMat,pairs.length);signals.frustumCulled=false;signals.instanceMatrix.setUsage(THREE.DynamicDrawUsage);routesGroup.add(signals);
    pairs.forEach(([a,b],i)=>{
      const start=cityVectors[a],end=cityVectors[b],height=.13+start.distanceTo(end)*.16;
      const points=Array.from({length:81},(_,j)=>{const p=flightPoint(start,end,j/80,height);return new THREE.Vector3(p.x,p.y,p.z);});
      const curve=new THREE.CatmullRomCurve3(points);
      const line=new THREE.Mesh(add(new THREE.TubeGeometry(curve,80,.0014,3,false)),add(new THREE.MeshBasicMaterial({color:i%3===0?'#f4c782':'#48bbdf',transparent:true,opacity:i%3===0?.72:.44,depthWrite:false})));
      routesGroup.add(line);
      routes.push({start,end,height,offset:i*.137});
    });
  }
  const orbitRoot=new THREE.Group();root.add(orbitRoot);const satellites=[];
  for(let i=0;i<2;i++){
    const orbit=new THREE.Group();orbit.rotation.set(.75+i*.7,.2+i*.7,-.3);orbitRoot.add(orbit);
    const path=Array.from({length:129},(_,j)=>new THREE.Vector3(Math.cos(j/128*Math.PI*2)*(1.22+i*.1),0,Math.sin(j/128*Math.PI*2)*(1.22+i*.1)));
    const line=new THREE.LineLoop(keep(new THREE.BufferGeometry().setFromPoints(path)),keep(new THREE.LineBasicMaterial({color:'#5cacc8',transparent:true,opacity:.23})));orbit.add(line);
    const sat=mesh(new THREE.OctahedronGeometry(.022),new THREE.MeshBasicMaterial({color:'#d9f9ff'}),orbit);satellites.push({sat,r:1.22+i*.1});
  }
  const q=new THREE.Vector3();
  function render({time,yaw,pitch,selected,opacity,w,h,cx,cy,unit,reduced}){
    if(dead||lost||opacity<.001){host.hidden=true;return [];}
    host.hidden=false;host.style.opacity=String(opacity);
    const key=`${w},${h},${devicePixelRatio}`;
    if(key!==viewKey){viewKey=key;renderer.setPixelRatio(Math.min(devicePixelRatio||1,1.5,Math.sqrt(2200000/(w*h))));renderer.setSize(w,h,false);camera.left=-w/2;camera.right=w/2;camera.top=h/2;camera.bottom=-h/2;camera.updateProjectionMatrix();}
    root.position.set(cx-w/2,h/2-cy,0);root.scale.setScalar(unit);
    globe.rotation.set(pitch,EARTH_YAW+time*EARTH_SPEED+yaw,0,'XYZ');uniforms.time.value=time;clouds.rotation.y=time*.006;
    orbitRoot.rotation.y=time*.025;
    if(selected!==selectedBefore){selectedBefore=selected;setRoutes(selected);selectedDot.visible=selected>=0;if(selected>=0)selectedDot.position.copy(cityVectors[selected]).multiplyScalar(1.015);}
    ringUniforms.reduced.value=reduced?1:0;
    routes.forEach((r,i)=>{const p=flightPoint(r.start,r.end,(time*.17+r.offset)%1,r.height);dummy.position.set(p.x,p.y,p.z);dummy.quaternion.identity();dummy.updateMatrix();signals.setMatrixAt(i,dummy.matrix);});signals.instanceMatrix.needsUpdate=true;
    satellites.forEach(({sat,r},i)=>sat.position.set(Math.cos(time*(.22+i*.06)+i*3)*r,0,Math.sin(time*(.22+i*.06)+i*3)*r));
    scene.updateMatrixWorld(true);const projected=cityVectors.map((p,index)=>{q.copy(p).applyEuler(globe.rotation);return {x:cx+q.x*unit,y:cy-q.y*unit,z:q.z,index,name:CITIES[index].name};});
    const placed=cityLabels(projected,{width:w,height:h,selected,limit:w<700?4:8}),visible=new Map(placed.map(p=>[p.index,p]));
    labelEls.forEach((el,i)=>{const p=visible.get(i);el.hidden=!p;if(p){el.style.transform=`translate3d(${p.left}px,${p.top}px,0)`;el.dataset.selected=String(i===selected);}});
    renderer.render(scene,camera);host.dataset.rotation=globe.rotation.y.toFixed(4);host.dataset.cities=String(CITIES.length);host.dataset.visibleCities=projected.filter(p=>p.z>.12).map(p=>CITIES[p.index].en).join(', ');host.dataset.drawCalls=String(renderer.info.render.calls);host.dataset.renderer='webgl';
    return [...projected.filter(p=>p.z>.12),...placed.map(p=>({index:p.index,x:p.left+p.width/2,y:p.top+p.height/2,z:p.z}))];
  }
  return {render,get available(){return !dead&&!lost;},hide(){host.hidden=true;},dispose(){if(dead)return;dead=true;abort.abort();signals?.dispose();routeResources.forEach(x=>x.dispose());resources.forEach(x=>x.dispose());renderer.dispose();renderer.forceContextLoss();host.replaceChildren();host.hidden=true;}};
}
