import {scenePreloader} from './preload.js'
import {sharedVideos} from './sharedVideos.js'

// Resource policy has no knowledge of circles or rendered scene instances.
export function themeResources({assets,resolveId=id=>id,preload=scenePreloader(),videos=sharedVideos()}={}){
  const states=new Map(),pending=new Map()
  function prepare(id){
    const url=assets[resolveId(id)].image
    if(pending.has(url))return pending.get(url)
    states.set(url,'loading')
    const task=Promise.resolve().then(()=>preload(url)).catch(()=>false).then(ready=>{
      states.set(url,ready?'ready':'failed');return ready
    }).finally(()=>pending.delete(url))
    pending.set(url,task);return task
  }
  return {prepare,videos,state:id=>states.get(assets[resolveId(id)].image)||'idle',
    prepareThumbnails:()=>Promise.all(Object.values(assets).map(asset=>preload(asset.thumb)))}
}
