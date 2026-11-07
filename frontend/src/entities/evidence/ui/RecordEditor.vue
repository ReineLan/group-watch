<script setup>
import {reactive,ref,computed,watch,nextTick,onMounted,onBeforeUnmount} from 'vue'
import ModalDialog from '../../../shared/ui/ModalDialog.vue'
import EvidenceIcon from '../../../shared/ui/EvidenceIcon.vue'
import {useSession} from '../../../shared/api/session.js'
import {useEvidence} from '../model/state.js'
import {buildRecordPayload,recordRemarks} from '../model/records.js'
import {localDate,localUrl} from '../../../shared/lib/format.js'
import {registrationDate} from '../model/registrationDate.js'
const props=defineProps({open:Boolean,record:Object,batch:Boolean,draft:Object}),emit=defineEmits(['close','saved'])
const {api,notify}=useSession(),{groups,groupLabel,rules,load}=useEvidence()
const previewImage=ref(null)
const form=reactive({}),uploads=ref([]),batchText=ref(''),busy=ref(false),error=ref(''),files=ref(),dragging=ref(false)
const groupOptions=computed(()=>groups.value)
const categoryOptions=computed(()=>[...new Set([...rules.value.map(rule=>rule.reason),form.reason].filter(Boolean))])
const analyzing=ref(false),analysisError=ref(''),aiRows=ref([]),personIndex=ref(0)
const analysis=computed(()=>aiRows.value[personIndex.value]?.analysis)
const dateEdited=ref(false)
let analysisController
let initialDecision='',session=0
onMounted(()=>document.addEventListener('paste',pasteImages))
onBeforeUnmount(()=>{session++;analysisController?.abort();document.removeEventListener('paste',pasteImages)})
function pasteImages(event){
 if(!props.open||previewImage.value||busy.value||analyzing.value)return
 const items=[...(event.clipboardData?.items||[])].filter(item=>item.kind==='file'&&item.type.startsWith('image/')).map(item=>item.getAsFile()).filter(Boolean)
 const images=items.length?items:[...(event.clipboardData?.files||[])].filter(file=>file.type.startsWith('image/'))
 if(!images.length)return
 event.preventDefault();addFiles(images)
}
const fields=['id','member_id','nickname','card','group_id','event_date','reason','punishment','operator','notes','occurrence','penalty_text','decision_detail']
function close(){if(!busy.value)emit('close')}
watch(()=>props.open,open=>{
 previewImage.value=null;session++;analysisController?.abort();analyzing.value=false;aiRows.value=[];personIndex.value=0;analysisError.value=''
 if(!open)return
 for(const key of fields)form[key]=['nickname','card'].includes(key)?null:''
 dateEdited.value=false;form.event_date=localDate();form.group_id=localStorage.getItem('group-evidence-group')||'';localStorage.removeItem('group-evidence-operator')
 for(const [key,value] of Object.entries(props.record||props.draft||{}))if(fields.includes(key))form[key]=value
 if(form.operator==='原表未记载')form.operator=''
 uploads.value=(props.record?.images||props.draft?.images||[]).map(i=>({...i}));batchText.value='';error.value=''
 const pendingShot=props.draft?.pendingShot,at=session
 if(pendingShot)Promise.resolve(pendingShot).then(shot=>{if(shot&&at===session&&uploads.value.length<8)uploads.value.push(shot)})
 form.notes=props.record?recordRemarks(props.record):props.draft?.notes||''
 if(props.draft?.autoAnalyze)nextTick(()=>analyzeImages())
 initialDecision=props.record?(props.record.penalty_text||''):'';form.decision_detail=initialDecision
},{immediate:true})

function stashPerson(){if(aiRows.value.length)Object.assign(aiRows.value[personIndex.value],{form:{...form},dateEdited:dateEdited.value})}
function selectPerson(index){stashPerson();personIndex.value=index;Object.assign(form,aiRows.value[index].form);dateEdited.value=aiRows.value[index].dateEdited}
function removePerson(){if(busy.value||analyzing.value||aiRows.value.length<2)return;aiRows.value.splice(personIndex.value,1);personIndex.value=Math.min(personIndex.value,aiRows.value.length-1);Object.assign(form,aiRows.value[personIndex.value].form);dateEdited.value=aiRows.value[personIndex.value].dateEdited}
function shareDecision(){stashPerson();for(const row of aiRows.value)for(const key of ['punishment','decision_detail','operator'])row.form[key]=form[key];notify('处理决定已用于所有人，仍可逐人调整')}
async function analyzeImages(){
 if(analyzing.value||busy.value)return
 const current=session;analyzing.value=true;analysisError.value='';analysisController=new AbortController()
 const timer=setTimeout(()=>analysisController.abort(),300000)
 try{
  const result=await api('/api/registration/analyze',{images:uploads.value.map(({name,data})=>({name,data})),case_id:props.draft?.case_id||'',context:form.notes||''},{signal:analysisController.signal})
  if(current!==session)return
  aiRows.value=result.people.map(person=>({analysis:{explanation:person.explanation,decision_detail:person.decision_detail},dateEdited:dateEdited.value,form:{...form,id:'',member_id:person.member_id,nickname:person.nickname,card:person.card??null,group_id:person.group_id,event_date:registrationDate(dateEdited.value?form.event_date:'',person.event_date),reason:person.reason,punishment:form.punishment||person.punishment||'',decision_detail:form.decision_detail||''}}))
  personIndex.value=0;Object.assign(form,aiRows.value[0].form)
 }catch(e){if(current===session)analysisError.value=e.name==='AbortError'?'分析已停止或超时，表单内容已保留，可重试。':e.message}
 finally{clearTimeout(timer);if(current===session)analyzing.value=false}
}
async function addFiles(list){
 if(busy.value||analyzing.value)return
 const current=session;busy.value=true;error.value=''
 try{for(const file of list){if(uploads.value.length>=8)throw new Error('最多上传 8 张图片');if(!['image/png','image/jpeg','image/webp'].includes(file.type))throw new Error('请选择 PNG、JPG 或 WebP 图片');if(file.size>5*1024*1024)throw new Error('每张图片最大 5 MB');const preview=await new Promise((resolve,reject)=>{const reader=new FileReader();reader.onload=()=>resolve(reader.result);reader.onerror=()=>reject(new Error('图片读取失败'));reader.readAsDataURL(file)});if(current===session)uploads.value.push({name:form.event_date.replaceAll('-','').slice(2)+'-'+(uploads.value.length+1)+'.'+({'image/png':'png','image/jpeg':'jpg','image/webp':'webp'}[file.type]),original_name:file.name,data:preview.split(',')[1],preview})}}
 catch(e){error.value=e.message}finally{busy.value=false;if(files.value)files.value.value=''}
}
async function save(){
 if(busy.value||analyzing.value)return;busy.value=true;error.value=''
 try{stashPerson();if(aiRows.value.length>1){const missing=aiRows.value.findIndex(row=>!['group_id','event_date','punishment','reason'].every(key=>String(row.form[key]||'').trim())||!String(row.form.member_id||'').trim());if(missing>=0){selectPerson(missing);throw new Error('请补齐第 '+(missing+1)+' 人的成员、日期和处理决定')}}const payload=aiRows.value.length>1?{records:aiRows.value.map(row=>buildRecordPayload(row.form,uploads.value,''))}:buildRecordPayload(form,uploads.value,initialDecision,props.batch?batchText.value:undefined);const result=await api(props.batch||aiRows.value.length>1?'/api/batch':'/api/records',payload,{evidence:true});const ids=Array.isArray(result.ids)?result.ids.filter(Boolean):(result.id?[result.id]:[]);const caseId=props.record?'':(props.draft?.case_id||'');localStorage.setItem('group-evidence-group',form.group_id);window.dispatchEvent(new Event('workbench-backups-changed'));emit('saved',{id:result.id,ids,caseId});emit('close');if(!caseId)notify('档案已保存');await load().catch(()=>{})}
 catch(e){error.value=e.message}finally{busy.value=false}
}
</script>
<template>
        <ModalDialog id="ev-editor" :open="open" label="编辑处罚档案" @close="close">
            <form id="ev-record-form" @submit.prevent="save">
                <div class="modal-header">
                    <div><span class="eyebrow" hidden></span>
                        <h2 id="ev-editor-title">{{batch?'批量登记':record?'编辑档案':'登记处理'}}</h2>
                    </div><button type="button" class="icon-button close-editor" @click="close" aria-label="关闭编辑">×</button>
                </div>
                <div class="modal-body"><input type="hidden" name="record_id" v-model="form.id" :disabled="busy||analyzing">
                    <section class="entry-section evidence-upload-section">
                        <div class="section-heading"><h3>图片证据 <small id="ev-upload-count">{{uploads.length}} / 8</small></h3><button v-if="!record&&!batch" type="button" class="button primary small" :disabled="busy||analyzing||(!uploads.length&&!draft?.case_id)" @click="analyzeImages">{{analyzing?'正在识别…':'自动识别'}}</button></div><div class="drop-zone" @click="files.click()"
                            id="ev-drop-zone" :class="{dragover:dragging,populated:uploads.length}" @dragenter.prevent="dragging=true" @dragover.prevent="dragging=true" @dragleave.prevent="dragging=false" @drop.prevent="dragging=false;addFiles($event.dataTransfer.files)" @keydown.enter.self.prevent="files.click()" @keydown.space.self.prevent="files.click()" :tabindex="uploads.length?-1:0" :role="uploads.length?'group':'button'" :aria-label="uploads.length?'证据图片':'上传证据图片'"><input id="ev-file-input"
                                type="file" ref="files" :disabled="busy||analyzing" @change="addFiles($event.target.files)" accept="image/png,image/jpeg,image/webp" multiple hidden><template v-if="!uploads.length"><EvidenceIcon name="upload"/><strong>点击上传、拖入或直接粘贴图片</strong><span>PNG、JPG、WebP · 每张最多 5 MB</span></template>
                        <div v-if="uploads.length" id="ev-upload-previews" class="upload-previews"><div v-for="(image,i) in uploads" :key="i" class="upload-item" @click.stop @keydown.stop><img :src="localUrl(image.preview||image.url)" :alt="image.name" role="button" tabindex="0" aria-label="放大证据图片" @click.stop="previewImage=image" @keydown.enter.prevent="previewImage=image" @keydown.space.prevent="previewImage=image"><button type="button" :disabled="busy||analyzing" :aria-label="'移除 '+image.name" @click.stop="uploads.splice(i,1)" @keydown.stop>×</button></div><button v-if="uploads.length<8" type="button" class="upload-add" :disabled="busy||analyzing" aria-label="添加证据图片" @click.stop="files.click()" @keydown.stop>＋</button></div></div>
<p v-if="analysisError" class="analysis-error" role="alert">{{analysisError}}</p>
                    </section>
                    <section v-if="analysis" class="registration-analysis" aria-label="识别结果与建议"><p v-if="analysis.explanation">{{analysis.explanation}}</p><p v-if="analysis.decision_detail" class="handling-advice"><strong>处理建议：</strong>{{analysis.decision_detail}}</p></section>
                    <div v-if="aiRows.length>1" class="analysis-people"><div role="tablist" aria-label="涉及人员"><button v-for="(row,i) in aiRows" :key="i" type="button" role="tab" :aria-selected="personIndex===i" :class="{active:personIndex===i}" @click="selectPerson(i)">{{i+1}} · {{row.form.nickname??(row.form.member_id||'待确认人员')}}</button></div><button type="button" class="text-link" @click="shareDecision">将本次处理决定用于所有人</button></div>
                    <button v-if="aiRows.length>1" type="button" class="text-link" :disabled="busy||analyzing" @click="removePerson">从本次登记移除当前人员</button>
                    <p v-if="draft?.case_id" class="draft-notice">已关联线索原文。核对无误后选择处理决定，再保存。</p><section class="entry-section">
                        <h3>成员与处理</h3>
                        <div class="form-grid" id="ev-single-member" :hidden="batch"><label>成员账号 / QQ<input name="member_id" v-model="form.member_id" :disabled="busy||analyzing"
                                    maxlength="100" placeholder="输入成员账号"></label><label>昵称<input name="nickname" v-model="form.nickname" :disabled="busy||analyzing" maxlength="100"
                                    placeholder="自动获取昵称"></label></div>
                        <label class="block-label" id="ev-batch-members-label" :hidden="!batch">成员名单 <em>*</em><textarea
                                id="ev-batch-members" v-model="batchText" :disabled="busy||analyzing" rows="4" placeholder="每行一人：QQ号 昵称（选填）"></textarea><small>最多 50
                                人，共用本次事件、处理决定与证据。</small></label>
                        <div class="form-grid"><label>所属群聊 <em>*</em><select name="group_id" v-model="form.group_id" :disabled="busy||analyzing" required><option value="" disabled>请选择群聊</option><option v-for="group in groupOptions" :key="group" :value="group">{{groupLabel(group)}}</option></select></label><label>行为分类 <em>*</em><input name="reason" v-model="form.reason" list="ev-reason-options" :disabled="busy||analyzing" maxlength="10000" placeholder="选择或填写具体行为" required><datalist id="ev-reason-options"><option v-for="category in categoryOptions" :key="category" :value="category"/></datalist></label></div>
                        <div class="form-grid"><label>处理日期 <em>*</em><input name="event_date" v-model="form.event_date" @input="dateEdited=true" :disabled="busy||analyzing" type="date" required></label><label>处理人<input name="operator" v-model="form.operator" :disabled="busy||analyzing" maxlength="100" placeholder="管理员昵称"></label></div>
                        <div class="form-grid"><label>处罚类型 <em>*</em><select name="punishment" v-model="form.punishment" :disabled="busy||analyzing" required>
                                    <option value="" disabled>请选择处理决定</option>
                                    <option>警告</option>
                                    <option>禁言</option>
                                    <option>移出群聊</option>
                                    <option>其他</option>
                                </select></label><label>时长 / 处理说明<input
                                    name="decision_detail" v-model="form.decision_detail" :disabled="busy||analyzing" maxlength="1000" placeholder="如：禁言3天、永久"></label></div>
                        <label class="block-label">备注<textarea name="notes" v-model="form.notes" :disabled="busy||analyzing" rows="3" maxlength="10000" placeholder="补充事件详情或处理说明"></textarea></label>
                    </section>
                    <p id="ev-form-error" role="alert">{{error}}</p>
                </div>
                <div class="modal-footer"><button type="button" class="button close-editor" @click="close">取消</button><button
                        type="submit" class="button primary" id="ev-save-button" :disabled="busy||analyzing">{{aiRows.length>1?'保存 '+aiRows.length+' 人记录':'保存档案'}}</button></div>
            </form>
        </ModalDialog>
<ModalDialog id="ev-editor-lightbox" :open="!!previewImage" label="证据原图" @close="previewImage=null"><template v-if="previewImage"><img :src="localUrl(previewImage.preview||previewImage.url)" alt="证据原图"></template></ModalDialog>
</template>

<style scoped>
.registration-analysis{margin:18px 0 22px;padding:16px;border:1px solid var(--line-2);border-radius:10px;background:var(--surface-2)}.registration-analysis p{white-space:pre-wrap;overflow-wrap:anywhere;line-height:1.8}.registration-analysis .handling-advice{margin-top:10px;color:var(--muted)}
#ev-record-form .form-grid label,#ev-record-form .block-label{font-size:13px;line-height:20px}#ev-record-form .form-grid input,#ev-record-form .form-grid select{box-sizing:border-box;height:46px;min-height:46px;margin-top:7px;padding:12px;font-family:inherit;font-size:14px;line-height:20px}
#ev-editor-lightbox{width:fit-content;min-width:0;height:fit-content;margin:auto;box-shadow:none;border:0;background:transparent;padding:0;max-width:95vw;max-height:95vh;overflow:visible}#ev-editor-lightbox::backdrop{background:color-mix(in srgb,var(--scrim) 90%,transparent)}#ev-editor-lightbox>img{display:block;margin:auto;width:auto;height:auto;max-width:92vw;max-height:90vh;object-fit:contain}.upload-item img[role=button]{cursor:zoom-in}

.evidence-upload-section{margin-top:0!important;padding-top:0!important}.evidence-upload-section .section-heading{margin-bottom:12px}.evidence-upload-section h3{gap:10px;margin:0!important}.evidence-upload-section .drop-zone{background:linear-gradient(135deg,var(--surface-2),var(--surface-3));border:1px dashed var(--line-3);border-radius:12px;min-height:116px;transition:background .15s,border-color .15s}.evidence-upload-section .drop-zone.dragover{background:var(--surface-3);border-color:var(--accent)}.upload-previews:empty{display:none}.evidence-upload-section .drop-zone{padding:20px;cursor:pointer}.evidence-upload-section .drop-zone.populated{display:block;min-height:0;padding:0;border:0;background:transparent;border-radius:0;cursor:default}.evidence-upload-section .drop-zone.populated.dragover{outline:2px dashed var(--line-3);outline-offset:6px;border-radius:8px}.evidence-upload-section .upload-previews{width:100%;display:grid;grid-template-columns:repeat(auto-fill,minmax(128px,1fr));gap:12px;margin:0}.evidence-upload-section .upload-item{position:relative;width:auto;min-width:0;background:var(--surface-2);border:1px solid var(--line-1);border-radius:10px;overflow:hidden}.evidence-upload-section .upload-item img{width:100%;height:144px;object-fit:contain;display:block;border:0;border-radius:0}.evidence-upload-section .upload-item button{position:absolute;top:6px;right:6px;width:24px;height:24px;padding:0;border-radius:50%;border:1px solid var(--line-1);background:color-mix(in srgb,var(--surface) 95%,transparent);color:var(--ink-2);cursor:pointer;box-shadow:0 1px 4px color-mix(in srgb,var(--shadow) 8%,transparent)}.evidence-upload-section .upload-add{display:grid;place-items:center;height:146px;border:1px dashed var(--line-2);border-radius:10px;background:var(--surface-2);color:var(--subtle);font:300 27px sans-serif;cursor:pointer}.evidence-upload-section .upload-add:hover{background:var(--surface-3);border-color:var(--line-3)}.evidence-upload-section .upload-add:focus-visible{outline:3px solid var(--line-3);outline-offset:3px}.analysis-error{color:var(--danger);font-size:12px;line-height:1.7;margin:10px 0}.analysis-people{margin:20px 0;padding:12px;background:var(--surface-2);border-radius:10px}.analysis-people [role=tablist]{display:flex;flex-wrap:wrap;gap:6px;margin-bottom:10px}.analysis-people [role=tab]{padding:8px 10px;border:1px solid var(--line-2);border-radius:6px;background:var(--surface);color:var(--muted);cursor:pointer}.analysis-people [role=tab].active{background:var(--accent);border-color:var(--accent);color:var(--on-accent)}.analysis-people>.text-link{font-size:11px}@media(max-width:480px){.evidence-upload-section .upload-previews{grid-template-columns:repeat(2,minmax(0,1fr))}.evidence-upload-section .upload-item img{height:128px}.evidence-upload-section .upload-add{height:130px}}
</style>
