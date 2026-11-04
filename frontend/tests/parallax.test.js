import test from 'node:test'
import assert from 'node:assert/strict'
import {pointerPosition,positionSceneLayers} from '../src/app/ui/background/parallax.js'

test('pointer geometry clamps offscreen input and handles a zero-size viewport',()=>{
  assert.deepEqual(pointerPosition(150,200,300,400),{x:0,y:0})
  assert.deepEqual(pointerPosition(-100,900,300,400),{x:-1,y:1})
  assert.deepEqual(pointerPosition(0,0,0,0),{x:-1,y:-1})
})

test('parallax keeps source and overlapping copies aligned without inherited stage properties',()=>{
  const layer=type=>({classList:{contains:name=>name===type},style:{}})
  const source=[layer('scene-media'),layer('scene-beam')]
  const copies=[layer('scene-media'),layer('scene-petals'),layer('scene-media'),layer('scene-beam')]
  // A stage with no style API also catches an inherited-property regression.
  const stage={querySelectorAll:()=>[...source,...copies]}
  positionSceneLayers(stage,{x:1,y:-.5})
  assert.equal(source[0].style.transform,'translate3d(-7.0000px,3.5000px,0)')
  assert.equal(source[1].style.transform,'translate3d(-56.0000px,28.0000px,0)')
  assert.equal(copies[1].style.transform,'translate3d(-46.0000px,23.0000px,0)')
  assert.equal(source[0].style.transform,copies[0].style.transform)
  assert.equal(source[1].style.transform,copies[3].style.transform)
  positionSceneLayers(stage,{x:0,y:0})
  assert.ok([...source,...copies].every(e=>e.style.transform==='translate3d(0.0000px,0.0000px,0)'))
  positionSceneLayers(null,{x:0,y:0})
})
