<script setup>
import {computed,ref,watch} from 'vue'
import {useWorkspace} from '../../../entities/monitor/model/workspace.js'
import {useEvidence} from '../../../entities/evidence/model/state.js'
import {caseDraft,cachedChatShot,cacheChatShot,reviveChatShot} from '../model/cases.js'
import {states,time} from '../../../shared/lib/format.js'
import ChatContext from './ChatContext.vue'
import AppIcon from '../../../shared/ui/AppIcon.vue'
const props=defineProps({item:Object}),emit=defineEmits(['saved'])
const {api,status,notify,loadStatus}=useWorkspace(),{draft}=useEvidence(),busy=ref(false)
const dismissing=ref(false),dismissReason=ref('')
const deleting=ref(false)
const portrait=ref(null),chat=ref(null)
const own=computed(()=>props.item.context.filter(m=>props.item.evidence.includes(m.message_id)&&m.user_id===props.item.user_id))
const labels={face:'QQ 表情',reply:'引用消息',image:'图片 · 未识别内容',record:'语音 · 未识别内容',video:'视频 · 未识别内容',json:'卡片摘要',xml:'卡片摘要',forward:'合并转发 · 未展开',file:'文件 · 未读取'}
function media(types){return [...new Set(types)].map(t=>(labels[t]||'其他消息附件')+(types.filter(x=>x===t).length>1?' ×'+types.filter(x=>x===t).length:''))}
function selected(m){return props.item.evidence.includes(m.message_id)&&m.user_id===props.item.user_id}
function record(){
 const value=caseDraft(props.item,status.value?.policies),cached=cachedChatShot(props.item.id)
 if(cached)value.images=[reviveChatShot(cached)]
 else value.pendingShot=(chat.value?.snapshot?.()||Promise.resolve(null)).then(shot=>{if(shot)cacheChatShot(props.item.id,shot);return shot}).catch(e=>{console.warn('聊天截图生成失败',e);return null})
 draft.value=value;location.hash='overview'
}
async function decide(resolution){if(busy.value)return;busy.value=true;try{await api('/api/cases/'+encodeURIComponent(props.item.id)+'/decision',{resolution,note:resolution==='dismissed'?dismissReason.value:undefined});dismissing.value=false;notify(resolution==='dismissed'?'已排除这条线索':resolution?'已保存':'已恢复为待办');await loadStatus();emit('saved')}catch(e){notify(e.message)}finally{busy.value=false}}
async function remove(){if(busy.value)return;busy.value=true;try{await api('/api/cases/'+encodeURIComponent(props.item.id),{},{method:'DELETE'});deleting.value=false;notify('线索已删除');await loadStatus();emit('saved')}catch(e){notify(e.message)}finally{busy.value=false}}
</script>
<template>
<article class="case panel" :class="'state-'+item.state">
<header class="case-head"><span class="case-avatar" aria-hidden="true">{{[...(item.member_name||'?')][0]}}<img v-if="portrait?.avatar" class="case-avatar-image" :src="portrait.avatar" alt="" loading="lazy" decoding="async"><img v-if="portrait?.pendant" class="case-avatar-pendant" :src="portrait.pendant" alt="" loading="lazy" decoding="async"></span><div class="case-title"><h3>{{status?.policies[item.rule]?.[0]||item.rule}}</h3><p class="case-meta">{{item.member_name}} · {{item.group_name}} · {{time(item.created)}}</p></div><span :class="['badge',item.state]">{{states[item.state]||item.state}}</span></header>
<div class="case-verdict"><span class="case-verdict-label"><AppIcon name="sparkle"/>DS 复核意见</span><p class="case-reason-full">{{item.reason||(item.state==='pending'?'正在排队等待 DS 复核。':'DS 没有给出复核理由。')}}</p></div>
<p v-if="item.error" class="case-advice"><AppIcon name="alert"/>{{item.error}}</p>
<ChatContext ref="chat" :item="item" @portrait="portrait=$event"/>
<div class="case-actions"><button class="button primary small" :disabled="busy" @click="record">转入登记 <AppIcon name="arrow"/></button><button v-if="item.resolution" class="button small" :disabled="busy" :aria-expanded="deleting" @click="deleting=!deleting">确认删除</button><button v-else class="button small" :disabled="busy" :aria-expanded="dismissing" @click="dismissing=!dismissing">排除线索</button><button v-if="item.resolution" class="button small subtle" :disabled="busy" @click="decide('')">恢复待办</button><span v-if="item.resolution" class="case-resolution">{{({confirmed:'已登记处理',dismissed:'已排除',follow_up:'继续核查'})[item.resolution]||''}}</span></div>
<div v-if="deleting&&item.resolution" class="decision-feedback"><p>删除这条已处理线索及其聊天资源？已登记档案会保留。</p><div class="case-actions"><button class="button small danger" :disabled="busy" @click="remove">永久删除</button><button class="button small subtle" :disabled="busy" @click="deleting=false">取消</button></div></div>
<form v-if="dismissing" class="decision-feedback" @submit.prevent="decide('dismissed')"><label :for="'dismiss-reason-'+item.id">排除理由 <span>（选填）</span></label><textarea :id="'dismiss-reason-'+item.id" v-model="dismissReason" rows="3" maxlength="2000" :disabled="busy" placeholder="说明判断依据，供后续复核参考"></textarea><div class="case-actions"><button class="button small primary" :disabled="busy">确认排除</button><button type="button" class="button small subtle" :disabled="busy" @click="dismissing=false">取消</button></div></form></article>
</template>
<style scoped>
.case-reason-full{white-space:normal;overflow-wrap:anywhere;margin:0;line-height:1.8}.case>details{margin-top:12px}
.decision-feedback{margin-top:16px;padding:16px;background:var(--surface-3);border-radius:10px}.decision-feedback label{display:block;margin-bottom:8px}.decision-feedback label span{font-size:11px;color:var(--subtle)}.decision-feedback textarea{width:100%;box-sizing:border-box;padding:10px;border:1px solid var(--line);border-radius:8px;background:var(--surface);color:var(--green);font:inherit}
</style>
