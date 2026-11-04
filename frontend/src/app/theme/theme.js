import {nextTick,ref,shallowRef} from 'vue'
import {resolveTheme,storageKey} from './themes.js'
import {sceneAssets} from './assets.js'
import {latestSelection} from './selection.js'
import {themeResources} from './resources.js'
import {sceneTransitions} from './sceneTransitions.js'
import {installThemeDiagnostics} from './diagnostics.js'
import {startupExperiment} from './startupExperiment.js'
import {selectionQueue} from './selectionQueue.js'
import {revealDriver} from './revealDriver.js'
import {revealTargets} from './revealTargets.js'

import {compactSceneQuery,reducedSceneQuery,useStillScene} from './scenePolicy.js'
const compactScene=matchMedia(compactSceneQuery),reducedScene=matchMedia(reducedSceneQuery)
export const staticScene=ref(useStillScene(compactScene,reducedScene))
function syncScenePolicy(){staticScene.value=useStillScene(compactScene,reducedScene);document.documentElement.toggleAttribute('data-scene-static',staticScene.value)}
syncScenePolicy()
compactScene.addEventListener('change',syncScenePolicy);reducedScene.addEventListener('change',syncScenePolicy)

function stored(){try{return localStorage.getItem(storageKey)}catch{return null}}
function apply(id){
  document.documentElement.dataset.theme=id
  document.documentElement.style.setProperty('--scene-image',`url(${sceneAssets[id].image})`)
  document.querySelector('meta[name="theme-color"]')?.setAttribute('content',resolveTheme(id).meta)
  try{localStorage.setItem(storageKey,id)}catch{}
}
const startupControl=startupExperiment(location.search)
export const theme=ref(resolveTheme(startupControl||new URLSearchParams(location.search).get('theme-debug')==='cold-double'?'chunxi':stored()).id)
export const sceneVideoEnabled=startupControl?.videoEnabled!==false
export const resources=themeResources({assets:sceneAssets,resolveId:id=>resolveTheme(id).id})
export const scenes=shallowRef([])
export const uiAppearancePrototype=new URLSearchParams(location.search).get('theme-debug')==='p3-ui'
export const uiAppearanceEnabled=!new URLSearchParams(location.search).has('theme-debug')||uiAppearancePrototype||(new URLSearchParams(location.search).get('theme-debug')==='mobile'&&new URLSearchParams(location.search).get('appearance')!=='off')
const targets=revealTargets()
export const registerRevealTarget=targets.register
export function registerSceneNode(key,node){targets.register(key,'background',{node,primary:true})}
export function registerSceneLifecycle(key,kind){diagnostics?.sceneLifecycle?.(key,kind)}
apply(theme.value)
const diagnostics=installThemeDiagnostics({selectTheme:setTheme,prepareImages:ids=>Promise.all(ids.map(prepareThemeImage)),resetTheme:async id=>{scheduledSelection?.cancel();theme.value=id;apply(id);reveal.cancel(id);await nextTick()},pause:progress=>reveal.pause(progress),resume:()=>reveal.resume()})

const reveal=sceneTransitions({
  initialTheme:theme.value,publish:value=>scenes.value=value,flush:nextTick,
  driver:revealDriver({targetsFor:targets.forScene}),
  observe:diagnostics?.sceneEvent,
  changing:value=>{if(value)document.documentElement.dataset.themeChanging='';else delete document.documentElement.dataset.themeChanging},
})
let origin
function startSelection(id,point,diagnostic,onStarted){
  const commit=()=>{theme.value=id;apply(id)}
  return reveal.run(id,commit,point,{width:innerWidth,height:innerHeight,diagnostic,onStarted,reduced:document.hidden||!Element.prototype.animate||matchMedia('(prefers-reduced-motion: reduce)').matches})
}
const select=latestSelection(()=>theme.value,prepareTheme,id=>startSelection(id,origin,diagnostics?.revealOptions()))
const compactQueueCapacity=compactScene.matches?3:5
const scheduledSelection=(!diagnostics||diagnostics.queueOptions)?selectionQueue({
  ...(diagnostics?.queueOptions||{interval:260,capacity:compactQueueCapacity}),observe:diagnostics?.queueEvent,
  run:(request,onStarted)=>{
    if(request.id===theme.value)return
    prepareTheme(request.id).catch(()=>{})
    return startSelection(request.id,request.point,request.diagnostic,onStarted)
  },
}):null
function cancelSelection(){scheduledSelection?.cancel();reveal.cancel()}
document.addEventListener('visibilitychange',()=>{if(document.hidden)cancelSelection()})
window.addEventListener('resize',cancelSelection)
window.addEventListener('hashchange',cancelSelection)
window.addEventListener('scroll',cancelSelection,{passive:true})
document.addEventListener('workspace-locked',cancelSelection)
// Hover/focus retains the decoded target without creating a video or switching themes.
export function prepareThemeImage(id){return resources.prepare(id)}
export function prepareTheme(id){return prepareThemeImage(id)}
export function prepareThemeThumbnails(){return resources.prepareThumbnails()}
export function setTheme(id,point){
  id=resolveTheme(id).id;origin=point;diagnostics?.selectionRequested?.(id,point)
  if(scheduledSelection)return scheduledSelection.enqueue({id,point:point?{...point}:null,diagnostic:{...diagnostics?.revealOptions()}})
  return select(id)
}
