import * as THREE from './vendor/three.module.min.js';

// Screen-space ribbons: unlike GL_LINES or sub-pixel tubes, the luminous core
// keeps its width as the camera moves. Analytic AA works at the capped DPR too.
export function createGlowPath(paths,{color='#a5e9f4',width=1.25,glow=3.5,opacity=1,flow=.15,closed=false}={}){
  const positions=[],previous=[],next=[],sides=[],distances=[],indices=[];
  for(const path of paths){
    const base=positions.length/3;let distance=0;
    const points=closed?[...path,path[0]]:path;
    for(let i=0;i<points.length;i++){
      if(i)distance+=points[i].distanceTo(points[i-1]);
      const before=points[i-1]|| (closed?path.at(-1):points[0]);
      const after=points[i+1]|| (closed?path[1]:points.at(-1));
      for(const side of [-1,1]){positions.push(...points[i]);previous.push(...before);next.push(...after);sides.push(side);distances.push(distance);}
      if(i<points.length-1){const a=base+i*2;indices.push(a,a+1,a+2,a+2,a+1,a+3);}
    }
  }
  const geometry=new THREE.BufferGeometry();
  for(const [name,data,size] of [['position',positions,3],['previous',previous,3],['next',next,3],['side',sides,1],['distance',distances,1]])geometry.setAttribute(name,new THREE.Float32BufferAttribute(data,size));
  geometry.setIndex(indices);
  const uniforms={viewport:{value:new THREE.Vector2(1,1)},pixelRatio:{value:1},width:{value:width},halo:{value:glow},tint:{value:new THREE.Color(color)},opacity:{value:opacity},time:{value:0},flow:{value:flow}};
  const material=new THREE.ShaderMaterial({uniforms,transparent:true,depthWrite:false,blending:THREE.AdditiveBlending,side:THREE.DoubleSide,
    vertexShader:`attribute vec3 previous,next;attribute float side,distance;
uniform vec2 viewport;uniform float pixelRatio,width,halo;varying float across,along;
void main(){
  vec4 p=projectionMatrix*modelViewMatrix*vec4(position,1.);
  vec4 a=projectionMatrix*modelViewMatrix*vec4(previous,1.);
  vec4 b=projectionMatrix*modelViewMatrix*vec4(next,1.);
  vec2 delta=(b.xy/max(b.w,.01)-a.xy/max(a.w,.01))*viewport;
  vec2 tangent=delta/max(length(delta),.00001),normal=vec2(-tangent.y,tangent.x);
  float radius=width*.5+halo;
  p.xy+=normal*side*radius*pixelRatio*2./viewport*p.w;
  gl_Position=p;across=side*radius;along=distance;
}`,
    fragmentShader:`uniform vec3 tint;uniform float width,halo,opacity,time,flow;varying float across,along;
void main(){float d=abs(across),aa=max(fwidth(across),.35);
  float core=1.-smoothstep(width*.5-aa*.5,width*.5+aa*.5,d);
  float glow=exp(-pow(d/max(halo*.42,.01),2.))*.24;
  float pulse=pow(.5+.5*cos(along*.16-time*.8),12.)*flow;
  float alpha=(core*.72+glow)*(1.+pulse)*opacity;
  if(alpha<.002)discard;
  gl_FragColor=vec4(mix(tint,vec3(1.),core*.4),alpha);
  #include <colorspace_fragment>
}`});
  const mesh=new THREE.Mesh(geometry,material);mesh.frustumCulled=false;
  return {mesh,geometry,material,uniforms,resize(w,h,dpr){uniforms.viewport.value.set(w*dpr,h*dpr);uniforms.pixelRatio.value=dpr;}};
}

export function circlePath(radius,segments=256){return Array.from({length:segments},(_,i)=>{const a=i/segments*Math.PI*2;return new THREE.Vector3(Math.cos(a)*radius,Math.sin(a)*radius,0);});}
