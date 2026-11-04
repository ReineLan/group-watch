import test from 'node:test'
import assert from 'node:assert/strict'
import {installThemeDiagnostics} from '../src/app/theme/diagnostics.js'
import {startupExperiment} from '../src/app/theme/startupExperiment.js'

test('normal pages do not access or modify the document through diagnostics',()=>{
  const previous=Object.getOwnPropertyDescriptor(globalThis,'location')
  Object.defineProperty(globalThis,'location',{configurable:true,value:{search:''}})
  try{assert.doesNotThrow(()=>installThemeDiagnostics())}
  finally{if(previous)Object.defineProperty(globalThis,'location',previous);else delete globalThis.location}
})

test('startup controls do not change production or the existing experiments',()=>{
  for(const search of ['', '?theme-debug=cold-double','?theme-debug=glow','?theme-debug=ring-filter'])assert.equal(startupExperiment(search),null)
})
