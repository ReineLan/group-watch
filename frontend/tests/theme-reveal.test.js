import test from 'node:test'
import assert from 'node:assert/strict'
import {afterPaint} from '../src/shared/lib/afterPaint.js'
import {mirrorVideo} from '../src/app/theme/videoMirror.js'

test('navigation yields a paint before first-page data work',async()=>{
  const frames=[];let done=false
  const pending=afterPaint(fn=>frames.push(fn)).then(()=>done=true)
  frames.shift()();await Promise.resolve();assert.equal(done,false)
  frames.shift()();await pending;assert.equal(done,true)
})

test('overlapping video layers reuse live frames without starting another video',()=>{
  let callback,draws=0,cancelled=0
  const video={readyState:4,videoWidth:1920,videoHeight:1080,
    requestVideoFrameCallback:fn=>{callback=fn;return 1},cancelVideoFrameCallback:()=>cancelled++}
  const canvas={getContext:()=>({drawImage:source=>{assert.equal(source,video);draws++}}),classList:{add:name=>assert.equal(name,'is-ready')}}
  const stop=mirrorVideo(video,canvas)
  assert.equal(draws,1);assert.equal(canvas.width,1920)
  callback();assert.equal(draws,2)
  stop();callback();assert.equal(draws,2);assert.equal(cancelled,1)
})
