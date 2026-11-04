// Renderer adapters register targets; neither the controller nor driver needs
// to know which visual surface they represent.
export function revealTargets(){
  const entries=new Map()
  return {
    register(key,name,target){
      if(!target?.node){const group=entries.get(key);group?.delete(name);if(!group?.size)entries.delete(key);return}
      if(!entries.has(key))entries.set(key,new Map())
      entries.get(key).set(name,target)
    },
    forScene(scene){
      const targets=[...(entries.get(scene.key)?.values()||[])].sort((a,b)=>Number(!!b.primary)-Number(!!a.primary))
      for(const target of targets)target.prepare?.(scene,target.node)
      return targets.map(target=>target.property?target:target.node)
    },
  }
}

export function positionLocalReveal(scene,node){
  if(!scene.ring)return
  const rect=node.getBoundingClientRect()
  node.style.setProperty('--reveal-center-x',`${scene.point.x-rect.left}px`)
  node.style.setProperty('--reveal-center-y',`${scene.point.y-rect.top}px`)
}

export function revealClip(scene,{local=false}={}){
  if(!scene.ring)return {clipPath:'none'}
  const x=local?'var(--reveal-center-x)':`${scene.point.x}px`,y=local?'var(--reveal-center-y)':`${scene.point.y}px`
  if(scene.mask){
    const mask=`radial-gradient(circle at ${x} ${y}, black 0 var(--theme-reveal-radius), transparent calc(var(--theme-reveal-radius) + 1px))`
    return {clipPath:'none',maskImage:mask,WebkitMaskImage:mask}
  }
  return {clipPath:`circle(var(--theme-reveal-radius) at ${x} ${y})`}
}
