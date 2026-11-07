// Pure geometry kept separate from animation and DOM for deterministic verification.
export function pointerPosition(x,y,width,height) {
  const clamp=value=>Math.max(-1,Math.min(1,value))
  return {x:clamp((x/Math.max(width,1)-.5)*2),y:clamp((y/Math.max(height,1)-.5)*2)}
}

// Write only the two moving groups in each scene. Inherited custom properties
// on the stage invalidated hundreds of descendants during overlapping reveals.
export function positionSceneLayers(stage,{x,y}) {
  for(const layer of stage?.querySelectorAll('.scene-media,.scene-beam,.scene-petals,[data-depth]')||[]) {
    const depth=Number(layer.dataset?.depth)||(layer.classList.contains('scene-media')?7:layer.classList.contains('scene-beam')?56:46)
    layer.style.transform=`translate3d(${(-x*depth).toFixed(4)}px,${(-y*depth).toFixed(4)}px,0)`
  }
}
