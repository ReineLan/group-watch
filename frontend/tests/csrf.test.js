import test from 'node:test'
import assert from 'node:assert/strict'
import {resolveCsrfToken} from '../src/shared/api/csrf.js'

test('server-rendered entries keep their token without another request',async()=>{
  assert.equal(await resolveCsrfToken('test-token',{fetcher:()=>{throw new Error('unexpected request')}}),'test-token')
})
test('static previews resolve a token from server HTML with same-origin credentials',async()=>{
  const requests=[]
  const token=await resolveCsrfToken('__CSRF__',{fetcher:async(path,options)=>{
    requests.push(path);assert.equal(options.credentials,'same-origin');assert.equal(options.cache,'no-store')
    return {ok:true,text:async()=>'server HTML'}
  },parse:html=>html==='server HTML'?'test-token':undefined})
  assert.equal(token,'test-token');assert.deepEqual(requests,['/work/'])
})
test('local previews fall back to root and refuse missing or placeholder tokens',async()=>{
  const paths=[]
  assert.equal(await resolveCsrfToken('',{fetcher:async path=>{
    paths.push(path);return {ok:true,text:async()=>path}
  },parse:path=>path==='/'?'local-token':'__CSRF__'}),'local-token')
  assert.deepEqual(paths,['/work/','/'])
  await assert.rejects(resolveCsrfToken('__CSRF__',{fetcher:async()=>({ok:true,text:async()=>''}),parse:()=>undefined}),/无法初始化/)
})
