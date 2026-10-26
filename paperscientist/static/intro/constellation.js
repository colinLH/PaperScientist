import * as THREE from './vendor/three.module.min.js';
import {createGlowPath} from './glow-path.js';

// Sparse research atlas: disconnected star groups and
// screen-space optical markers. All lines/markers remain vector geometry at 4K.
export function createConstellation(){
  const group=new THREE.Group(),float=new THREE.Group(),resources=[],paths=[];group.add(float);
  // Small disconnected constellations across the view, leaving a quiet reading area.
  const coords=[[-.88,.62],[-.68,.83],[-.36,.65],[-.08,.82],[.22,.56],[.62,.78],[.86,.48],[.68,.18],
    [.90,-.10],[.72,-.50],[.44,-.72],[.14,-.46],[-.14,-.73],[-.45,-.50],[-.78,-.65],[-.90,-.30],[-.45,.22],[.30,-.02]];
  const points=coords.map(([x,y])=>new THREE.Vector3(x,y,-280));
  const main=[[0,1],[1,2],[3,4],[5,6],[6,7],[8,9],[10,11],[12,13],[14,15],[2,16],[17,11]];
  group.userData={nodes:coords.length,edges:main.length};
  function path(lines,opts){const p=createGlowPath(lines,opts);float.add(p.mesh);resources.push(p.geometry,p.material);paths.push(p);return p;}
  const routes=path(main.map(([a,b])=>[points[a],points[b]]),{color:'#b3d9eb',width:.7,glow:1.8,flow:.35});
  const geo=new THREE.BufferGeometry().setFromPoints(points);
  geo.setAttribute('importance',new THREE.Float32BufferAttribute(coords.map((_,i)=>[1,6,11].includes(i)?.55:.12),1));
  const uniforms={opacity:{value:0},time:{value:0},scale:{value:1}};
  const mat=new THREE.ShaderMaterial({uniforms,transparent:true,depthTest:false,depthWrite:false,blending:THREE.AdditiveBlending,
    vertexShader:`attribute float importance;uniform float scale;varying float rank;void main(){rank=importance;gl_Position=projectionMatrix*modelViewMatrix*vec4(position,1.);gl_PointSize=(15.+importance*32.)*scale;}`,
    fragmentShader:`uniform float opacity,time;varying float rank;
void main(){vec2 p=(gl_PointCoord-.5)*2.;float r=length(p),aa=max(fwidth(r),.012);
float core=1.-smoothstep(.065,.065+aa,r);float halo=exp(-r*r*19.)*.5;
float diamond=1.-smoothstep(.12,.12+aa,abs(p.x)+abs(p.y));
float rays=(exp(-abs(p.x)*100.)*exp(-abs(p.y)*7.)+exp(-abs(p.y)*100.)*exp(-abs(p.x)*7.))*rank*.65;
float ring=(1.-smoothstep(.016,.016+aa,abs(r-.52)))*rank*.42;
float a=(core+halo+diamond*.4+rays+ring)*opacity*(.92+.08*sin(time*1.4+rank*8.));
if(a<.004)discard;gl_FragColor=vec4(mix(vec3(.35,.72,1.),vec3(1.),min(1.,core+diamond+rays)),a);
#include <colorspace_fragment>
}`});
  const nodes=new THREE.Points(geo,mat);nodes.frustumCulled=false;float.add(nodes);resources.push(geo,mat);
  // Visible travelling signals add a second rhythm to the slowly floating map.
  const signalGeo=new THREE.BufferGeometry(),signals=new Float32Array(main.length*3);
  signalGeo.setAttribute('position',new THREE.BufferAttribute(signals,3).setUsage(THREE.DynamicDrawUsage));
  const signalMat=mat.clone();signalMat.uniforms=THREE.UniformsUtils.clone(uniforms);
  signalGeo.setAttribute('importance',new THREE.Float32BufferAttribute(main.map(()=>.4),1));
  const signalPoints=new THREE.Points(signalGeo,signalMat);signalPoints.frustumCulled=false;float.add(signalPoints);resources.push(signalGeo,signalMat);
  return {group,resize(w,h,dpr){paths.forEach(p=>p.resize(w,h,dpr));uniforms.scale.value=dpr*Math.min(1.4,Math.max(.7,h/900));signalMat.uniforms.scale.value=uniforms.scale.value*.45;},
    render(night,time){group.visible=night>.001;if(!group.visible)return;
      float.position.set(Math.sin(time*.13)*.006,Math.sin(time*.19)*.007,0);
      float.rotation.z=Math.sin(time*.12)*.003;
      main.forEach(([a,b],i)=>{const t=(time*(.09+i%3*.012)+i*.173)%1;signals[i*3]=points[a].x+(points[b].x-points[a].x)*t;signals[i*3+1]=points[a].y+(points[b].y-points[a].y)*t;signals[i*3+2]=points[a].z;});signalGeo.attributes.position.needsUpdate=true;
      signalMat.uniforms.opacity.value=night*.9;signalMat.uniforms.time.value=time;
      routes.uniforms.opacity.value=night*.52;paths.forEach(p=>p.uniforms.time.value=time*1.6);uniforms.opacity.value=night;uniforms.time.value=time;},
    dispose(){resources.forEach(r=>r.dispose());}};
}
