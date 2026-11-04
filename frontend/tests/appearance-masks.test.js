import test from 'node:test'
import assert from 'node:assert/strict'
import {appearanceMasks} from '../src/app/theme/appearanceMasks.js'

const ring=(key,x=100,y=200)=>({key,ring:true,point:{x,y}})
test('transparent appearances intersect their own Reveal with every later exclusion',()=>{
  const masks=appearanceMasks(()=>{}),scenes=[{key:0,ring:false},ring(1),ring(2,400,500)]
  masks.sync(scenes)
  const base=masks.style(scenes[0],0,scenes),first=masks.style(scenes[1],1,scenes),last=masks.style(scenes[2],2,scenes)
  assert.equal(base.maskComposite,'intersect')
  assert.match(base.maskImage,/transparent 0 var\(--appearance-radius-0\)/)
  assert.match(base.maskImage,/transparent 0 var\(--appearance-radius-1\)/)
  assert.match(first.maskImage,/black 0 var\(--appearance-radius-0\)/)
  assert.match(first.maskImage,/transparent 0 var\(--appearance-radius-1\)/)
  assert.match(last.maskImage,/circle at 400px 500px, black/)
  assert.ok(!last.maskImage.includes('--appearance-radius-0'))
})
test('promotion removes exclusions; registered properties grow with concurrency rather than clicks',()=>{
  const registered=[],masks=appearanceMasks(name=>registered.push(name))
  for(let i=0;i<100;i++){
    const scenes=[{key:i,ring:false},ring(i+1)]
    masks.sync(scenes);assert.equal(masks.property(i+1),'--appearance-radius-0')
    masks.sync([{key:i+1,ring:false}])
    assert.equal(masks.style({ring:false},0,[{ring:false}]).maskImage,'none')
  }
  assert.deepEqual(registered,['--appearance-radius-0'])
  masks.sync([ring(101),ring(102)])
  masks.sync([ring(102),ring(103)])
  assert.equal(masks.property(102),'--appearance-radius-1')
  assert.equal(masks.property(103),'--appearance-radius-0')
  assert.equal(registered.length,2)
})
