import test from 'node:test'
import assert from 'node:assert/strict'
import {paletteDelay,paletteWave} from '../src/app/theme/paletteWave.js'

test('phone archive arrival uses its visible area even for a very tall table',()=>{
 const viewport={width:390,height:844},scene={point:{x:340,y:30},radius:900}
 const visible={left:13,top:170,width:364,height:674}
 const tall={...visible,height:4000}
 assert.equal(paletteDelay(tall,scene,viewport),paletteDelay(visible,scene,viewport))
 assert.equal(paletteDelay({...tall,width:720},scene,viewport),paletteDelay({...visible,width:377},scene,viewport))
 const desktop={width:1440,height:1000},card={left:300,top:200,width:900,height:500}
 assert.equal(paletteDelay(card,scene,desktop),paletteDelay(card,scene,{}))
})

test('circle arrival uses eased radius, with whole-region fades in spatial order',()=>{
 const scene={point:{x:0,y:0},radius:1000}
 const box=x=>({left:x,top:0,width:0,height:0})
 assert.equal(paletteDelay(box(0),scene),0)
 assert.ok(paletteDelay(box(300),scene)<paletteDelay(box(900),scene))
 assert.ok(paletteDelay(box(1000),scene)<=821)
})

test('an older circle arriving late never reverts a newer displayed theme',()=>{
 let id=0
 const jobs=new Map(),seen=[]
 const wave=paletteWave({setTimer:(fn,delay)=>{jobs.set(++id,{fn,delay});return id},clearTimer:key=>jobs.delete(key)})
 const region={rect:()=>({left:900,top:0,width:0,height:0}),sync:colors=>seen.push(colors)}
 wave.run([region],{point:{x:0,y:0},radius:1000},'old')
 const oldJob=jobs.get(1)
 wave.run([region],{point:{x:900,y:0},radius:1000},'new')
 assert.deepEqual(seen,['new'])
 oldJob.fn()
 assert.deepEqual(seen,['new'])
 wave.run([region],{point:{x:0,y:0},radius:1000},'next')
 wave.cancel()
 assert.ok(!jobs.has(2))
 wave.run([region],null,'reduced',{immediate:true})
 assert.deepEqual(seen,['new','reduced'])
})


test('a new pending theme cancels an older arrival before either changes the surface',()=>{
 let id=0
 const jobs=new Map(),seen=[]
 const wave=paletteWave({setTimer:(fn,delay)=>{jobs.set(++id,{fn,delay});return id},clearTimer:key=>jobs.delete(key)})
 const region={rect:()=>({left:900,top:0,width:0,height:0}),sync:value=>seen.push(value)}
 const scene={point:{x:0,y:0},radius:1000}
 wave.run([region],scene,'old');const stale=jobs.get(1)
 wave.run([region],scene,'latest')
 assert.equal(jobs.has(1),false);stale.fn();assert.deepEqual(seen,[])
 jobs.get(2).fn();assert.deepEqual(seen,['latest'])
})
