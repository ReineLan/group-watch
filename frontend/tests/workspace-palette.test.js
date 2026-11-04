import test from 'node:test'
import assert from 'node:assert/strict'
import {workspacePalette,workspaceColors,paletteClock} from '../src/app/theme/workspacePalette.js'

function fixture(){
 const values=new Map(),writes=[],source={colors:Object.fromEntries(workspaceColors.map(name=>[`--${name}`,'rgb(10, 20, 30)']))},attrs=new Set()
 let time=0,next=0
 const frames=new Map(),timeline=paletteClock({now:()=>time,request:callback=>{frames.set(++next,callback);return next},cancel:key=>frames.delete(key)})
 const node={style:{getPropertyValue:key=>values.get(key)||'',getPropertyPriority:()=>'',setProperty:(key,value)=>{values.set(key,value);writes.push(key)},removeProperty:key=>values.delete(key)},hasAttribute:key=>attrs.has(key),setAttribute:key=>attrs.add(key),removeAttribute:key=>attrs.delete(key)}
 const read=target=>({getPropertyValue:key=>target===source?source.colors[key]:node.display?.[key]||values.get(key)})
 const advance=t=>{time=t;const pending=[...frames.values()];frames.clear();for(const callback of pending)callback(t)}
 const palette=workspacePalette(node,{source,read,timeline,reduced:()=>false})
 return {node,source,values,writes,attrs,frames,advance,palette,read,timeline}
}

test('surface text, accents and edges share one monotonic progress without native color animations',()=>{
 const f=fixture(),target=Object.fromEntries(workspaceColors.map(name=>[`--${name}`,'rgb(200, 210, 220)']))
 f.palette.sync(target)
 assert.equal(f.frames.size,1)
 for(const name of ['ink','muted','accent','on-accent','glass-edge','surface'])assert.match(f.values.get(`--${name}`),/var\(--palette-progress\)/)
 f.writes.length=0
 f.advance(65)
 const first=parseFloat(f.values.get('--palette-progress'))
 f.advance(130)
 assert.ok(parseFloat(f.values.get('--palette-progress'))>first)
 assert.deepEqual(f.writes,['--palette-progress','--palette-progress'],'only one progress write per frame, no style reads or per-token animation')
 f.palette.sync(target)
 assert.equal(f.frames.size,1,'same destination does not restart the clock')
 f.advance(260)
 assert.equal(f.frames.size,0)
 assert.equal(f.values.get('--ink'),target['--ink'])
 assert.equal(f.values.get('--glass-edge'),target['--glass-edge'])
 assert.ok(!f.attrs.has('data-palette-animating'))
})

test('retarget captures the displayed palette; removed jobs cannot restore old colors',()=>{
 const f=fixture(),target={...f.source.colors,'--ink':'rgb(200, 210, 220)'}
 f.palette.sync(target);f.advance(100)
 f.node.display={...f.source.colors,'--ink':'rgb(80, 90, 100)'}
 const next={...target,'--ink':'rgb(30, 40, 50)'}
 f.palette.sync(next)
 assert.match(f.values.get('--ink'),/rgb\(80, 90, 100\)/)
 f.advance(260)
 assert.ok(f.attrs.has('data-palette-animating'),'new transition keeps its own 260ms duration')
 f.advance(360)
 assert.equal(f.values.get('--ink'),next['--ink'])
 f.palette.dispose();f.palette.sync(target)
 assert.equal(f.frames.size,0)
 assert.equal(f.values.get('--ink'),next['--ink'])
})

test('all regions share one RAF callback and disposal cancels the last pending frame',()=>{
 const f=fixture(),other={...f.node,style:{getPropertyValue:()=>'',getPropertyPriority:()=>'',setProperty:()=>{},removeProperty:()=>{}}}
 const palette=workspacePalette(other,{source:f.source,read:f.read,timeline:f.timeline,reduced:()=>false})
 const target={...f.source.colors,'--ink':'white'}
 f.palette.sync(target);palette.sync(target)
 assert.equal(f.frames.size,1)
 f.palette.dispose();assert.equal(f.frames.size,1)
 palette.dispose();assert.equal(f.frames.size,0)
})

test('reduced motion publishes the palette immediately without scheduling frames',()=>{
 const f=fixture(),palette=workspacePalette(f.node,{source:f.source,read:f.read,timeline:f.timeline,reduced:()=>true})
 palette.sync({...f.source.colors,'--ink':'white'})
 assert.equal(f.frames.size,0);assert.equal(f.values.get('--ink'),'white')
 palette.dispose()
})

test('retiring a moved region releases its fixed colors and preserves pre-existing inline styles',()=>{
 const f=fixture()
 f.palette.dispose({release:true})
 assert.ok(!f.values.has('--ink'))
 assert.ok(!f.attrs.has('data-ui-palette'))
 f.values.set('--ink','purple')
 const palette=workspacePalette(f.node,{source:f.source,read:f.read,timeline:f.timeline,reduced:()=>true})
 palette.sync({...f.source.colors,'--ink':'white'})
 palette.dispose({release:true})
 assert.equal(f.values.get('--ink'),'purple')
})
