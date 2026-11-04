import test from 'node:test'
import assert from 'node:assert/strict'
import {readdirSync,readFileSync,existsSync} from 'node:fs'
import {dirname,resolve,relative,extname} from 'node:path'
import {fileURLToPath} from 'node:url'

const root=fileURLToPath(new URL('../src',import.meta.url))
function files(dir){return readdirSync(dir,{withFileTypes:true}).flatMap(item=>item.isDirectory()?files(resolve(dir,item.name)):[resolve(dir,item.name)])}
const graph=new Map()
for(const file of files(root).filter(file=>['.vue','.js'].includes(extname(file)))){
 const imports=[...readFileSync(file,'utf8').matchAll(/(?:from\s*|import\s*)['"]([^'"]+)['"]/g)].map(match=>match[1]).filter(spec=>spec.startsWith('.')).map(spec=>resolve(dirname(file),spec))
 graph.set(file,imports)
}
test('frontend dependencies resolve without cycles or imports back into higher layers',()=>{
 const ranks={app:3,pages:2,entities:1,shared:0}
 const visiting=new Set(),visited=new Set()
 function visit(file){
  assert.ok(!visiting.has(file),`Circular import: ${relative(root,file)}`)
  if(visited.has(file))return
  visiting.add(file)
  for(const target of graph.get(file)||[]){
   assert.ok(existsSync(target),`Missing import: ${relative(root,target)}`)
   const owner=relative(root,file).split(/[\\/]/)[0],dependency=relative(root,target).split(/[\\/]/)[0]
   if(owner in ranks&&dependency in ranks)assert.ok(ranks[dependency]<=ranks[owner],`${owner} depends on ${dependency}`)
   if(graph.has(target))visit(target)
  }
  visiting.delete(file);visited.add(file)
 }
 for(const file of graph.keys())visit(file)
})
