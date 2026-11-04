<script setup>
import {computed,ref,watch} from 'vue'
import ModalDialog from '../../../shared/ui/ModalDialog.vue'
import MemberIdentity from '../../../entities/evidence/ui/MemberIdentity.vue'
import PunishmentBadge from '../../../entities/evidence/ui/PunishmentBadge.vue'
import BanLabel from '../../../entities/evidence/ui/BanLabel.vue'
import {recordRemarks} from '../../../entities/evidence/model/records.js'
import {useSession} from '../../../shared/api/session.js'
import {useEvidence} from '../../../entities/evidence/model/state.js'
import {localUrl,fmt} from '../../../shared/lib/format.js'
const props=defineProps({id:String}),emit=defineEmits(['close','edit','member'])
const {api,notify}=useSession(),{records,load,profileFor}=useEvidence()
const record=computed(()=>records.value.find(r=>r.id===props.id)),profile=computed(()=>record.value?profileFor(record.value):{})
const deleting=ref(false),busy=ref(false),error=ref(''),image=ref(null)
watch(()=>props.id,()=>{deleting.value=false;error.value='';image.value=null})
async function remove(){if(busy.value)return;busy.value=true;error.value='';try{await api('/api/records/'+encodeURIComponent(props.id),{},{method:'DELETE',evidence:true});window.dispatchEvent(new Event('workbench-backups-changed'));deleting.value=false;emit('close');notify('档案已删除，删除前已自动备份');await load().catch(()=>{})}catch(e){error.value=e.message}finally{busy.value=false}}
function edit(){emit('edit',record.value)}
</script>
<template>
<ModalDialog id="ev-detail" :open="!!record" label="处理记录" @close="emit('close')"><template v-if="record"><div id="ev-detail-content"><div class="modal-header"><div><h2>处理记录</h2><p>{{record.event_date}}</p></div><button class="icon-button" id="ev-close-detail" aria-label="关闭详情" @click="emit('close')">×</button></div>
<div class="modal-body"><div class="detail-top"><MemberIdentity :record="record" @open="emit('member',$event)"/><button class="button subtle" @click="emit('member',record.id)">个人历史 →</button></div><dl class="detail-grid"><div><dt>违规行为</dt><dd>{{record.reason}}</dd></div><div><dt>处理人</dt><dd>{{record.operator||'未记载'}}</dd></div><div class="decision-fact"><dt>处理结果</dt><dd><time>{{record.event_date}}</time><PunishmentBadge :record="record"/></dd></div><div v-if="recordRemarks(record)" class="remarks-fact"><dt>备注</dt><dd>{{recordRemarks(record)}}</dd></div></dl>
<section v-if="record.ban" class="detail-section"><h3>禁言时间</h3><BanLabel :ban="record.ban"/><p>{{record.ban.basis}}</p></section>
<section class="detail-section"><div class="section-heading"><h3>图片证据 <span>{{record.images.length}} 张</span></h3><button v-if="!record.images.length" class="button subtle" id="ev-add-evidence" @click="edit">补充图片</button></div><div v-if="record.images.length" class="detail-images"><button v-for="(img,i) in record.images" :key="i" @click="image=img"><img :src="localUrl(img.url)" :alt="img.name"></button></div><p v-else class="empty-evidence">还没有图片证据</p></section>

</div>
<div class="modal-footer"><button class="delete-link" id="ev-delete-record" @click="deleting=true;error=''">删除记录</button><button class="button" id="ev-detail-done" @click="emit('close')">关闭</button><button class="button primary" id="ev-edit-record" @click="edit">编辑记录</button></div></div></template></ModalDialog>
<ModalDialog id="ev-confirm-dialog" :open="deleting&&!!record" label="确认删除档案" @close="!busy&&(deleting=false)"><div class="confirm-content"><h2>删除这份档案？</h2><p>这条处理记录及其证据将从档案中移除。删除前会自动备份。</p><div><button class="button" :disabled="busy" @click="deleting=false">保留档案</button><button class="button danger" id="ev-confirm-delete" :disabled="busy" @click="remove">确认删除</button></div><p role="alert">{{error}}</p></div></ModalDialog>
<ModalDialog id="ev-lightbox" :open="!!image" label="证据图片" @close="image=null"><template v-if="image"><button class="lightbox-close" aria-label="关闭图片" @click="image=null">×</button><img id="ev-lightbox-image" :src="localUrl(image.url)" alt="证据原图"></template></ModalDialog>
</template>
<style scoped>
#ev-detail .modal-body{padding-top:0}#ev-detail .detail-top{align-items:center;min-height:96px;margin-bottom:0;padding:16px 0;box-sizing:border-box}#ev-detail .detail-grid{margin-top:0}#ev-detail .detail-top :deep(.member-button){align-items:center}#ev-detail .detail-top :deep(.avatar){align-self:center}
.remarks-fact dd{white-space:pre-wrap;line-height:1.8}.decision-fact dd{display:flex;align-items:center;flex-wrap:wrap;gap:8px}.decision-fact time{margin-right:4px}
</style>
