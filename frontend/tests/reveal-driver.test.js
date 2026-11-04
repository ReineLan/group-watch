import test from 'node:test'
import assert from 'node:assert/strict'
import {revealDriver} from '../src/app/theme/revealDriver.js'
import {revealTimeForRadius} from '../src/app/theme/reveal.js'

function fixture(count=2,custom=false){
  const targets=Array.from({length:count},()=>({style:{clipPath:'circle(...)',maskImage:'mask'}})),animations=[],timers=new Map(),completed=[]
  let timer=0,starts=0
  const driver=revealDriver({targetsFor:()=>targets.map((node,index)=>custom&&index?{node,property:'--appearance-radius-0'}:node),timingEnabled:()=>false,
    setTimer:(fn,ms)=>{timers.set(++timer,{fn,ms});return timer},clearTimer:id=>timers.delete(id),
    animate:(node,frames,options)=>{
      let finish,reject,ready
      const animation={node,frames,options,currentTime:0,startTime:null,playState:'running',
        ready:new Promise(resolve=>ready=resolve),finished:new Promise((resolve,no)=>{finish=resolve;reject=no}),
        finish:()=>finish(),reject:()=>reject(Error('cancelled')),readyNow:time=>{animation.startTime=time;ready()},
        pause(){this.playState='paused';this.startTime=null},play(){this.playState='running';this.startTime=null},cancel(){this.playState='idle';reject(Error('cancelled'))}}
      animations.push(animation);return animation
    }})
  const handle=driver.start({key:1,radius:500},{onStarted:()=>starts++,onComplete:reason=>completed.push(reason)})
  return {targets,animations,timers,completed,handle,starts}
}
const flush=async()=>{for(let i=0;i<5;i++)await Promise.resolve()}

test('shared appearance host animates its registered property without clearing unrelated masks',async()=>{
  const f=fixture(2,true),[primary,appearance]=f.animations
  assert.deepEqual(appearance.frames,[{'--appearance-radius-0':'0px'},{'--appearance-radius-0':'500px'}])
  primary.readyNow(200);appearance.readyNow(240);await flush()
  assert.equal(appearance.startTime,200)
  f.handle.pause(.4);assert.equal(primary.currentTime,appearance.currentTime)
  f.handle.promote();await flush()
  assert.equal(f.targets[0].style.maskImage,'none')
  assert.equal(f.targets[1].style.maskImage,'mask')
  assert.equal(appearance.playState,'idle');assert.equal(f.completed.length,0)
})

test('promotion can keep appearance radii alive until renderer removes their masks',async()=>{
  const f=fixture(2,true)
  f.handle.promote({deferDispose:true})
  assert.equal(f.targets[0].style.clipPath,'none')
  assert.ok(f.animations.every(animation=>animation.playState!=='idle'))
  f.handle.dispose();await flush()
  assert.ok(f.animations.every(animation=>animation.playState==='idle'))
})

test('visual targets share primary clock, radius and exactly one completion; promotion clears all clips',async()=>{
  const f=fixture(),[primary,secondary]=f.animations
  assert.equal(f.starts,1);assert.equal(f.timers.size,1)
  assert.deepEqual(primary.frames,secondary.frames);assert.equal(primary.options.duration,950)
  primary.readyNow(123);secondary.readyNow(140);await flush();assert.equal(secondary.startTime,123)
  secondary.finish();await flush();assert.equal(f.completed.length,0)
  primary.finish();await flush();assert.deepEqual(f.completed,['animation-finished']);assert.equal(f.timers.size,0)
  f.handle.promote();await flush()
  assert.ok(f.targets.every(node=>node.style.clipPath==='none'&&node.style.maskImage==='none'))
  assert.ok(f.animations.every(a=>a.playState==='idle'));assert.equal(f.completed.length,1)
})

test('pause/resume affects every target with one radius clock and one remaining-time fallback',async()=>{
  const f=fixture()
  f.handle.pause(.6)
  assert.ok(f.animations.every(a=>a.currentTime===revealTimeForRadius(.6)&&a.playState==='paused'));assert.equal(f.timers.size,0)
  f.handle.resume();f.animations[0].readyNow(500);await flush()
  assert.ok(f.animations.every(a=>a.playState==='running'&&a.startTime===500))
  assert.equal(f.timers.size,1);assert.equal([...f.timers.values()][0].ms,950-revealTimeForRadius(.6)+1250)
  f.handle.dispose();await flush();assert.equal(f.timers.size,0);assert.equal(f.completed.length,0)
})

test('fallback fires once; later natural completion and repeated disposal cannot duplicate it',async()=>{
  const f=fixture(1),callback=[...f.timers.values()][0].fn
  callback();callback();f.animations[0].finish();await flush()
  assert.deepEqual(f.completed,['fallback']);f.handle.dispose();f.handle.dispose();assert.equal(f.timers.size,0)
})

test('failed target setup cancels already-created animations instead of leaking partial targets',async()=>{
  let cancelled=0,created=0
  const animation={finished:Promise.resolve(),cancel:()=>cancelled++}
  const driver=revealDriver({targetsFor:()=>[{},{}],animate:()=>{if(created++===0)return animation;throw Error('second target failed')}})
  assert.throws(()=>driver.start({radius:100}),/second target failed/)
  assert.equal(cancelled,1);await flush()
})
