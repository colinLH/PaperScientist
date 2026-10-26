import * as THREE from './vendor/three.module.min.js';
import {createGlowPath,circlePath} from './glow-path.js';

// Original research atlas: four navigation hubs, triangulated branches and
// screen-space optical markers. All lines/markers remain vector geometry at 4K.
export function createConstellation(){
  const group=new THREE.Group(),resources=[],paths=[];
  const coords=[[-49,7],[-38,23],[-23,28],[-24,5],[-42,-13],[-26,-25],[-6,-17],[-5,10],
    [9,28],[22,12],[43,23],[51,1],[37,-18],[14,-24],[19,-5],[3,-1]];
  const points=coords.map(([x,y])=>new THREE.Vector3(x+30,y+110,-280));
  const main=[[0,1],[1,2],[2,7],[7,8],[8,9],[9,10],[10,11],[11,12],[12,13],[13,6],[6,5],[5,4],[4,0],[3,7],[7,9],[9,14],[14,13],[3,4],[3,5],[7,15],[15,6]];
  const secondary=[[0,3],[1,3],[2,3],[3,6],[6,14],[7,14],[9,11],[11,14],[12,14],[14,15]];
  function path(lines,opts){const p=createGlowPath(lines,opts);group.add(p.mesh);resources.push(p.geometry,p.material);paths.push(p);return p;}
  const routes=path(main.map(([a,b])=>[points[a],points[b]]),{color:'#8cdeff',width:1.45,glow:5,flow:.65});
  const links=path(secondary.map(([a,b])=>[points[a],points[b]]),{color:'#779de8',width:.65,glow:2.2,flow:.16});
  const rings=[];
  for(const index of [3,7,9,14]){
    const r=index===7?3.2:2.4;
    const circle=circlePath(r,96).map(p=>p.add(points[index]));rings.push([...circle,circle[0]]);
    // Four widely spaced ticks give the hubs a navigational instrument motif.
    for(let k=0;k<4;k++){const a=k*Math.PI/2;const line=[r+1,r+1.7].map(d=>points[index].clone().add(new THREE.Vector3(Math.cos(a)*d,Math.sin(a)*d,0)));rings.push(line);}
  }
  const orbit=path(rings,{color:'#badfff',width:.75,glow:2.2,flow:.25});
  const geo=new THREE.BufferGeometry().setFromPoints(points);
  geo.setAttribute('importance',new THREE.Float32BufferAttribute(coords.map((_,i)=>i===7?1:[3,9,14].includes(i)?.72:.24),1));
  const uniforms={opacity:{value:0},time:{value:0},scale:{value:1}};
  const mat=new THREE.ShaderMaterial({uniforms,transparent:true,depthTest:false,depthWrite:false,blending:THREE.AdditiveBlending,
    vertexShader:`attribute float importance;uniform float scale;varying float rank;void main(){rank=importance;gl_Position=projectionMatrix*modelViewMatrix*vec4(position,1.);gl_PointSize=(19.+importance*42.)*scale;}`,
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
  const nodes=new THREE.Points(geo,mat);nodes.frustumCulled=false;group.add(nodes);resources.push(geo,mat);
  return {group,resize(w,h,dpr){paths.forEach(p=>p.resize(w,h,dpr));uniforms.scale.value=dpr*Math.min(1.4,Math.max(.7,h/900));},
    render(night,time){group.visible=night>.001;routes.uniforms.opacity.value=night*.85;links.uniforms.opacity.value=night*.38;orbit.uniforms.opacity.value=night*.65;paths.forEach(p=>p.uniforms.time.value=time);uniforms.opacity.value=night;uniforms.time.value=time;},
    dispose(){resources.forEach(r=>r.dispose());}};
}
