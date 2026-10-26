import * as THREE from './vendor/three.module.min.js';
import {clamp, smooth} from './motion.mjs';
import {createGlowPath,circlePath} from './glow-path.js';
import {createConstellation} from './constellation.js';
import {scenePixelRatio} from './render-quality.mjs';
import {mistEnvelope,paintMist} from './atmosphere.mjs';

// One small scene, instanced trees, no shadows or post-processing framebuffers.
export function createScene(host) {
  const renderer = new THREE.WebGLRenderer({antialias:false,alpha:false,powerPreference:'low-power'});
  renderer.outputColorSpace = THREE.SRGBColorSpace;
  host.append(renderer.domElement);
  const scene = new THREE.Scene(), camera = new THREE.PerspectiveCamera(50, 1, .5, 1800);
  scene.fog = new THREE.FogExp2('#879eaa', .0065);
  const hemi = new THREE.HemisphereLight('#d2e9ec','#24343a',2.1), sun = new THREE.DirectionalLight('#ffe4ba',2.2);
  sun.position.set(-150,120,-400); scene.add(hemi,sun);
  const resources = new Set();
  const geometry = g => { resources.add(g); return g; };
  const material = m => { resources.add(m); return m; };
  const softTexture = stops => { const c=document.createElement('canvas');c.width=c.height=128;const g=c.getContext('2d'),r=g.createRadialGradient(64,64,0,64,64,64);stops.forEach(([o,col])=>r.addColorStop(o,col));g.fillStyle=r;g.fillRect(0,0,128,128);const t=new THREE.CanvasTexture(c);t.colorSpace=THREE.SRGBColorSpace;resources.add(t);return t; };
  let seed = 41;
  const random = () => { seed = (Math.imul(seed,1664525)+1013904223)>>>0; return seed/4294967296; };
  const height = (x,z) => -18 + Math.pow(Math.abs(x)/35,1.2)*7 + Math.sin(x*.027+z*.012)*8 + Math.sin(z*.025)*5 + Math.sin(x*.08-z*.04)*2;
  const groundMaterial = material(new THREE.MeshLambertMaterial({color:'#ffffff',vertexColors:true,flatShading:true}));
  const land = geometry(new THREE.PlaneGeometry(1100,1400,100,110)); land.rotateX(-Math.PI/2);
  const pos=land.attributes.position, tones=['#2f444b','#526868','#869a92','#bcc8bf'].map(x=>new THREE.Color(x)), shade=[], tone=new THREE.Color();
  for(let i=0;i<pos.count;i++){const y=height(pos.getX(i),pos.getZ(i));pos.setY(i,y);const t=clamp((y+24)/34+(random()-.5)*.12,0,.999)*3,k=Math.floor(t);tone.copy(tones[k]).lerp(tones[k+1],t-k);shade.push(tone.r,tone.g,tone.b);}
  land.setAttribute('color',new THREE.Float32BufferAttribute(shade,3));
  land.computeVertexNormals(); scene.add(new THREE.Mesh(land,groundMaterial));
  // Narrow river through the valley; its quiet reflection separates depth layers.
  const waterMaterial=material(new THREE.MeshBasicMaterial({color:'#abc8ca',transparent:true,opacity:.58}));
  const water=new THREE.Mesh(geometry(new THREE.PlaneGeometry(23,1300)),waterMaterial);water.rotation.x=-Math.PI/2;water.position.y=-14;scene.add(water);
  const pineMaterial=material(new THREE.MeshLambertMaterial({color:'#203a3c',side:THREE.DoubleSide,flatShading:true}));
  const bark=material(new THREE.MeshLambertMaterial({color:'#32403e'}));
  const vertices=[];
  function triangle(a,b,c){vertices.push(...a,...b,...c);}
  for(let tier=0;tier<9;tier++) {
    const y=1.6+tier*.86, radius=(9-tier)*.30;
    for(let j=0;j<9;j++) {
      const a=j*Math.PI*2/9+tier*.9,b=(j+1)*Math.PI*2/9+tier*.9,m=(a+b)/2;
      const r=radius*(.80+random()*.35);
      triangle([0,y+1.9,0],[Math.cos(a)*r,y,Math.sin(a)*r],[Math.cos(m)*r*.75,y+.5,Math.sin(m)*r*.75]);
      triangle([0,y+1.9,0],[Math.cos(m)*r*.75,y+.5,Math.sin(m)*r*.75],[Math.cos(b)*r,y-.1,Math.sin(b)*r]);
    }
  }
  const foliage=geometry(new THREE.BufferGeometry());foliage.setAttribute('position',new THREE.Float32BufferAttribute(vertices,3));foliage.computeVertexNormals();
  const treeCount=620, trees=new THREE.InstancedMesh(foliage,pineMaterial,treeCount);
  const trunks=new THREE.InstancedMesh(geometry(new THREE.CylinderGeometry(.12,.3,9,5).translate(0,4.5,0)),bark,treeCount);
  const dummy=new THREE.Object3D();
  for(let i=0;i<treeCount;i++) {
    let x=(random()-.5)*570,z=random()*1100-650;
    if(Math.abs(x)<18)x+=x<0?-23:23;
    if(Math.hypot(x-35,z+125)<36)x+=65;
    const s=.8+random()*2.4;dummy.position.set(x,height(x,z)-.1,z);dummy.rotation.y=random()*6.28;dummy.scale.set(s,s*(.9+random()*.3),s);dummy.updateMatrix();trees.setMatrixAt(i,dummy.matrix);trunks.setMatrixAt(i,dummy.matrix);
  }
  scene.add(trees,trunks);
  const rockMaterial=material(new THREE.MeshLambertMaterial({color:'#65747a',flatShading:true}));
  for(let layer=0;layer<3;layer++){
    const ridge=[],z=-570-layer*210;
    const crest=x=>95+layer*24+Math.sin(x*.008+layer*2)*43+Math.sin(x*.018-layer)*26+Math.cos(x*.041+layer)*13+Math.sin(x*.071)*5;
    for(let i=0;i<130;i++){const x=-1200+i*19,n=x+19;ridge.push(x,-130,z,x,crest(x),z,n,crest(n),z,x,-130,z,n,crest(n),z,n,-130,z);}
    const g=geometry(new THREE.BufferGeometry());g.setAttribute('position',new THREE.Float32BufferAttribute(ridge,3));g.computeVertexNormals();scene.add(new THREE.Mesh(g,rockMaterial));
  }
  // Observatory and illuminated armillary ring: the first concrete destination.
  const station=new THREE.Group();station.position.set(35,height(35,-125),-125);scene.add(station);
  const concrete=material(new THREE.MeshLambertMaterial({color:'#87958f',flatShading:true}));
  const dark=material(new THREE.MeshLambertMaterial({color:'#293d45'}));
  function piece(g,m,x,y,z,group=station){const mesh=new THREE.Mesh(geometry(g),m);mesh.position.set(x,y,z);group.add(mesh);return mesh;}
  piece(new THREE.CylinderGeometry(12,16,4,40),concrete,0,1,0);
  piece(new THREE.CylinderGeometry(8,8,10,32),dark,0,8,0);
  piece(new THREE.SphereGeometry(8.1,32,16,0,Math.PI*2,0,Math.PI/2),concrete,0,13,0);
  const glow=material(new THREE.MeshBasicMaterial({color:'#b6e9dd'}));
  const windowBand=piece(new THREE.CylinderGeometry(8.05,8.05,1.1,40,1,true),glow,0,10.5,0);
  const paths=[];
  function lightPath(points,options,parent=station){const path=createGlowPath(points,options);geometry(path.geometry);material(path.material);parent.add(path.mesh);paths.push(path);return path;}
  const orbit=lightPath([circlePath(19)],{closed:true,width:1.55,glow:5,color:'#8befe1',flow:.55});
  const orbit2=lightPath([circlePath(16)],{closed:true,width:1.05,glow:4,color:'#b0d8ff',flow:.35});
  const ring=orbit.mesh,ring2=orbit2.mesh;ring.position.set(0,23,-3);ring.rotation.y=-.45;ring.rotation.z=.15;ring2.position.copy(ring.position);ring2.rotation.y=.9;ring2.rotation.x=.7;
  const axis=lightPath([[new THREE.Vector3(0,-21,0),new THREE.Vector3(0,21,0)]],{width:.85,glow:3,color:'#dcfff0',opacity:.7,flow:.1}).mesh;axis.position.copy(ring.position);axis.rotation.z=.55;
  // A static constellation becomes visible as the camera tilts into night.
  const U=new THREE.Vector3(1,.25,-.1).normalize(),V=new THREE.Vector3(.13,.45,-.88).normalize(),W=new THREE.Vector3().crossVectors(U,V).normalize();
  const gauss=()=>(random()+random()+random()-1.5)*.8,dir=new THREE.Vector3(),hue=new THREE.Color();
  const starTints=['#cfe0ff','#ffffff','#ffe9c9','#bfe8ff','#ffd0e6','#c9fff0'].map(x=>new THREE.Color(x));
  const sp=[],sc=[],ss=[],sph=[];
  for(let i=0;i<5200;i++){
    if(random()<.55){const a=random()*Math.PI*2;dir.copy(U).multiplyScalar(Math.cos(a)).addScaledVector(V,Math.sin(a)).addScaledVector(W,gauss()*.16);}
    else dir.set(random()*2-1,random()*1.1-.1,random()*2-1);
    dir.normalize();if(dir.y<-.08)dir.y=-dir.y;sp.push(dir.x*900,dir.y*900,dir.z*900);
    hue.copy(starTints[Math.floor(random()*starTints.length)]);const b=.55+random()*.45;sc.push(hue.r*b,hue.g*b,hue.b*b);
    ss.push(1.1+Math.pow(random(),7)*7.5);sph.push(random());
  }
  // Dense faint Milky-Way star dust around the star-map view; its own seed keeps every other layout unchanged.
  let dustSeed=97;const dustRandom=()=>(dustSeed=(Math.imul(dustSeed,1664525)+1013904223)>>>0)/4294967296,spread=new THREE.Vector3();
  for(let i=0;i<6000;i++){
    if(dustRandom()<.65){const a=Math.PI/2+dustRandom()*2-1,g=(dustRandom()+dustRandom()+dustRandom()-1.5)*.8;dir.copy(U).multiplyScalar(Math.cos(a)).addScaledVector(V,Math.sin(a)).addScaledVector(W,g*.14);}
    else dir.copy(V).add(spread.set((dustRandom()*2-1)*.9,(dustRandom()*2-1)*.7,(dustRandom()*2-1)*.9));
    dir.normalize();if(dir.y<-.08)dir.y=-dir.y;sp.push(dir.x*900,dir.y*900,dir.z*900);
    hue.copy(starTints[Math.floor(dustRandom()*starTints.length)]);const b=(.55+dustRandom()*.45)*.55;sc.push(hue.r*b,hue.g*b,hue.b*b);
    ss.push(.9+Math.pow(dustRandom(),4)*1.8);sph.push(dustRandom());
  }
  const starsGeo=geometry(new THREE.BufferGeometry());starsGeo.setAttribute('position',new THREE.Float32BufferAttribute(sp,3));starsGeo.setAttribute('tint',new THREE.Float32BufferAttribute(sc,3));starsGeo.setAttribute('size',new THREE.Float32BufferAttribute(ss,1));starsGeo.setAttribute('phase',new THREE.Float32BufferAttribute(sph,1));
  const starsMat=material(new THREE.ShaderMaterial({transparent:true,depthWrite:false,blending:THREE.AdditiveBlending,uniforms:{time:{value:0},opacity:{value:0},scale:{value:1}},
    vertexShader:'attribute vec3 tint;attribute float size;attribute float phase;uniform float time;uniform float opacity;uniform float scale;varying vec3 vColor;varying float vAlpha;varying float vFlare;void main(){gl_Position=projectionMatrix*modelViewMatrix*vec4(position,1.);float tw=.6+.4*sin(time*(.8+phase*2.2)+phase*40.);vColor=tint;vAlpha=opacity*tw;vFlare=smoothstep(3.,7.,size);gl_PointSize=size*scale*(1.+vFlare*2.2)*(.8+.35*tw);}',
    fragmentShader:'varying vec3 vColor;varying float vAlpha;varying float vFlare;void main(){vec2 p=gl_PointCoord-.5;float d=length(p);float glow=exp(-d*d*(30.-vFlare*18.));float core=smoothstep(.12,0.,d);float rays=(exp(-abs(p.x)*90.)*exp(-abs(p.y)*7.)+exp(-abs(p.y)*90.)*exp(-abs(p.x)*7.))*vFlare;float a=(glow+core+rays)*vAlpha;if(a<.004)discard;gl_FragColor=vec4(vColor*(.8+core+rays),a);}'}));
  const stars=new THREE.Points(starsGeo,starsMat);stars.frustumCulled=false;scene.add(stars);
  const glowTex=softTexture([[0,'rgba(255,255,255,1)'],[.18,'rgba(255,255,255,.75)'],[.45,'rgba(255,255,255,.18)'],[1,'rgba(255,255,255,0)']]);
  const atlas=createConstellation(),network=atlas.group;scene.add(network);
  const lin=hex=>{const k=new THREE.Color(hex);return `vec3(${k.r.toFixed(4)},${k.g.toFixed(4)},${k.b.toFixed(4)})`;};
  const skyMat=material(new THREE.ShaderMaterial({side:THREE.BackSide,depthWrite:false,uniforms:{top:{value:new THREE.Color()},bottom:{value:new THREE.Color()},sunTint:{value:new THREE.Color('#ffddb1')},sunAmount:{value:0},night:{value:0},time:{value:0},nebula:{value:null},nebulaReady:{value:0},imageAspect:{value:16/9},viewport:{value:new THREE.Vector2(1,1)},parallax:{value:new THREE.Vector2()}},
    vertexShader:'varying vec3 v; void main(){v=position; gl_Position=projectionMatrix*modelViewMatrix*vec4(position,1.);}',
    fragmentShader:`varying vec3 v;uniform vec3 top,bottom,sunTint;uniform float sunAmount,night,time;
uniform sampler2D nebula;uniform float nebulaReady,imageAspect;uniform vec2 viewport,parallax;
float hash(vec3 p){p=fract(p*.3183099+.1);p*=17.;return fract(p.x*p.y*p.z*(p.x+p.y+p.z));}
float noise(vec3 x){vec3 i=floor(x),f=fract(x);f=f*f*(3.-2.*f);return mix(mix(mix(hash(i),hash(i+vec3(1,0,0)),f.x),mix(hash(i+vec3(0,1,0)),hash(i+vec3(1,1,0)),f.x),f.y),mix(mix(hash(i+vec3(0,0,1)),hash(i+vec3(1,0,1)),f.x),mix(hash(i+vec3(0,1,1)),hash(i+vec3(1,1,1)),f.x),f.y),f.z);}
float fbm(vec3 p){float s=0.,a=.5;for(int i=0;i<5;i++){s+=a*noise(p);p=p*2.07+vec3(1.7,9.2,3.1);a*=.5;}return s;}
void main(){vec3 d=normalize(v);float h=smoothstep(-.1,.7,d.y);vec3 c=mix(bottom,top,h);
c+=bottom*.22*exp(-abs(d.y-.02)*9.);
vec2 q=d.xz/(max(d.y,0.)+.28);float cl=night<.999?smoothstep(.48,.82,fbm(vec3(q*.9,time*.012)))*smoothstep(-.02,.3,d.y)*(1.-night):0.;
c=mix(c,mix(bottom,vec3(1.),.3),cl*.26);
if(night>.001){vec3 w=vec3(${W.x.toFixed(4)},${W.y.toFixed(4)},${W.z.toFixed(4)});
if(nebulaReady>.5){
  vec2 uv=gl_FragCoord.xy/viewport;float aspect=viewport.x/viewport.y;
  vec2 crop=vec2(min(1.,aspect/imageAspect),min(1.,imageAspect/aspect));
  uv=(uv-.5)*crop*.985+.5+parallax*.006;
  c=mix(c,texture2D(nebula,uv).rgb*.92,night);
}else{
vec3 gu=vec3(${U.x.toFixed(4)},${U.y.toFixed(4)},${U.z.toFixed(4)}),gv=vec3(${V.x.toFixed(4)},${V.y.toFixed(4)},${V.z.toFixed(4)});float lon=atan(dot(d,gv),dot(d,gu)),dl=lon-1.3;
float n1=fbm(d*2.4+vec3(0.,0.,time*.004)),n2=fbm(d*5.8+n1*2.2+3.7),n3=fbm(d*14.+n2*2.6+9.1);
float lat=dot(d,w)-.05*sin(lon*2.6+.9)+.09*(lon-1.27)+.02-(n1-.5)*.1;
float wide=exp(-lat*lat*13.),core=exp(-lat*lat*70.),along=exp(-dl*dl/(dl<0.?.5:.12));
vec3 g=mix(${lin('#0a1f6b')}*.25,${lin('#2950c8')}*.55,smoothstep(.3,.8,n2*.6+n1*.55))*(.4+.8*n1);
g+=${lin('#4a86e8')}*pow(smoothstep(.35,.85,n2),2.)*(.35+wide*.9)*.5;
g+=${lin('#5cc8e6')}*pow(1.-abs(n3*2.-1.),5.)*wide*smoothstep(.4,.75,n2)*.55;
g+=${lin('#5a52c8')}*smoothstep(.5,.85,n1)*wide*.15;
g*=1.-core*(.6+.38*along);
float bx=(lon-1.33)/.24,by=(lat+.03)/.065,lum=core*(.3+.75*along)*(.35+.75*smoothstep(.3,.78,n2))*(.7+.5*n3)+exp(-bx*bx-by*by)*(.15+.45*n2)*(.6+.8*n3);
g+=mix(${lin('#cfe3ff')},mix(${lin('#e0904a')},${lin('#fff0d8')},smoothstep(.3,.9,lum)),smoothstep(.2,.7,along))*lum*1.1;
g+=vec3(.85,.9,1.)*pow(n3,6.)*wide*.9;
c=c*mix(1.,.35+.9*n1,night)+g*night;
float dx=(lat-.04)/.085,dz=(lon-1.18)/.45,dust=smoothstep(.38,.55,fbm(d*8.5+n1*1.8+21.)+(n3-.5)*.3)*exp(-dx*dx)*(.25*along+.75*exp(-dz*dz));
c=mix(c,c*vec3(.2,.11,.08),dust*.95*night);c+=${lin('#e0904a')}*dust*(1.-dust)*core*2.2*along*night;
}
float k=floor(time/4.),ft=fract(time/4.);if(ft<.32){vec3 u=vec3(${U.x.toFixed(4)},${U.y.toFixed(4)},${U.z.toFixed(4)}),vv=vec3(${V.x.toFixed(4)},${V.y.toFixed(4)},${V.z.toFixed(4)});
vec3 a=normalize(vv+u*(hash(vec3(k,1.,2.))*1.1-.55)+w*(hash(vec3(k,5.,7.))*.5-.05)),dm=normalize(-u*.8-w*.55);float t=ft/.32;
vec3 head=normalize(a+dm*t*.4),tail=normalize(a+dm*max(0.,t*.4-.14)),pa=d-tail,ba=head-tail;float hh=clamp(dot(pa,ba)/max(dot(ba,ba),1e-6),0.,1.);
c+=vec3(.92,.96,1.)*smoothstep(.003,0.,length(pa-ba*hh))*hh*hh*sin(t*3.1416)*night*1.6;}}
float s=max(0.,dot(d,normalize(vec3(-.26,.16,-1.))));c+=sunTint*(pow(s,5.)*.16+pow(s,40.)*.3+pow(s,300.)*.5)*sunAmount+vec3(1.,.97,.9)*pow(s,2600.)*2.*sunAmount;
gl_FragColor=vec4(c,1.);
#include <tonemapping_fragment>
#include <colorspace_fragment>
}`}));
  const sky=new THREE.Mesh(geometry(new THREE.SphereGeometry(1100,32,20)),skyMat);scene.add(sky);
  const nebulaTexture=new THREE.TextureLoader().load(new URL('./textures/nebula-4k.webp',import.meta.url).href,texture=>{if(!dead){skyMat.uniforms.imageAspect.value=texture.image.width/texture.image.height;skyMat.uniforms.nebulaReady.value=1;host.dataset.nebula='super-resolution-4k';host.dataset.textureSize=`${texture.image.width}x${texture.image.height}`;host.dispatchEvent(new CustomEvent('scene-ready'));}},undefined,()=>{host.dataset.nebula='procedural-fallback';});
  nebulaTexture.colorSpace=THREE.SRGBColorSpace;resources.add(nebulaTexture);skyMat.uniforms.nebula.value=nebulaTexture;
  const positions=[[90,64,175],[25,25,22],[80,48,-62],[-20,45,-160],[-90,105,-225],[12,155,-325]];
  const targets=[[0,15,-150],[30,17,-125],[10,28,-140],[0,108,-300],[0,28,-430],[-55,100,-650]];
  const route=new THREE.CatmullRomCurve3(positions.map(p=>new THREE.Vector3(...p)),false,'catmullrom',.35);
  const gaze=new THREE.CatmullRomCurve3(targets.map(p=>new THREE.Vector3(...p)),false,'catmullrom',.35);
  const palettes=[['#728b9b','#b6c8c8','#98afb4'],['#586d82','#a5b6ba','#829aa3'],['#213449','#7d929e','#667e8d'],['#07154a','#163a8e','#122a62'],['#263c57','#b8a8a7','#718b9e'],['#577e9b','#f2d7a8','#b6b8ad']].map(p=>p.map(x=>new THREE.Color(x)));
  const tmp=new THREE.Vector3(),look=new THREE.Vector3(),color=new THREE.Color(),white=new THREE.Color('#ffffff'),nightTint=new THREE.Color('#3d5272');
  const aim=new THREE.Vector2(),lean=new THREE.Vector2();
  const mistCanvas=document.createElement('canvas');paintMist(mistCanvas);
  const mistTex=new THREE.CanvasTexture(mistCanvas),mists=[];resources.add(mistTex);
  for(let i=0;i<48;i++){
    const x=(random()-.5)*460,z=80-random()*760,w=110+random()*200,s=new THREE.Sprite(material(new THREE.SpriteMaterial({map:mistTex,color:'#e6eeee',transparent:true,opacity:0,depthWrite:false,fog:false})));
    s.scale.set(w,w*(.22+random()*.14),1);s.position.set(x,height(x,z)+5+random()*16,z);s.userData={x,amount:.16+random()*.2,speed:1.5+random()*3,phase:random()*6.28};scene.add(s);mists.push(s);
  }
  const mp=[],mph=[];
  for(let i=0;i<360;i++){route.getPoint(random(),tmp);mp.push(tmp.x+(random()-.5)*140,tmp.y-15+random()*40-random()*25,tmp.z+(random()-.5)*140);mph.push(random());}
  const moteGeo=geometry(new THREE.BufferGeometry());moteGeo.setAttribute('position',new THREE.Float32BufferAttribute(mp,3));moteGeo.setAttribute('phase',new THREE.Float32BufferAttribute(mph,1));
  const warm=new THREE.Color('#ffe2b0'),cool=new THREE.Color('#9ff3ff');
  const moteMat=material(new THREE.ShaderMaterial({transparent:true,depthWrite:false,blending:THREE.AdditiveBlending,uniforms:{time:{value:0},opacity:{value:0},scale:{value:1},tint:{value:warm.clone()}},
    vertexShader:'attribute float phase;uniform float time;uniform float scale;varying float vTw;void main(){vec3 p=position;float t=time*.25+phase*20.;p+=vec3(sin(t*1.3)*3.,sin(t*.9+phase*7.)*2.2,cos(t*1.1)*3.);vec4 mv=modelViewMatrix*vec4(p,1.);gl_Position=projectionMatrix*mv;vTw=.5+.5*sin(time*(1.5+phase*2.)+phase*30.);gl_PointSize=min(46.,scale*(2.+phase*2.5)*(220./max(1.,-mv.z)));}',
    fragmentShader:'uniform vec3 tint;uniform float opacity;varying float vTw;void main(){float d=length(gl_PointCoord-.5);float a=exp(-d*d*22.)*opacity*(.35+.65*vTw);if(a<.004)discard;gl_FragColor=vec4(tint,a);}'}));
  const motes=new THREE.Points(moteGeo,moteMat);motes.frustumCulled=false;scene.add(motes);
  const halo=new THREE.Sprite(material(new THREE.SpriteMaterial({map:glowTex,color:'#bff5e6',transparent:true,opacity:0,depthWrite:false,blending:THREE.AdditiveBlending,fog:false})));halo.scale.set(80,80,1);halo.position.set(0,21,-3);station.add(halo);
  let dead=false,highDetail=false;
  function setDetail(enabled){if(highDetail===enabled)return false;highDetail=enabled;resize();return true;}
  function resize(){const w=Math.max(1,host.clientWidth),h=Math.max(1,host.clientHeight);renderer.setPixelRatio(scenePixelRatio(w,h,devicePixelRatio||1,highDetail));renderer.setSize(w,h,false);camera.aspect=w/h;camera.updateProjectionMatrix();const dpr=renderer.getPixelRatio(),k=dpr*clamp(h/900,.7,1.4);starsMat.uniforms.scale.value=k;moteMat.uniforms.scale.value=k;renderer.getDrawingBufferSize(skyMat.uniforms.viewport.value);paths.forEach(path=>path.resize(w,h,dpr));
    const fit=Math.min(1,camera.aspect/1.5);network.scale.setScalar(fit);network.position.set(0,92*(1-fit),-280*(1-fit));atlas.resize(w,h,dpr);
    host.dataset.quality=highDetail?'native-up-to-4k':'balanced';host.dataset.renderSize=`${renderer.domElement.width}x${renderer.domElement.height}`;
  }
  function pointer(x,y){aim.set(clamp(x,-1,1),clamp(y,-1,1));}
  function render(p,time=0){
    if(dead)return;p=clamp(p,0,5);const a=Math.min(4,Math.floor(p)),f=smooth(p-a);
    camera.position.copy(route.getPoint(p/5,tmp));lean.lerp(aim,.05);camera.position.x+=lean.x*7;camera.position.y-=lean.y*4;
    skyMat.uniforms.parallax.value.copy(lean);
    look.copy(gaze.getPoint(p/5,look));camera.lookAt(look);
    sky.position.copy(camera.position);stars.position.copy(camera.position);skyMat.uniforms.top.value.copy(palettes[a][0]).lerp(palettes[a+1][0],f);skyMat.uniforms.bottom.value.copy(palettes[a][1]).lerp(palettes[a+1][1],f);
    const atmosphere=mistEnvelope(p);
    scene.fog.color.copy(palettes[a][2]).lerp(palettes[a+1][2],f);scene.fog.density=(.0075-.0034*Math.sin(p/5*Math.PI)-.0028*smooth(p-4))*(1+atmosphere*.28);
    const night=Math.max(0,1-Math.abs(p-3));hemi.intensity=2.1-night*1.35;sun.intensity=2.2-night*1.85;
    skyMat.uniforms.sunAmount.value=smooth((p-3.7)/1.3)*1.4;skyMat.uniforms.night.value=night;skyMat.uniforms.time.value=time;
    starsMat.uniforms.opacity.value=smooth(night*1.25);starsMat.uniforms.time.value=time;
    atlas.render(night,time);paths.forEach(path=>path.uniforms.time.value=time);
    groundMaterial.color.copy(white).lerp(nightTint,night*.7);
    waterMaterial.color.copy(skyMat.uniforms.bottom.value).lerp(white,.18);
    color.copy(scene.fog.color).lerp(white,.35);
    for(const s of mists){const u=s.userData;s.position.x=u.x+Math.sin(time*.018*u.speed+u.phase)*32;const dist=s.position.distanceTo(camera.position);s.material.color.copy(color);s.material.opacity=u.amount*(1+atmosphere*2.2)*(1-night)*smooth((dist-20)/75)*(1-smooth((dist-650)/200));s.visible=s.material.opacity>.001;}
    moteMat.uniforms.time.value=time;moteMat.uniforms.opacity.value=.55+night*.25;moteMat.uniforms.tint.value.copy(warm).lerp(cool,night);
    halo.material.opacity=(.18+.42*Math.max(0,1-Math.abs(p-2))+night*.2)*(.85+.15*Math.sin(time*1.6));
    ring.rotation.z=.15+time*.05;ring2.rotation.y=.9+time*.08;
    renderer.render(scene,camera);host.dataset.drawCalls=renderer.info.render.calls;host.dataset.triangles=renderer.info.render.triangles;
  }
  const lost=e=>{e.preventDefault();host.dispatchEvent(new CustomEvent('scene-lost'));};renderer.domElement.addEventListener('webglcontextlost',lost);
  function dispose(){if(dead)return;dead=true;renderer.domElement.removeEventListener('webglcontextlost',lost);atlas.dispose();resources.forEach(r=>r.dispose());renderer.dispose();renderer.forceContextLoss();renderer.domElement.remove();}
  resize();return {resize,setDetail,render,pointer,dispose,renderer,canvas:renderer.domElement};
}
