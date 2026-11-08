import {ref,nextTick,onBeforeUnmount} from 'vue'
export function usePopup(anchor){
 const open=ref(false),target=ref(document.body),style=ref({})
 function place(){
  const el=anchor();if(!el)return
  const host=el.closest('dialog')||document.body;target.value=host
  const r=el.getBoundingClientRect(),hr=host.getBoundingClientRect()
  const fixed=host===document.body,gap=6
  const below=(fixed?innerHeight-r.bottom:hr.bottom-r.bottom)-gap
  const above=r.top-(fixed?0:hr.top)-gap
  const flip=below<120&&above>below
  const maxH=Math.max(96,Math.min(204,(flip?above:below)-gap))
  const edgeL=fixed?0:hr.left,edgeR=fixed?innerWidth:hr.right
  const roomRight=edgeR-r.left-8,roomLeft=r.right-edgeL-8
  const alignEnd=roomRight<200&&roomLeft>roomRight
  style.value={position:fixed?'fixed':'absolute',minWidth:r.width+'px',maxWidth:Math.max(160,Math.min(320,alignEnd?roomLeft:roomRight))+'px',maxHeight:maxH+'px'}
  if(alignEnd)style.value.right=(edgeR-r.right)+'px'
  else style.value.left=(r.left-edgeL)+'px'
  if(flip)style.value.bottom=(fixed?innerHeight-r.top:hr.bottom-r.top)+gap+'px'
  else style.value.top=(fixed?r.bottom:r.bottom-hr.top)+gap+'px'
 }
 async function show(){if(open.value)return;place();open.value=true;await nextTick();window.addEventListener('resize',place);document.addEventListener('scroll',place,true)}
 function hide(){if(!open.value)return;open.value=false;window.removeEventListener('resize',place);document.removeEventListener('scroll',place,true)}
 onBeforeUnmount(hide)
 return {open,target,style,show,hide}
}
