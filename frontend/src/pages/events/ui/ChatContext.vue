<script setup>
import {computed,ref,nextTick,onMounted,onBeforeUnmount} from 'vue'
import {useWorkspace} from '../../../entities/monitor/model/workspace.js'
import {whenNearViewport} from '../../../shared/lib/nearViewport.js'
import {snapshotElement,readAsDataURL} from '../../../shared/lib/domSnapshot.js'
const props=defineProps({item:Object}),{api}=useWorkspace(),data=ref(null),loading=ref(true),error=ref('')
const emit=defineEmits(['portrait']),context=ref(null),nearby=ref(false)
const rows=computed(()=>data.value?.messages||props.item.context.map(m=>({...m,parts:[...(m.text?[{type:'text',text:m.text}]:[]),...(m.media||[]).filter(t=>!['reply','at'].includes(t)).map(t=>({type:'unsupported',text:({image:'图片加载后显示',face:'QQ 表情',record:'语音',video:'视频'}[t]||'附件')}))]})))
const selected=m=>String(m.user_id)===String(props.item.user_id)&&props.item.evidence.some(id=>String(id)===String(m.message_id))
const clockFormat=new Intl.DateTimeFormat('zh-CN',{timeZone:'Asia/Shanghai',month:'numeric',day:'numeric',hour:'2-digit',minute:'2-digit',hour12:false})
const clock=value=>clockFormat.format(new Date(value*1000))
let request,stopObserving
async function load(){request?.abort();const active=new AbortController();request=active;const timer=setTimeout(()=>active.abort(),35000);loading.value=true;error.value='';try{const value=await api('/api/cases/'+encodeURIComponent(props.item.id)+'/context',undefined,{signal:active.signal});if(request===active){data.value=value;emit('portrait',value.messages?.find(m=>String(m.user_id)===String(props.item.user_id)&&m.avatar)||null)}}catch(e){if(request===active)error.value=e.message}finally{clearTimeout(timer);if(request===active)loading.value=false}}
onMounted(()=>stopObserving=whenNearViewport(context.value,()=>{nearby.value=true;load()}))
onBeforeUnmount(()=>{stopObserving?.();request?.abort();request=null})
function trimContext(chat){
 const msgs=rows.value,picked=msgs.map((m,i)=>selected(m)?i:-1).filter(i=>i>=0),keep=new Set()
 if(picked.length){
  const first=picked[0],last=picked[picked.length-1]
  for(let i=Math.max(0,first-3);i<=first;i++)keep.add(i)
  for(let i=last;i<=Math.min(msgs.length-1,last+3);i++)keep.add(i)
  const middle=picked.slice(1,-1).filter(i=>!keep.has(i))
  for(const i of middle.slice(0,2))keep.add(i)
 }else for(let i=Math.max(0,msgs.length-8);i<msgs.length;i++)keep.add(i)
 const children=[...chat.children],decision=new Map()
 let index=0
 for(const node of children)if(node.classList.contains('qq-message'))decision.set(node,keep.has(index++))
 for(const node of children)if(node.classList.contains('qq-stamp'))decision.set(node,decision.get(node.nextElementSibling)===true)
 let omitted=0
 const flush=anchor=>{
  if(!omitted)return
  const marker=chat.ownerDocument.createElement('div')
  marker.style.cssText='text-align:center;font-size:11px;color:var(--subtle);margin:10px 0'
  marker.textContent='· 省略 '+omitted+' 条消息 ·'
  chat.insertBefore(marker,anchor);omitted=0
 }
 for(const node of children){
  if(decision.get(node)){flush(node);continue}
  if(node.classList.contains('qq-message'))omitted++
  node.remove()
 }
 flush(null)
}
async function snapshot(){
 const element=context.value
 if(!element)return null
 nearby.value=true
 if(!data.value)await load()
 if(error.value)throw new Error(error.value)
 await nextTick()
 const blob=await snapshotElement(element,{prepare:chat=>chat.querySelector('.qq-chat')&&trimContext(chat.querySelector('.qq-chat'))})
 const preview=await readAsDataURL(blob),ext=blob.type==='image/png'?'png':'webp'
 return {name:'聊天上下文.'+ext,original_name:'聊天上下文.'+ext,type:blob.type,data:preview.split(',')[1],preview}
}
defineExpose({snapshot})
</script>
<template>
<section ref="context" class="qq-context" aria-label="聊天上下文">
 <header class="qq-bar"><span aria-hidden="true">‹</span><strong>{{data?.group_name||item.group_name}}<small v-if="data?.member_count"> ({{data.member_count}})</small></strong><span aria-hidden="true">☰</span></header>
 <p v-if="!nearby" class="qq-notice qq-deferred">滚动到这里时加载聊天上下文</p><p v-else-if="loading" class="qq-notice" role="status">正在读取头像、挂件与消息图片…</p><p v-if="error" class="qq-notice" role="alert">{{error}} <button type="button" @click="load">重试</button></p>
 <div v-if="nearby" class="qq-chat">
  <template v-for="(msg,i) in rows" :key="msg.message_id+'-'+i">
   <time v-if="i===0||msg.time-rows[i-1].time>300" class="qq-stamp">{{clock(msg.time)}}</time>
   <div class="qq-message" :class="{'qq-candidate':selected(msg)}" :aria-label="selected(msg)?'候选发言':undefined">
    <div class="qq-portrait"><span>{{msg.name?.slice(0,1)||'群'}}</span><img v-if="msg.avatar" class="qq-avatar" :src="msg.avatar" alt="成员头像" loading="lazy" @error="$event.target.style.visibility='hidden'"><img v-if="msg.pendant" class="qq-pendant" :src="msg.pendant" :alt="msg.pendant_name||'头像挂件'" loading="lazy" @error="$event.target.style.visibility='hidden'"></div>
    <div class="qq-body"><div class="qq-name"><span v-if="msg.title||['owner','admin'].includes(msg.role)||msg.level" class="qq-tag">{{msg.title||({owner:'群主',admin:'管理员'})[msg.role]||'LV '+msg.level}}</span>{{msg.name}}<span v-if="selected(msg)" class="qq-marker">候选发言</span><time class="qq-inline-time">{{clock(msg.time)}}</time></div>
     <div class="qq-content">
      <div v-if="msg.medal||msg.guard_level||msg.super_chat" class="live-badges"><span v-if="msg.medal?.name">{{msg.medal.name}} {{msg.medal.level}}</span><span v-if="msg.guard_level">{{({1:'总督',2:'提督',3:'舰长'})[msg.guard_level]||''}}</span><strong v-if="msg.super_chat">醒目留言 · ¥{{msg.super_chat.price_cny}}</strong></div>
      <img v-if="msg.nameplate" class="live-nameplate" :src="msg.nameplate" alt="用户铭牌" loading="lazy">
      <div class="qq-bubble" :class="{'qq-media-only':msg.parts.every(p=>['image','face'].includes(p.type))}">
       <template v-for="(part,n) in msg.parts" :key="n"><blockquote v-if="part.type==='reply'" class="qq-quote"><strong>{{part.name}}</strong>{{part.text}}</blockquote><span v-else-if="part.type==='text'" class="qq-text">{{part.text}}</span><a v-else-if="part.url" :href="part.url" target="_blank" rel="noopener" :aria-label="'查看'+part.text"><img :class="part.type==='face'?'qq-face':'qq-picture'" :src="part.url" :alt="part.text" loading="lazy"></a><span v-else class="qq-attachment">[{{part.text}}]</span></template>
      </div>
     </div>
    </div>
   </div>
  </template>
 </div>

</section>
</template>
<style scoped>
.live-badges{display:flex;gap:7px;flex-wrap:wrap;font-size:11px;color:var(--muted);margin-bottom:6px}.live-badges strong{color:var(--warn)}.live-nameplate{max-width:160px;max-height:36px;object-fit:contain;display:block;margin-bottom:6px}
.qq-context{margin:18px 0;background:var(--surface-3);border:1px solid var(--line-1);border-radius:12px;overflow:hidden;color:var(--ink);font-family:'Microsoft YaHei',sans-serif}.qq-bar{display:flex;align-items:center;gap:18px;padding:15px 19px;border-bottom:1px solid var(--line-1);background:var(--surface-2)}.qq-bar>span:first-child{font-size:29px;line-height:1}.qq-bar strong{flex:1;font-size:16px;font-weight:500}.qq-bar small{color:var(--muted);font-size:13px}.qq-chat{padding:18px 20px 10px;max-height:650px;overflow:auto}.qq-stamp{display:block;text-align:center;font-size:11px;color:var(--subtle);margin:2px 0 18px}.qq-message{position:relative;display:flex;align-items:flex-start;gap:12px;margin:0 0 14px}.qq-portrait{position:relative;width:44px;height:44px;flex:none;border-radius:50%;background:var(--surface-4);margin-top:3px}.qq-portrait>span{position:absolute;inset:0;display:grid;place-items:center;color:var(--subtle)}.qq-avatar{position:absolute;inset:0;width:44px;height:44px;object-fit:cover;border-radius:50%}.qq-pendant{position:absolute;width:74px;height:74px;max-width:none;left:-15px;top:-15px;object-fit:contain;pointer-events:none;z-index:1}.qq-body{flex:1;min-width:0;max-width:calc(100% - 59px)}.qq-name{display:flex;align-items:center;flex-wrap:wrap;gap:6px;color:var(--subtle);font-size:12px;margin:0 0 6px;line-height:1.5}.qq-tag{font-size:9px;padding:1px 4px;border-radius:3px;background:var(--accent-2);color:var(--on-accent);white-space:nowrap}.qq-marker{font-size:10px;color:var(--danger)}.qq-inline-time{font-size:10px;color:var(--faint)}.qq-content{display:inline-block;max-width:100%}.qq-message.qq-candidate:before{content:"";position:absolute;inset:-13px -6px -5px -16px;border:2px dashed var(--danger);border-radius:11px;pointer-events:none}.qq-bubble{display:block;position:relative;max-width:100%;border-radius:9px;padding:10px 13px;background:var(--surface);font-size:15px;line-height:1.65;overflow-wrap:anywhere;white-space:pre-wrap}.qq-bubble:before{content:'';position:absolute;top:12px;left:-4px;width:9px;height:9px;border-radius:2px;background:inherit;transform:rotate(45deg)}.qq-media-only{background:transparent;padding:0}.qq-media-only:before{display:none}.qq-quote{margin:0 0 8px;padding:7px 10px;border:0;border-left:3px solid var(--line-2);background:var(--surface-3);border-radius:4px;color:var(--subtle);font-size:12px;line-height:1.6}.qq-quote strong{display:block;font-weight:400;margin-bottom:3px}.qq-picture{max-width:min(240px,100%);max-height:280px;object-fit:contain;display:block;border-radius:7px;margin:3px 0}.qq-face{width:30px;height:30px;object-fit:contain;vertical-align:middle}.qq-attachment{font-size:13px;color:var(--subtle)}.qq-notice{font-size:11px;color:var(--subtle);padding:10px 18px;margin:0;line-height:1.7}.qq-footnote{border-top:1px solid var(--line-1)}.qq-notice button{border:0;background:none;color:var(--muted);text-decoration:underline;cursor:pointer}@media(max-width:600px){.qq-chat{padding:18px 14px 6px}.qq-bar{padding:12px 14px}.qq-bar strong{font-size:14px}.qq-inline-time{display:none}.qq-picture{max-width:min(180px,100%)}}
</style>
