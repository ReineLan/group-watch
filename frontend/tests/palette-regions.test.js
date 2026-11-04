import test from 'node:test'
import assert from 'node:assert/strict'
import {syncPaletteRegions} from '../src/app/theme/paletteRegions.js'

test('moving an archive under a different surface releases old ownership even while still attached',()=>{
 const archive={closest:()=>null,getClientRects:()=>[{}]},target={closest:()=>null,getClientRects:()=>[{}]},regions=new Map(),released=[]
 let visible=[archive],made=0
 const host={querySelectorAll:()=>visible},create=node=>{made++;return {sync:()=>{},dispose:options=>released.push({node,options})}}
 syncPaletteRegions(host,regions,create)
 assert.equal(regions.size,1)
 visible=[target]
 syncPaletteRegions(host,regions,create)
 assert.deepEqual(released,[{node:archive,options:{release:true}}])
 assert.ok(!regions.has(archive));assert.ok(regions.has(target))
 syncPaletteRegions(host,regions,create)
 assert.equal(made,2,'unchanged owners keep their shared progress')
})

test('a hidden route releases its pinned colors and initializes anew when shown',()=>{
 let hidden=false,made=0,released=0
 const node={closest:()=>hidden?{}:null,getClientRects:()=>[{}]},regions=new Map(),host={querySelectorAll:()=>[node]}
 const create=()=>{made++;return {sync:()=>{},dispose:()=>released++}}
 syncPaletteRegions(host,regions,create);hidden=true
 assert.deepEqual(syncPaletteRegions(host,regions,create),[])
 assert.equal(released,1)
 hidden=false;syncPaletteRegions(host,regions,create)
 assert.equal(made,2)
})
