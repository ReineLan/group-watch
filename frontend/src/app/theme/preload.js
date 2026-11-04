// Share and retain decoded images. Selection may use a thumbnail meanwhile.
export function scenePreloader(createImage=()=>new Image()) {
  const decoded=new Map(),pending=new Map()
  return url=>{
    if(decoded.has(url))return Promise.resolve(true)
    if(pending.has(url))return pending.get(url)
    const image=createImage();image.decoding='async';image.src=url
    const ready=image.decode().then(()=>{decoded.set(url,image);return true}).catch(()=>false).finally(()=>pending.delete(url))
    pending.set(url,ready)
    return ready
  }
}
