// Official project-page media. These remain on their authors' servers; no
// third-party recordings, analytics scripts or website bundles are copied.
export const papers=[
  {name:'Nerfies',title:'Deformable Neural Radiance Fields',venue:'ICCV 2021',url:'https://nerfies.github.io/',video:'https://nerfies.github.io/static/videos/teaser.mp4',poster:'https://nerfies.github.io/static/images/interpolate_start.jpg'},
  {name:'HyperNeRF',title:'A Higher-Dimensional Representation',venue:'SIGGRAPH Asia 2021',url:'https://hypernerf.github.io/',video:'https://hypernerf.github.io/static/videos/espresso_rgb.mp4',poster:'https://hypernerf.github.io/static/images/thumbnail.png'},
  {name:'DreamFusion',title:'Text-to-3D using 2D Diffusion',venue:'ICLR 2023',url:'https://dreamfusion3d.github.io/',video:'https://dreamfusion-cdn.ajayj.com/sept28/shaded_3x3_smoothstep.mp4',poster:'https://dreamfusion3d.github.io/assets/images/dreamfusion_samples.png'},
  {name:'Zip-NeRF',title:'Anti-Aliased Grid-Based Neural Radiance Fields',venue:'ICCV 2023',url:'https://jonbarron.info/zipnerf/',video:'https://jonbarron.info/zipnerf/img/teaser.mp4',poster:'https://jonbarron.info/images/zipnerf.jpg'},
  {name:'Mip-NeRF 360',title:'Unbounded Anti-Aliased Neural Radiance Fields',venue:'CVPR 2022',url:'https://jonbarron.info/mipnerf360/',video:'https://jonbarron.info/mipnerf360/img/gardenvase_720.mp4',poster:'https://jonbarron.info/mipnerf360/img/gardenvase.jpg'},
  {name:'Ref-NeRF',title:'Structured View-Dependent Appearance',venue:'CVPR 2022',url:'https://dorverbin.github.io/refnerf/',video:'https://dorverbin.github.io/refnerf/video/materials_circle_mipnerf_ours.mp4',poster:'https://dorverbin.github.io/refnerf/img/refnerf_titlecard.jpg'},
  {"name": "3D Gaussian Splatting", "title": "Real-Time Radiance Field Rendering", "venue": "SIGGRAPH 2023", "url": "https://repo-sam.inria.fr/fungraph/3d-gaussian-splatting/", "video": "https://repo-sam.inria.fr/fungraph/3d-gaussian-splatting/content/videos/bicycle.mp4", "poster": "https://repo-sam.inria.fr/fungraph/3d-gaussian-splatting/content/images/comparisons/ours_bicycle.png"},
  {"name": "SMERF", "title": "Real-Time Large-Scene Exploration", "venue": "实时场景 · 2023", "url": "https://smerf-3d.github.io/", "video": "https://storage.googleapis.com/realtime-nerf-360/smerf/videos/mildenhall%20desktop.mp4", "poster": "https://smerf-3d.github.io/assets/img/merf/scene_preview/berlin_v2.png"},
  {"name": "ReconFusion", "title": "3D Reconstruction with Diffusion Priors", "venue": "CVPR 2024", "url": "https://reconfusion.github.io/", "video": "https://reconfusion.github.io/videos/teaser/wipe_4.mp4", "poster": "https://reconfusion.github.io/thumbnails/llff_fern_thumbnail.jpg"},
  {"name": "CAT4D", "title": "Create Anything in 4D", "venue": "CVPR 2025", "url": "https://cat-4d.github.io/", "video": "https://cat-4d.github.io/videos/teaser_crf28.mp4", "poster": "https://cat-4d.github.io/img/teaser_frame.jpg"},
  {"name": "DreamGaussian", "title": "Generative Gaussian Splatting", "venue": "ICLR 2024 · Oral", "url": "https://dreamgaussian.github.io/", "video": "https://dreamgaussian.github.io/videos/image1.mp4", "poster": "https://dreamgaussian.github.io/meshes/toy.jpg"},
  {"name": "Diffusion Policy", "title": "Visuomotor Policy Learning via Action Diffusion", "venue": "RSS 2023", "url": "https://diffusion-policy.cs.columbia.edu/", "video": "https://diffusion-policy.cs.columbia.edu/videos/highlight_mug.mp4", "poster": "https://diffusion-policy.cs.columbia.edu/images/teaser.svg"}
];

// At most one live decoder per rail. Epochs prevent late play() fulfillment
// from restarting a preview after a reversal, tab hide, or navigation away.
export function createPreviewPlayback(items){
  const active=new Set();let disposed=false;
  for(const item of items){
    item.epoch=0;item.failed=false;item.video.muted=true;item.video.loop=true;item.video.playsInline=true;item.video.preload='none';item.video.disableRemotePlayback=true;
    item.video.onplaying=()=>{if(disposed||!active.has(item.index)){item.video.pause();return;}item.element.dataset.media='playing';};
    item.video.onerror=()=>{if(!active.has(item.index))return;item.failed=true;item.element.dataset.media='unavailable';};
  }
  function stop(item){item.epoch++;item.video.pause();item.video.removeAttribute('src');item.video.load();item.element.dataset.media=item.failed?'unavailable':'poster';}
  function sync(indices){
    if(disposed)return;
    const wanted=new Set(indices.slice(0,2));
    for(const index of [...active])if(!wanted.has(index)){active.delete(index);stop(items[index]);}
    for(const index of wanted){
      const item=items[index];if(!item||active.has(index)||item.failed)continue;
      active.add(index);item.element.dataset.media='loading';item.video.src=item.source;const epoch=++item.epoch;
      Promise.resolve(item.video.play()).then(()=>{if(disposed||!active.has(index))item.video.pause();}).catch(()=>{if(item.epoch===epoch&&active.has(index)){item.element.dataset.media='paused';}});
    }
  }
  return {sync,get active(){return [...active];},retry(){sync([]);for(const item of items)item.failed=false;},dispose(){if(disposed)return;sync([]);disposed=true;for(const item of items)item.video.onplaying=item.video.onerror=null;}};
}
