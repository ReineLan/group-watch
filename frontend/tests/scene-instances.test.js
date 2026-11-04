import test from 'node:test'
import assert from 'node:assert/strict'
import {createRenderer,h,shallowRef,nextTick,onMounted,onUnmounted} from 'vue'
import {sceneTransitions} from '../src/app/theme/sceneTransitions.js'
import {revealDriver} from '../src/app/theme/revealDriver.js'
import {themeResources} from '../src/app/theme/resources.js'
import {sharedVideos} from '../src/app/theme/sharedVideos.js'
import {joinSceneClock} from '../src/app/theme/sceneClock.js'

// A Vue renderer with an in-memory host: verifies actual keyed component
// identity and teardown without operating the user's browser.
function fixture(){
  const node=type=>({type,children:[],style:{},parent:null})
  const renderer=createRenderer({
    createElement:node,createText:node,createComment:node,setText(){},setElementText(){},
    parentNode:n=>n.parent,nextSibling:n=>n.parent?.children[n.parent.children.indexOf(n)+1],
    patchProp(n,key,old,value){if(key==='style')n.style=value||{}},
    insert(n,parent,anchor){if(n.parent){const a=n.parent.children;a.splice(a.indexOf(n),1)}n.parent=parent;const i=anchor?parent.children.indexOf(anchor):-1;parent.children.splice(i<0?parent.children.length:i,0,n)},
    remove(n){n.parent.children.splice(n.parent.children.indexOf(n),1);n.parent=null},
  })
  const scenes=shallowRef([]),nodes=new Map(),animations=[],timers=new Map(),mounted=[],removed=[],commits=[]
  let timer=0,isChanging=false
  const component={props:['identity'],setup(props){onMounted(()=>mounted.push(props.identity));onUnmounted(()=>removed.push(props.identity));return()=>h('background')}}
  const driver=revealDriver({targetsFor:scene=>nodes.has(scene.key)?[nodes.get(scene.key)]:[],
    setTimer:fn=>{timers.set(++timer,fn);return timer},clearTimer:key=>timers.delete(key),
    animate(node,frames,options){
      let finish,reject
      const finished=new Promise((yes,no)=>{finish=yes;reject=no})
      const animation={node,frames,options,finished,finish,pause(){this.playState='paused'},play(){this.playState='running'},cancel(){this.cancelled=true;reject(Error('cancelled'))}}
      animations.push(animation);return animation
    }})
  const controller=sceneTransitions({initialTheme:'initial',publish:value=>scenes.value=value,flush:nextTick,driver,changing:value=>isChanging=value})
  const app=renderer.createApp({setup:()=>()=>h('host',scenes.value.map(scene=>h('shell',{key:scene.key,ref:node=>node?nodes.set(scene.key,node):nodes.delete(scene.key),style:{clipPath:scene.ring?'circle(...)':'none'}},[h(component,{identity:scene.key})])))})
  app.mount(node('root'))
  const run=(id,options={})=>controller.run(id,()=>commits.push(id),{x:0,y:0},{width:300,height:400,...options})
  const dispose=()=>{controller.cancel();app.unmount()}
  return {controller,run,scenes,nodes,animations,timers,mounted,removed,commits,dispose,changing:()=>isChanging}
}

test('Vue owns base + overlapping rings; promotion preserves the same component and DOM',async()=>{
  const f=fixture(),first=f.run('one');await nextTick();await new Promise(setImmediate)
  const second=f.run('two');await new Promise(setImmediate)
  assert.deepEqual(f.commits,['one','two']);assert.equal(f.scenes.value.length,3)
  const key=f.scenes.value[1].key,originalNode=f.nodes.get(key)
  assert.ok(f.animations.every(a=>!a.cancelled))
  assert.equal(f.animations[0].frames[1]['--theme-reveal-radius'],'500px')
  assert.deepEqual(f.animations[0].options,{duration:950,easing:'cubic-bezier(.22,.8,.2,1)',fill:'forwards'})
  f.animations[0].finish();await first;await nextTick()
  assert.equal(f.scenes.value[0].key,key);assert.equal(f.nodes.get(key),originalNode)
  assert.equal(f.mounted.filter(value=>value===key).length,1);assert.equal(f.removed.includes(key),false)
  assert.equal(f.changing(),true)
  f.animations[1].finish();await second;await nextTick()
  assert.equal(f.scenes.value.length,1);assert.equal(f.scenes.value[0].theme,'two')
  assert.equal(f.timers.size,0);assert.equal(f.changing(),false);f.dispose()
})

test('twelve rapid selections never promote unfinished circles, including reverse completion',async()=>{
  const f=fixture(),pending=[]
  for(let i=0;i<12;i++){pending.push(f.run('theme-'+i));await new Promise(setImmediate);assert.equal(f.scenes.value.length,i+2)}
  assert.ok(f.animations.every(a=>!a.cancelled))
  for(const a of [...f.animations].reverse()){a.finish();await new Promise(setImmediate)}
  await Promise.all(pending);await nextTick()
  assert.equal(f.scenes.value.length,1);assert.equal(f.scenes.value[0].theme,'theme-11')
  assert.equal(f.removed.length,12);assert.equal(f.timers.size,0);f.dispose()
})

test('navigation cancels pending work and retains only the latest committed instance',async()=>{
  const f=fixture(),first=f.run('one');await new Promise(setImmediate)
  const kept=f.scenes.value[1].key,queued=f.run('stale')
  f.controller.cancel();await Promise.all([first,queued]);await nextTick()
  assert.deepEqual(f.commits,['one']);assert.equal(f.scenes.value.length,1)
  assert.equal(f.scenes.value[0].key,kept);assert.equal(f.timers.size,0);f.dispose()
})

test('cancelling while Vue flush is pending settles the waiting selection',async()=>{
  let values,finishFlush
  const flush=new Promise(resolve=>finishFlush=resolve)
  const controller=sceneTransitions({initialTheme:'base',publish:value=>values=value,flush:()=>flush,driver:{start(){throw Error('cancelled mount must not animate')}}})
  const pending=controller.run('new',()=>{},null,{width:1,height:1})
  await Promise.resolve();controller.cancel();finishFlush();await pending
  assert.equal(values.length,1);assert.equal(values[0].theme,'new')
})

test('fallback and reduced motion leave one base with no timers or abandoned instances',async()=>{
  const f=fixture(),pending=f.run('one');await new Promise(setImmediate)
  for(const fn of [...f.timers.values()])fn()
  await pending;await nextTick();assert.equal(f.scenes.value.length,1)
  await f.run('still',{reduced:true});await nextTick()
  assert.equal(f.scenes.value.length,1);assert.equal(f.scenes.value[0].theme,'still')
  assert.equal(f.animations.length,1);assert.equal(f.timers.size,0);f.dispose()
})

test('missing renderer falls back to the selected base and settles callers',async()=>{
  let values
  const controller=sceneTransitions({initialTheme:'base',publish:value=>values=value,flush:async()=>{},driver:revealDriver({targetsFor:()=>[]})})
  await controller.run('new',()=>{},null,{width:1,height:1})
  assert.equal(values.length,1);assert.equal(values[0].theme,'new');assert.equal(values[0].ring,false)
})

test('resource preparation deduplicates aliases, records failure, and retries without acquiring video',async()=>{
  let finish,calls=0,acquired=0
  const resources=themeResources({assets:{one:{image:'shared'},two:{image:'shared'}},videos:{acquire(){acquired++}},preload:()=>{calls++;return new Promise(resolve=>finish=resolve)}})
  assert.equal(resources.state('one'),'idle')
  const first=resources.prepare('one'),second=resources.prepare('two')
  assert.equal(first,second);assert.equal(resources.state('two'),'loading');await Promise.resolve()
  finish(false);assert.equal(await first,false);assert.equal(resources.state('one'),'failed')
  const retry=resources.prepare('one');await Promise.resolve();finish(true);await retry
  assert.equal(resources.state('one'),'ready');assert.equal(calls,2);assert.equal(acquired,0)
})

test('shared videos use one source and playback per URL and release only after the last scene',()=>{
  let created=0,started=0,stopped=0
  const pool=sharedVideos({createVideo:()=>{created++;return {}},play:()=>{started++;return()=>stopped++}})
  assert.equal(created,0)
  const a=pool.acquire('video'),b=pool.acquire('video');assert.equal(a.video,b.video)
  assert.equal(created,1);assert.equal(started,1)
  a.release();a.release();assert.equal(stopped,0)
  pool.setVisible(false);assert.equal(stopped,1);pool.setVisible(true);assert.equal(started,2)
  b.release();assert.equal(stopped,2)
  const c=pool.acquire('video');assert.equal(c.video,b.video);assert.equal(created,1);c.release()
})

test('new scenes share one CSS animation epoch while transitions retain their clock',()=>{
  const a={animationName:'petals',startTime:null},b={animationName:'glow',startTime:null},transition={transitionProperty:'opacity',startTime:55}
  joinSceneClock({getAnimations:()=>[transition,a,b]},120)
  assert.equal(a.startTime,120);assert.equal(b.startTime,120);assert.equal(transition.startTime,55)
})
