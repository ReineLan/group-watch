import test from 'node:test'
import assert from 'node:assert/strict'
import {revealTargets,positionLocalReveal,revealClip} from '../src/app/theme/revealTargets.js'

test('registry retains appearance property adapters while keeping the scene primary',()=>{
  const targets=revealTargets(),host={},background={},adapter={node:host,property:'--appearance-radius-0'}
  targets.register(1,'appearance',adapter)
  targets.register(1,'scene',{node:background,primary:true})
  assert.deepEqual(targets.forScene({key:1}),[background,adapter])
})

test('renderer registry keeps background primary regardless of mount order and prepares local geometry',()=>{
  const targets=revealTargets(),values={},skin={style:{setProperty:(key,value)=>values[key]=value},getBoundingClientRect:()=>({left:200,top:100})},background={}
  targets.register(1,'skin',{node:skin,prepare:positionLocalReveal})
  targets.register(1,'scene',{node:background,primary:true})
  const scene={key:1,ring:true,point:{x:800,y:500}}
  assert.deepEqual(targets.forScene(scene),[background,skin])
  assert.deepEqual(values,{'--reveal-center-x':'600px','--reveal-center-y':'400px'})
  targets.register(1,'skin',null);assert.deepEqual(targets.forScene(scene),[background])
  targets.register(1,'scene',{node:null});assert.deepEqual(targets.forScene(scene),[])
})

test('local and viewport targets use the same radius and preserve circle/mask semantics on promotion',()=>{
  const scene={key:1,ring:true,point:{x:800,y:500}}
  assert.equal(revealClip(scene).clipPath,'circle(var(--theme-reveal-radius) at 800px 500px)')
  assert.equal(revealClip(scene,{local:true}).clipPath,'circle(var(--theme-reveal-radius) at var(--reveal-center-x) var(--reveal-center-y))')
  const masked=revealClip({...scene,mask:true},{local:true})
  assert.equal(masked.clipPath,'none');assert.equal(masked.maskImage,masked.WebkitMaskImage)
  assert.ok(masked.maskImage.includes('var(--reveal-center-x) var(--reveal-center-y)'))
  assert.deepEqual(revealClip({...scene,ring:false},{local:true}),{clipPath:'none'})
})
