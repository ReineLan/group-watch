<script setup>
import {computed,ref,watch} from 'vue'
import {useEvidence} from '../../../entities/evidence/model/state.js'
import {norm} from '../../../entities/evidence/model/records.js'
import {fmt} from '../../../shared/lib/format.js'
import ModalDialog from '../../../shared/ui/ModalDialog.vue'
import {useSession} from '../../../shared/api/session.js'
import MemberIdentity from '../../../entities/evidence/ui/MemberIdentity.vue'
import SearchField from '../../../shared/ui/SearchField.vue'
import SelectBox from '../../../shared/ui/SelectBox.vue'
defineProps({view:String})
const emit=defineEmits(['member','record','rule'])
const {rules,records,overview,displayName,profileFor,groupLabel,load}=useEvidence(),search=ref(''),status=ref('')
const risks=computed(()=>{const q=norm(search.value);return overview.value.risks.filter(r=>(!q||[r.nickname,profileFor(r).nickname,r.member_id,r.group_id].some(x=>norm(x).includes(q)))&&(!status.value||r.status===status.value)).sort((a,b)=>(a.status==='再犯预警'?0:1)-(b.status==='再犯预警'?0:1)||latest(b).localeCompare(latest(a))||String(a.member_id).localeCompare(String(b.member_id),undefined,{numeric:true}))})
const isRedPacket=r=>r.record_ids.length>0&&r.record_ids.every(id=>{const row=records.value.find(x=>x.id===id);return row&&/抢红包外挂/.test(row.reason)})
const ordinaryRisks=computed(()=>risks.value.filter(r=>!isRedPacket(r))),redPacketRisks=computed(()=>risks.value.filter(isRedPacket))
function latest(r){return records.value.filter(x=>r.record_ids.includes(x.id)).map(x=>x.event_date+'|'+x.id).sort().at(-1)||''}
function auditRecord(id){return records.value.find(r=>r.id===id)}
function openRisk(r){if(r.record_ids?.[0])emit('member',r.record_ids[0])}
const {api,notify}=useSession(),rollbackTarget=ref(null),working=ref(false),operationError=ref('')
async function rollback(){
 if(working.value||!rollbackTarget.value)return
 working.value=true;operationError.value=''
 try{await api('/api/rollback',{backup:rollbackTarget.value.backup},{evidence:true,signal:AbortSignal.timeout(180000)});rollbackTarget.value=null;await load();window.dispatchEvent(new Event('workbench-backups-changed'));notify('已恢复所选备份')}
 catch(error){operationError.value=error.message}finally{working.value=false}
}
async function downloadBackup(){
 if(working.value)return
 working.value=true;operationError.value=''
 try{const result=await api('/api/maintenance/backup',{}, {signal:AbortSignal.timeout(180000)});const link=document.createElement('a');link.href=result.url;link.download=result.name;link.click();await load();window.dispatchEvent(new Event('workbench-backups-changed'));notify('新备份已生成，正在下载')}
 catch(error){operationError.value=error.message}finally{working.value=false}
}

</script>
<template>
<section id="ev-special-panel">
<div v-if="view==='policies'" class="records-panel"><div class="panel-heading"><h2>处理办法 <span>{{rules.length}} 类</span></h2></div><div class="table-wrap"><table class="rules-table"><thead><tr><th>违规行为</th><th>第一次</th><th>第二次</th><th>第三次及以后</th><th>备注</th></tr></thead><tbody id="ev-rules-list"><tr v-for="(r,i) in rules" :key="i" class="editable-rule" tabindex="0" @dblclick="emit('rule',i)" @keydown.enter="emit('rule',i)"><td>{{r.reason}}</td><td>{{r.steps[0]||'—'}}</td><td>{{r.steps[1]||'—'}}</td><td><template v-for="(step,n) in r.steps.slice(2)" :key="n">{{n?'第'+(n+3)+'次：':''}}{{step||'—'}}<br v-if="n<r.steps.length-3"></template><template v-if="r.steps.length<3">—</template></td><td>{{r.notes||'—'}}</td></tr></tbody></table></div><p v-if="!rules.length" class="empty-state">没有匹配的规则</p></div>
<div v-else-if="view==='risks'" class="records-panel"><div class="panel-heading"><div><h2>黑名单与预警 <span>{{overview.risks.length}}</span></h2></div></div><div class="filterbar"><SearchField id="ev-risk-search" v-model="search" label="查询黑名单成员" placeholder="搜索 QQ 号、昵称或群聊"/><SelectBox id="ev-risk-status" v-model="status" aria-label="筛选黑名单状态" :options="[{value:'',label:'全部状态'},'已记录移出','达到移出规则','再犯预警']"/></div><div id="ev-risk-list" class="risk-grid"><article v-for="r in ordinaryRisks" :key="r.group_id+'|'+r.nickname_id+'|'+r.nickname" class="risk-card" role="button" tabindex="0" aria-label="查看个人历史" @click="openRisk(r)" @keydown.enter.self.prevent="openRisk(r)" @keydown.space.self.prevent="openRisk(r)"><div><span class="badge" :class="r.status==='再犯预警'?'warning':'remove'">{{r.status}}</span><small>{{r.total}} 条历史记录</small></div><div class="risk-person"><MemberIdentity :record="r" avatar-only/><h3>{{displayName(r)}}</h3></div><p>账号 {{r.member_id||'未记载'}} · {{groupLabel(r.group_id)}}</p><ul><li v-for="(ground,i) in r.grounds" :key="i">{{ground}}</li></ul><span class="button subtle risk-history" aria-hidden="true">个人历史 →</span></article><details v-if="redPacketRisks.length" class="red-packet-group"><summary>抢红包外挂 · {{redPacketRisks.length}} 人</summary><div class="risk-grid"><article v-for="r in redPacketRisks" :key="r.group_id+'|'+r.nickname_id+'|'+r.nickname" class="risk-card" role="button" tabindex="0" aria-label="查看个人历史" @click="openRisk(r)" @keydown.enter.self.prevent="openRisk(r)" @keydown.space.self.prevent="openRisk(r)"><div><span class="badge" :class="r.status==='再犯预警'?'warning':'remove'">{{r.status}}</span><small>{{r.total}} 条历史记录</small></div><div class="risk-person"><MemberIdentity :record="r" avatar-only/><h3>{{displayName(r)}}</h3></div><p>账号 {{r.member_id||'未记载'}} · {{groupLabel(r.group_id)}}</p><ul><li v-for="(ground,i) in r.grounds" :key="i">{{ground}}</li></ul><span class="button subtle risk-history" aria-hidden="true">个人历史 →</span></article></div></details><div v-if="!risks.length" class="empty-state">暂无匹配的成员</div></div></div>
<template v-else-if="view==='maintenance'">

<div class="records-panel data-section"><div class="panel-heading"><h2>最近操作</h2></div><div class="audit-list"><div v-for="(x,i) in overview.audit.slice(0,50)" :key="i"><time>{{fmt(x.at)}}</time><strong>{{x.action}}</strong><div v-if="auditRecord(x.record_id)||x.backup" class="audit-actions"><button v-if="auditRecord(x.record_id)" class="audit-record" @click="emit('record',x.record_id)">{{displayName(auditRecord(x.record_id))}} · {{auditRecord(x.record_id).event_date}} ↗</button><button v-if="x.backup" class="button small" title="撤销此次及后续操作" :disabled="working" @click="operationError='';rollbackTarget=x">撤销</button></div></div><p v-if="!overview.audit.length">还没有操作记录</p></div></div>
<article class="info-card backup-card"><div><h2>完整备份</h2><p>包含全部档案、证据原图和留存的昵称头像，可用于迁移或恢复。</p></div><button class="button primary" :disabled="working" @click="downloadBackup">{{working?'正在处理…':'下载备份 ↓'}}</button></article>
<p v-if="operationError&&!rollbackTarget" role="alert">{{operationError}}</p>
<ModalDialog id="ev-rollback" :open="!!rollbackTarget" label="撤销留证操作" @close="!working&&(rollbackTarget=null)"><div class="modal-header"><h2>撤销留证操作</h2></div><div class="modal-body"><p>将全部留证档案、处理规则和昵称头像恢复到 {{fmt(rollbackTarget?.at)}} 的备份状态。后续登记和修改将撤回。</p><p v-if="operationError" role="alert">{{operationError}}</p></div><div class="modal-footer"><button class="button" :disabled="working" @click="rollbackTarget=null">取消</button><button class="button primary" :disabled="working" @click="rollback">{{working?'正在撤销…':'恢复所选备份'}}</button></div></ModalDialog>
</template>
</section>
</template>

<style scoped>
.audit-list>div{align-items:center}.audit-list>div>time,.audit-list>div>strong{align-self:center}.audit-actions{display:flex;align-items:center;justify-content:flex-start;gap:8px;min-width:0}.audit-actions .audit-record{min-width:0}.audit-list{max-height:360px;overflow-y:auto;overscroll-behavior:contain}.red-packet-group{grid-column:1/-1;border-top:1px solid var(--line);padding-top:16px}.red-packet-group>summary{cursor:pointer;color:var(--green);padding:10px 0}.red-packet-group[open]>.risk-grid{margin-top:12px}

#ev-special-panel .rules-table{width:100%;min-width:720px;table-layout:fixed}#ev-special-panel .rules-table th,#ev-special-panel .rules-table td{min-width:0;max-width:none;height:auto;box-sizing:border-box;text-align:left;vertical-align:top;padding:14px 16px;line-height:1.7;white-space:normal;overflow-wrap:anywhere}#ev-special-panel .rules-table th:first-child{width:24%}#ev-special-panel .rules-table th:nth-child(2),#ev-special-panel .rules-table th:nth-child(3){width:16%}#ev-special-panel .rules-table th:nth-child(4){width:22%}#ev-special-panel .rules-table th:last-child{width:22%}#ev-special-panel .rules-table tbody tr{height:auto}.backup-card{margin-top:20px}
@media(max-width:1100px){
#ev-special-panel .audit-list>div{grid-template-columns:140px minmax(0,1fr);grid-auto-rows:auto;align-content:center;align-items:center;min-height:64px;padding:16px 0;gap:12px 16px}
#ev-special-panel .audit-list>div>time,#ev-special-panel .audit-list>div>strong{white-space:nowrap;margin:0;line-height:1.5}
#ev-special-panel .audit-actions{grid-column:1/-1;display:grid;grid-template-columns:140px minmax(0,1fr);min-width:0;width:100%;gap:16px}
#ev-special-panel .audit-actions .audit-record{grid-column:1;grid-row:1;justify-self:start;text-align:left;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;line-height:1.5}
#ev-special-panel .audit-actions .button{grid-column:2;grid-row:1;justify-self:start;flex-shrink:0;margin:0}
}
</style>
