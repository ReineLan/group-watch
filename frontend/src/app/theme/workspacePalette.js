// All colors on a surface resolve from the same progress value in one frame.
export const workspaceColors=['ink','ink-2','muted','subtle','faint','accent','accent-strong','accent-2','highlight','on-accent','surface','surface-2','surface-3','surface-4','line','line-1','line-2','line-3','glass-edge','panel','sidebar','shadow','scrim','warn','warn-soft','warn-line','danger','danger-soft','danger-line','info']
export function paletteClock({request=callback=>requestAnimationFrame(callback),cancel=id=>cancelAnimationFrame(id),now=()=>performance.now()}={}){
  const jobs=new Map()
  let frame=null
  function tick(time){
    frame=null
    for(const [key,job] of jobs){
      const progress=Math.max(0,Math.min(1,(time-job.start)/260))
      if(progress===1)jobs.delete(key)
      job.apply(1-(1-progress)**3)
    }
    if(jobs.size)frame=request(tick)
  }
  return {
    start(key,apply){jobs.set(key,{start:now(),apply});if(frame===null)frame=request(tick)},
    stop(key){jobs.delete(key);if(!jobs.size&&frame!==null){cancel(frame);frame=null}},
  }
}
const clock=paletteClock()
export function paletteColors(source=document.documentElement,read=getComputedStyle){
  const style=read(source)
  return Object.fromEntries(workspaceColors.map(name=>[`--${name}`,style.getPropertyValue(`--${name}`).trim()]))
}
export function workspacePalette(node,{source=document.documentElement,read=getComputedStyle,timeline=clock,reduced=()=>globalThis.matchMedia?.('(prefers-reduced-motion: reduce)').matches}={}){
  let targetColors,disposed=false
  const original=new Map([...workspaceColors.map(name=>`--${name}`),'--palette-progress','transition-property'].map(name=>[name,{value:node.style.getPropertyValue(name),priority:node.style.getPropertyPriority(name)}]))
  const originalMarker=node.hasAttribute('data-ui-palette')
  node.setAttribute('data-ui-palette','')
  const write=colors=>{for(const [token,value] of Object.entries(colors))node.style.setProperty(token,value)}
  // Freeze the initial palette before root theme changes. No inherited proxies.
  targetColors=paletteColors(source,read)
  write(targetColors)
  node.style.transitionProperty='transform,opacity'
  function sync(colors=paletteColors(source,read)){
    if(disposed)return
    // Scene promotion must not restart the same in-flight color change.
    if(workspaceColors.every(name=>targetColors[`--${name}`]===colors[`--${name}`]))return
    targetColors={...colors}
    const from=paletteColors(node,read)
    timeline.stop(node)
    if(reduced()||workspaceColors.every(name=>from[`--${name}`]===colors[`--${name}`])){
      write(colors);node.style.removeProperty('--palette-progress');node.removeAttribute('data-palette-animating');return
    }
    node.style.setProperty('--palette-progress','0%')
    write(Object.fromEntries(workspaceColors.map(name=>{
      const key=`--${name}`
      return [key,`color-mix(in srgb, ${from[key]} calc(100% - var(--palette-progress)), ${colors[key]})`]
    })))
    node.setAttribute('data-palette-animating','')
    timeline.start(node,progress=>{
      if(progress===1){write(colors);node.style.removeProperty('--palette-progress');node.removeAttribute('data-palette-animating')}
      else node.style.setProperty('--palette-progress',`${progress*100}%`)
    })
  }
  function dispose({release=false}={}){
    disposed=true;timeline.stop(node);node.removeAttribute('data-palette-animating')
    if(release){
      for(const [name,{value,priority}] of original){if(value)node.style.setProperty(name,value,priority);else node.style.removeProperty(name)}
      if(!originalMarker)node.removeAttribute('data-ui-palette')
    }
  }
  return {sync,dispose}
}
