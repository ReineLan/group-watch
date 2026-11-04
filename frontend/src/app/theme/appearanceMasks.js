// Registered properties are reused after recycling, bounded by concurrency.
export function appearanceMasks(register){
  const slots=new Map(),registered=new Set()
  function sync(scenes){
    const active=new Set(scenes.filter(s=>s.ring).map(s=>s.key))
    for(const key of slots.keys())if(!active.has(key))slots.delete(key)
    for(const key of active){
      if(slots.has(key))continue
      let slot=0;while([...slots.values()].includes(slot))slot++
      if(!registered.has(slot)){register(`--appearance-radius-${slot}`);registered.add(slot)}
      slots.set(key,slot)
    }
  }
  const property=key=>`--appearance-radius-${slots.get(key)}`
  function style(scene,index,scenes){
    const gradient=(ring,include)=>{
      const radius=`var(${property(ring.key)})`,{x,y}=ring.point
      return `radial-gradient(circle at ${x}px ${y}px, ${include?'black':'transparent'} 0 ${radius}, ${include?'transparent':'black'} calc(${radius} + .5px))`
    }
    const images=[]
    if(scene.ring)images.push(gradient(scene,true))
    for(const newer of scenes.slice(index+1))if(newer.ring)images.push(gradient(newer,false))
    return {maskImage:images.length?images.join(','):'none',maskComposite:'intersect'}
  }
  return {sync,property,style}
}
