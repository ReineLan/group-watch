<script setup>
import {computed} from 'vue'
import ModalDialog from '../../../shared/ui/ModalDialog.vue'
import MemberIdentity from '../../../entities/evidence/ui/MemberIdentity.vue'
import {useEvidence} from '../../../entities/evidence/model/state.js'
import {sameMember} from '../../../entities/evidence/model/records.js'
const props=defineProps({id:String}),emit=defineEmits(['close','record'])
const {records,displayName,groupLabel}=useEvidence(),record=computed(()=>records.value.find(r=>r.id===props.id)),history=computed(()=>record.value?records.value.filter(r=>sameMember(r,record.value)).sort((a,b)=>b.event_date.localeCompare(a.event_date)||b.id.localeCompare(a.id)):[])

</script>
<template><ModalDialog id="ev-member-dialog" :open="!!record" label="个人历史" @close="emit('close')"><div v-if="record" id="ev-member-content"><div class="modal-header"><div><span class="eyebrow">MEMBER HISTORY</span><h2>{{displayName(record)}} 的历史档案</h2><p>{{record.member_id||'未记账号'}}</p></div><button class="icon-button" id="ev-close-member" aria-label="关闭个人历史" @click="emit('close')">×</button></div><div class="modal-body"><div class="member-profile"><MemberIdentity :record="record" avatar-only/><div><strong>{{displayName(record)}}</strong><small>账号 {{record.member_id||'未记载'}}</small></div></div><h3 class="history-heading">处理记录 <span>{{history.length}} 条</span></h3><div class="history-list"><button v-for="item in history" :key="item.id" @click="emit('record',item.id);emit('close')"><time>{{item.event_date}}</time><div><strong>{{item.reason}}</strong><p>{{groupLabel(item.group_id)}} · {{item.penalty_text||item.punishment}}</p></div><span>↗</span></button></div></div></div></ModalDialog></template>

<style scoped>
.history-heading{display:flex;align-items:center;gap:10px;margin:22px 0 8px;font-size:13px}.history-heading span{font-size:12px;font-weight:400;color:var(--muted)}
</style>
