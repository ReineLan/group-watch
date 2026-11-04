import test from 'node:test'
import assert from 'node:assert/strict'
import {readFileSync} from 'node:fs'
import {createRenderer,compile,h,nextTick,ref} from 'vue'

test('evidence mounts inside the new wrapper and moves between records and maintenance',async()=>{
 const source=readFileSync(new URL('../src/app/Workspace.vue',import.meta.url),'utf8')
 const teleport=source.match(/<Teleport[\s\S]*?<\/Teleport>/)[0]
 const root={tag:'root',children:[]}
 const find=(node,id)=>node.props?.id===id?node:(node.children||[]).map(child=>find(child,id)).find(Boolean)
 const remove=node=>{if(node.parent){const list=node.parent.children;list.splice(list.indexOf(node),1);node.parent=null}}
 const renderer=createRenderer({
  createElement:tag=>({tag,children:[],props:{}}),createText:text=>({text}),createComment:text=>({comment:text}),
  setText:(node,text)=>node.text=text,setElementText:(node,text)=>node.text=text,
  patchProp:(node,key,_old,value)=>node.props[key]=value,
  parentNode:node=>node.parent,nextSibling:node=>node.parent?.children[node.parent.children.indexOf(node)+1],
  insert(node,parent,anchor){remove(node);node.parent=parent;const index=anchor?parent.children.indexOf(anchor):-1;parent.children.splice(index<0?parent.children.length:index,0,node)},
  remove,querySelector:selector=>find(root,selector.slice(1)),
 })
 const active=ref('bans')
 const component={setup:()=>({active,evidenceVisible:ref(true),archive:ref(null)}),components:{EvidenceWorkspace:{render:()=>h('section',{id:'evidence-fixture'})}},
  render:compile(`<div><section id="view-records"></section><section id="maintenance-archive"></section>${teleport}</div>`)}
 const app=renderer.createApp(component);app.mount(root);await nextTick()
 assert.equal(find(root,'evidence-fixture').parent,find(root,'view-records'))
 active.value='maintenance';await nextTick()
 assert.equal(find(root,'evidence-fixture').parent,find(root,'maintenance-archive'))
 active.value='methods';await nextTick()
 assert.equal(find(root,'evidence-fixture').parent,find(root,'view-records'))
 app.unmount()
})
