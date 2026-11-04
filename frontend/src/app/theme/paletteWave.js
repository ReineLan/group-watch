import {revealTimeForRadius} from './reveal.js'

// A whole control/card fades as the expanding circle reaches its centre.
// The 260ms fade straddles that crossing; no glyph/button is cut in half.
export function paletteDelay(rect,scene,viewport={width:globalThis.innerWidth,height:globalThis.innerHeight}){
  // Long archive tables can extend several screens below a phone. Time the
  // visible surface, rather than its offscreen document centre.
  const centre=(start,length,limit)=>Number.isFinite(limit)
    ?(Math.max(0,Math.min(limit,start))+Math.max(0,Math.min(limit,start+length)))/2
    :start+length/2
  const distance=Math.hypot(centre(rect.left,rect.width,viewport.width)-scene.point.x,centre(rect.top,rect.height,viewport.height)-scene.point.y)
  return Math.max(0,revealTimeForRadius(distance/Math.max(1,scene.radius))-130)
}
export function paletteWave({setTimer=setTimeout,clearTimer=clearTimeout}={}){
  let sequence=0
  const latest=new Map(),pending=new Map()
  return {
    run(regions,scene,colors,{immediate=false}={}){
      const order=++sequence
      for(const region of regions){
        if(pending.has(region)){clearTimer(pending.get(region));pending.delete(region)}
        // Newest intent owns the pending change, even before its circle arrives.
        latest.set(region,order)
        const apply=()=>{if(latest.get(region)!==order)return;region.sync(colors)}
        const delay=immediate?0:paletteDelay(region.rect(),scene)
        if(!delay){apply();continue}
        const timer=setTimer(()=>{if(pending.get(region)===timer)pending.delete(region);apply()},delay)
        pending.set(region,timer)
      }
    },
    cancel(){for(const timer of pending.values())clearTimer(timer);pending.clear();latest.clear();sequence++},
  }
}
