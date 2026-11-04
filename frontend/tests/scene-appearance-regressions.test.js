import test from 'node:test'
import assert from 'node:assert/strict'
import {createSSRApp,h,compile} from 'vue'
import {readFileSync} from 'node:fs'
import {renderToString} from 'vue/server-renderer'
import SceneThemeLine from '../src/app/ui/SceneThemeLine.js'
import {resolveTheme} from '../src/app/theme/themes.js'
import {sceneTransitions} from '../src/app/theme/sceneTransitions.js'

test('overlapping scene text copies retain their own names and lines',async()=>{
  const ids=['shuizhong','feihua','chunxi']
  const source=readFileSync(new URL('../src/app/ui/background/SceneRenderer.vue',import.meta.url),'utf8')
  const slot=source.match(/<slot[^>]*\/>/)[0]
  const SceneSlot={props:['scene'],render:compile(slot)}
  const html=await renderToString(createSSRApp({render:()=>h('div',ids.map(themeId=>h(SceneSlot,{scene:{theme:themeId}},
    {default:({theme})=>h(SceneThemeLine,{themeId:theme})})))}))
  for(const id of ids){const theme=resolveTheme(id);assert.ok(html.includes(`<b>${theme.name}</b><span>${theme.line}</span>`))}
})

test('completed appearance animation is disposed only after the promoted scene is patched',async()=>{
  let finish,patch,latest,disposed=false,promoted=false,holdPatch=false
  const driver={start:(_scene,{onComplete})=>{
    finish=()=>onComplete('animation-finished')
    return {promote:options=>{assert.equal(options.deferDispose,true);promoted=true},dispose:()=>disposed=true}
  }}
  const controller=sceneTransitions({initialTheme:'chunxi',publish:value=>latest=value,driver,
    flush:()=>holdPatch?new Promise(resolve=>patch=resolve):Promise.resolve()})
  const settled=controller.run('shuizhong',()=>{},{x:0,y:0},{width:300,height:400})
  await new Promise(setImmediate)
  holdPatch=true;finish()
  assert.equal(latest[0].theme,'shuizhong');assert.equal(latest[0].ring,false)
  assert.equal(promoted,true);assert.equal(disposed,false)
  patch();await settled;await Promise.resolve()
  assert.equal(disposed,true)
  controller.cancel()
})
