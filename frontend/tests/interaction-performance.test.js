import test from 'node:test'
import assert from 'node:assert/strict'
import {latestSelection} from '../src/app/theme/selection.js'
import {scenePreloader} from '../src/app/theme/preload.js'
import {whenNearViewport} from '../src/shared/lib/nearViewport.js'
import {playSceneVideo} from '../src/app/ui/background/playback.js'

test('selection responds before decoding and late completion cannot revert it', async () => {
  let current='huadian'
  const waiting=new Map(),commits=[]
  const select=latestSelection(()=>current,id=>new Promise(resolve=>waiting.set(id,resolve)),id=>{current=id;commits.push(id)})
  const first=select('chunxi'),second=select('feihua')
  waiting.get('feihua')();await second
  waiting.get('chunxi')();await first
  assert.deepEqual(commits,['chunxi','feihua'])
  const pending=select('shuizhong')
  await select('feihua')
  waiting.get('shuizhong')();await pending
  assert.equal(current,'feihua')
  assert.deepEqual(commits,['chunxi','feihua','shuizhong','feihua'])
})

test('a failed full image still selects the thumbnail fallback and later choices work', async () => {
  let current='huadian'
  const select=latestSelection(()=>current,async id=>id!=='chunxi',id=>{current=id})
  await select('chunxi')
  assert.equal(current,'chunxi')
  await select('feihua')
  assert.equal(current,'feihua')
})

test('a 2400ms first decode never delays selection and its result is retained', async t => {
  t.mock.timers.enable({apis:['setTimeout']})
  let finish,created=0,current='old'
  const preload=scenePreloader(()=>{created++;return {decode:()=>new Promise(resolve=>finish=resolve)}})
  const select=latestSelection(()=>current,preload,id=>{current=id})
  const switching=select('new')
  assert.equal(current,'new')
  // Model a busy computer's first decode taking longer than the former cutoff.
  t.mock.timers.tick(2400)
  await new Promise(setImmediate)
  assert.equal(current,'new')
  finish();await switching
  assert.equal(current,'new')
  assert.equal(await preload('new'),true)
  assert.equal(created,1)
})

test('a failed decode can be retried without revealing the unavailable scene', async () => {
  let attempts=0
  const preload=scenePreloader(()=>({decode:()=>++attempts===1?Promise.reject(Error('unavailable')):Promise.resolve()}))
  assert.equal(await preload('scene'),false)
  assert.equal(await preload('scene'),true)
  assert.equal(attempts,2)
})

test('offscreen chat loading waits for proximity, runs once and stops on unmount', () => {
  let notify,observed,disconnected=0,loads=0
  class Observer {
    constructor(callback,options){notify=callback;assert.equal(options.rootMargin,'400px')}
    observe(element){observed=element}
    disconnect(){disconnected++}
  }
  const element={}
  whenNearViewport(element,()=>loads++,Observer)
  assert.equal(observed,element)
  notify([{isIntersecting:false}]);assert.equal(loads,0)
  notify([{isIntersecting:true}]);notify([{isIntersecting:true}])
  assert.equal(loads,1);assert.equal(disconnected,1)
  const cancel=whenNearViewport(element,()=>loads++,Observer)
  cancel();notify([{isIntersecting:true}]);assert.equal(loads,1)
  whenNearViewport(element,()=>loads++,null);assert.equal(loads,2)
})

test('video keeps its poster until a fresh frame and ignores callbacks after hiding', async () => {
  const events=new Map(),states=[]
  let presented,visible=true,paused=0,cancelled=0
  const video={
    play:()=>Promise.resolve(),pause:()=>paused++,
    addEventListener:(name,fn)=>events.set(name,fn),removeEventListener:name=>events.delete(name),
    requestVideoFrameCallback:fn=>{presented=fn;return 7},cancelVideoFrameCallback:()=>cancelled++
  }
  const stop=playSceneVideo(video,value=>states.push(value),()=>visible)
  assert.deepEqual(states,[false])
  await Promise.resolve()
  presented();assert.equal(states.at(-1),true)
  events.get('waiting')?.();assert.equal(states.at(-1),true)
  events.get('error')();assert.equal(states.at(-1),false)
  events.get('playing')()
  visible=false;stop();presented()
  assert.equal(states.at(-1),false)
  assert.equal(paused,1);assert.equal(cancelled,1);assert.equal(events.size,0)
  visible=true
  playSceneVideo(video,value=>states.push(value),()=>visible)
  await Promise.resolve();presented()
  assert.equal(states.at(-1),true)
})

test('loop boundary waiting keeps the presented frame without exposing the poster',async()=>{
  const video=new EventTarget(),states=[]
  let presented,frame=0
  Object.assign(video,{
    play:()=>Promise.resolve(),pause(){},
    requestVideoFrameCallback:fn=>{presented=fn;return ++frame},cancelVideoFrameCallback(){}
  })
  const stop=playSceneVideo(video,value=>states.push(value),()=>true)
  video.dispatchEvent(new Event('waiting'))
  assert.deepEqual(states,[false])
  await Promise.resolve();presented()
  assert.equal(states.at(-1),true)
  for(let loop=0;loop<3;loop++){
    video.dispatchEvent(new Event('waiting'))
    assert.equal(states.at(-1),true)
    video.dispatchEvent(new Event('playing'));presented()
  }
  assert.deepEqual(states,[false,true,true,true,true])
  video.dispatchEvent(new Event('error'))
  assert.equal(states.at(-1),false)
  stop()
})

test('blocked video playback leaves the poster visible', async () => {
  const states=[]
  const stop=playSceneVideo({play:()=>Promise.reject(new Error('blocked')),pause(){},addEventListener(){},removeEventListener(){}},value=>states.push(value),()=>true)
  await Promise.resolve();await Promise.resolve()
  assert.deepEqual(states,[false,false])
  stop()
})
