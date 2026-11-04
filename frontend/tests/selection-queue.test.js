import test from 'node:test'
import assert from 'node:assert/strict'
import {selectionQueue} from '../src/app/theme/selectionQueue.js'

const flush=async()=>{for(let i=0;i<8;i++)await Promise.resolve()}
function clock(){
  let time=0,key=0
  const timers=new Map()
  return {now:()=>time,setTimer:(fn,delay)=>{timers.set(++key,{fn,at:time+delay});return key},clearTimer:key=>timers.delete(key),
    async advance(ms){time+=ms;for(const [key,timer] of [...timers])if(timer.at<=time){timers.delete(key);timer.fn()}await flush()},timers}
}

test('260ms is measured from actual start, and next starts overlap unfinished 950ms circles',async()=>{
  const c=clock(),starts=[],ready=[],finishes=[]
  const q=selectionQueue({...c,run:(request,onStarted)=>new Promise(resolve=>{ready.push(()=>{starts.push([request,c.now()]);onStarted()});finishes.push(resolve)})})
  const a=q.enqueue('one'),b=q.enqueue('two'),d=q.enqueue('three')
  await c.advance(100);assert.equal(ready.length,1)
  ready[0]();await c.advance(259);assert.equal(ready.length,1)
  await c.advance(1);assert.equal(ready.length,2)
  await c.advance(80);ready[1]();await c.advance(260);assert.equal(ready.length,3)
  ready[2]();assert.deepEqual(starts,[['one',100],['two',440],['three',700]])
  finishes.forEach(f=>f());await Promise.all([a,b,d])
})

test('five waiting entries drop the oldest waiting click and preserve bound points and latest intent',async()=>{
  const c=clock(),events=[],seen=[]
  const q=selectionQueue({...c,observe:e=>events.push(e),run:(request,start)=>{seen.push(request);start()}})
  const promises=[]
  for(let i=0;i<9;i++)promises.push(q.enqueue({id:i,point:{x:i,y:-i}}))
  assert.deepEqual(await promises[1],{status:'dropped'});assert.deepEqual(await promises[2],{status:'dropped'});assert.deepEqual(await promises[3],{status:'dropped'})
  for(let i=0;i<5;i++)await c.advance(260)
  await Promise.all(promises)
  assert.deepEqual(seen.map(e=>e.id),[0,4,5,6,7,8]);assert.deepEqual(seen.at(-1).point,{x:8,y:-8})
  assert.ok(events.every(e=>e.pending.length<=5));assert.equal(c.timers.size,0)
})

test('returning to current theme after a queued different theme is preserved; no-op does not stall',async()=>{
  const c=clock(),seen=[];let current='a'
  const q=selectionQueue({...c,run:(id,start)=>{if(id===current)return;current=id;seen.push(id);start()}})
  const pending=['a','b','a','a','c'].map(id=>q.enqueue(id));await flush()
  await c.advance(260);await c.advance(260);await c.advance(260)
  await Promise.all(pending);assert.deepEqual(seen,['b','a','c']);assert.equal(current,'c')
})

test('cancel clears waiting clicks/timer and invalidates a delayed old start signal',async()=>{
  const c=clock(),ready=[],finish=[]
  const q=selectionQueue({...c,run:(id,start)=>new Promise(resolve=>{ready.push(start);finish.push(resolve)})})
  const first=q.enqueue('old'),waiting=q.enqueue('waiting');q.cancel()
  assert.deepEqual(await waiting,{status:'cancelled'})
  const next=q.enqueue('new');ready[0]();ready[1]();assert.equal(c.timers.size,0)
  finish.forEach(f=>f());await Promise.all([first,next]);assert.equal(c.timers.size,0)
})

test('overdue timer starts one request without catching up in a burst',async()=>{
  const c=clock(),times=[]
  const q=selectionQueue({...c,run:(id,start)=>{times.push(c.now());start()}})
  const pending=[1,2,3].map(id=>q.enqueue(id))
  await c.advance(1000);assert.deepEqual(times,[0,1000])
  await c.advance(260);await Promise.all(pending);assert.deepEqual(times,[0,1000,1260])
})
