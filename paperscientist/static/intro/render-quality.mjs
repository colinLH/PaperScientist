// Native display pixels (up to UHD) for the settled star map. Travelling scenes
// retain their original small buffer; never render 4K just to downscale to 720p.
export function scenePixelRatio(width,height,dpr=1,detail=false){
  const pixels=Math.max(1,width)*Math.max(1,height);
  return Math.min(Math.max(.1,dpr),detail?2:1.25,Math.sqrt((detail?3840*2160:1400000)/pixels));
}
