import test from 'node:test'
import assert from 'node:assert/strict'
import {readdirSync,readFileSync} from 'node:fs'
import {resolve,relative} from 'node:path'
import {fileURLToPath} from 'node:url'
import viteConfig from '../vite.config.js'
import {themes,resolveTheme,revealRadius} from '../src/app/theme/themes.js'

const root=fileURLToPath(new URL('../src',import.meta.url))
const files=dir=>readdirSync(dir,{withFileTypes:true}).flatMap(item=>item.isDirectory()?files(resolve(dir,item.name)):[resolve(dir,item.name)])

test('unknown or missing stored themes fall back to the first theme, 春熙',()=>{
  assert.equal(resolveTheme(null).id,'chunxi')
  assert.equal(resolveTheme('retired').id,'chunxi')
  assert.deepEqual(themes.map(theme=>theme.id),['chunxi','feihua','shuizhong','huadian'])
  assert.deepEqual(themes.map(theme=>theme.effect),['sunlight','petals','petals','sunlight'])
})

test('every theme defines the complete token set and a scene asset',()=>{
  const css=readFileSync(resolve(root,'app/styles/themes.css'),'utf8')
  const assets=viteConfig.plugins.find(plugin=>plugin.name==='scene-assets').load('\0scene-assets')
  const block=id=>css.match(new RegExp(`\\[data-theme=${id}\\]\\{([^}]*)\\}`))[1]
  const base=[...block('huadian').matchAll(/(--[a-z0-9-]+):/g)].map(match=>match[1])
  for(const {id} of themes){
    assert.match(assets,new RegExp(`${id}:\\{image:`),`${id} has no scene image`)
    if(id==='huadian')continue
    const own=new Set([...block(id).matchAll(/(--[a-z0-9-]+):/g)].map(match=>match[1]))
    const optional=['--warn','--warn-soft','--warn-line','--danger','--danger-soft','--danger-line','--info','--sun','--sun-ray','--sun-ray-soft','--shade','--sun-core','--sun-gold','--sparkle','--sun-sweep','--sun-strength','--petal-a','--petal-b','--petal-c','--petal-glow']
    for(const token of base.filter(token=>!optional.includes(token)))assert.ok(own.has(token),`${id} is missing ${token}`)
  }
})

test('the theme reveal always reaches the farthest viewport corner',()=>{
  assert.equal(revealRadius(0,0,300,400),500)
  assert.equal(revealRadius(300,400,300,400),500)
  assert.ok(revealRadius(150,200,300,400)>=250)
})

test('component styles use theme tokens instead of hardcoded colors',()=>{
  const allowed=new Set(['app/styles/themes.css','app/ui/background/BackgroundScene.vue','app/ui/ThemeSwitcher.vue'])
  for(const file of files(root).filter(file=>/\.(css|vue)$/.test(file))){
    const name=relative(root,file).replace(/\\/g,'/')
    if(allowed.has(name))continue
    let css=readFileSync(file,'utf8')
    if(name.endsWith('.vue'))css=[...css.matchAll(/<style[^>]*>([\s\S]*?)<\/style>/g)].map(match=>match[1]).join('')
    const literals=[...css.matchAll(/(^|[{;])\s*([a-z-]+)\s*:([^;{}]*)/g)]
      .filter(([, ,prop])=>!prop.startsWith('--')&&prop!=='mask-image')
      .flatMap(([, ,prop,value])=>(value.match(/#[0-9a-f]{3,8}\b|rgba?\(/gi)||[]).filter(color=>!/^#0{3,6}$/.test(color)).map(color=>prop+':'+color))
    assert.deepEqual(literals,[],`${name} hardcodes colors`)
  }
})
