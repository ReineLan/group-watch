<script setup>
import {ref,computed,reactive,watch,onMounted,onBeforeUnmount,nextTick} from 'vue'
import {useSession} from '../../../shared/api/session.js'
import {useEvidence} from '../../../entities/evidence/model/state.js'
import {blankFilters,filterRecords} from '../../../entities/evidence/model/records.js'
import {downloadCsv,localDate} from '../../../shared/lib/format.js'
import EvidenceIcon from '../../../shared/ui/EvidenceIcon.vue'
import SearchField from '../../../shared/ui/SearchField.vue'
import PageHeading from '../../../shared/ui/PageHeading.vue'
import MemberIdentity from '../../../entities/evidence/ui/MemberIdentity.vue'
import PunishmentBadge from '../../../entities/evidence/ui/PunishmentBadge.vue'
import BanLabel from '../../../entities/evidence/ui/BanLabel.vue'
import EvidenceSpecial from './EvidenceSpecial.vue'
import RecordEditor from '../../../entities/evidence/ui/RecordEditor.vue'
import RecordDetail from './RecordDetail.vue'
import MemberHistory from './MemberHistory.vue'
import RuleEditor from './RuleEditor.vue'
import ArchiveQuery from './ArchiveQuery.vue'
const {notify}=useSession()
const props=defineProps({view:String,active:Boolean}),emit=defineEmits(['saved'])
const {records,profiles,groups,groupLabel,load,error,loaded,displayName,interacting}=useEvidence()
const filters=reactive(blankFilters()),page=ref(1),moreFilters=ref(),selected=ref(''),member=ref(''),ruleIndex=ref(null),editing=ref(false),editRecord=ref(null),editDraft=ref(null),batch=ref(false)
const queryOpen=ref(false)
const content=ref(null)
const title=computed(()=>({records:'处罚档案',bans:'禁言跟踪',risks:'黑名单与预警',policies:'处理办法',maintenance:'数据与备份'}[props.view]||'处罚档案'))
const eyebrow=computed(()=>({records:'ARCHIVE',bans:'MUTES',risks:'WATCHLIST',policies:'POLICIES'}[props.view]||''))
const filtered=computed(()=>filterRecords(records.value,profiles.value,filters,props.view,groups.value)),pages=computed(()=>Math.max(1,Math.ceil(filtered.value.length/20))),paged=computed(()=>filtered.value.slice((page.value-1)*20,page.value*20))
const extra=computed(()=>[filters.image==='missing'?'待补图片':filters.image==='has'?'已附图片':'',filters.start?'从 '+filters.start:'',filters.end?'至 '+filters.end:''].filter(Boolean)),hasFilters=computed(()=>Object.values(filters).some(Boolean))
watch(filters,()=>page.value=1);watch(pages,n=>page.value=Math.min(page.value,n))
function reset(){Object.assign(filters,blankFilters());page.value=1}
function openEditor(record=null,isBatch=false,value=null){editRecord.value=record;batch.value=isBatch;editDraft.value=value;editing.value=true}
watch(()=>props.view,()=>{reset();if(moreFilters.value)moreFilters.value.open=false})
// These views share one visible container, so display changes cannot restart its CSS entrance.
watch(()=>props.view,()=>{
 if(!props.active)return
 for(const animation of content.value?.getAnimations()||[]){
  if(animation.animationName==='rise'){animation.currentTime=0;animation.play()}
 }
},{flush:'post'})
watch(()=>props.active,async active=>{if(active){if(!loaded.value)await load().catch(()=>{});}},{immediate:true})
watch([editing,selected,member,ruleIndex],()=>{interacting.value=editing.value||!!selected.value||!!member.value||ruleIndex.value!==null},{flush:'sync'})
async function refresh(){await load().catch(()=>{})}
function csv(){
 if(!filtered.value.length)return notify('当前筛选下没有可导出的档案')
 const columns=[['档案编号','id'],['成员昵称','nickname'],['群名片','card'],['成员账号','member_id'],['所属群聊','group_id'],['处理日期','event_date'],['事件经过','reason'],['处罚类型','punishment'],['处罚原文','penalty_text'],['原表次数','occurrence'],['处理人','operator'],['备注','notes']]
 downloadCsv([columns.map(x=>x[0]).concat(['证据文件','禁言状态','禁言开始','禁言结束','时间依据']),...filtered.value.map(r=>columns.map(x=>r[x[1]]).concat([r.images.map(i=>i.name).join('; '),r.ban?.status,r.ban?.start,r.ban?.end,r.ban?.basis]))],`群序-${title.value}-${localDate()}.csv`);notify(`已导出 ${filtered.value.length} 条记录`)
}
function shortcut(e){if(!props.active||interacting.value||e.key!=='/'||['INPUT','TEXTAREA','SELECT'].includes(document.activeElement?.tagName))return;e.preventDefault();if(!['records','bans'].includes(props.view))location.hash='records';nextTick(()=>document.getElementById('ev-search')?.focus())}
onMounted(()=>document.addEventListener('keydown',shortcut));onBeforeUnmount(()=>document.removeEventListener('keydown',shortcut))
defineExpose({refresh})
</script>
<template>

    <div ref="content" id="evidence-workspace" class="evidence-workspace">
        <PageHeading title-id="ev-page-title" :title="title" :eyebrow="eyebrow"/>
        <p id="ev-archive-context" class="archive-context" :hidden="!['records','bans'].includes(view)">{{groups.length===1?groupLabel(groups[0]):''}}</p>
        <section class="records-panel" id="ev-records-panel" :hidden="!['records','bans'].includes(view)">
            <div class="panel-heading">
                <div>
                    <h2 id="ev-list-title">{{view==='bans'?'禁言记录':'全部档案'}} <span id="ev-result-count">{{filtered.length}}</span></h2>

                </div><button class="button subtle" id="ev-export" @click="csv"><EvidenceIcon name="download"/>导出 CSV</button>
            </div>
            <div class="filterbar archive-filterbar"><button v-if="view==='records'" class="archive-query-toggle" type="button" :aria-expanded="queryOpen" aria-controls="archive-query-panel" @click="queryOpen=!queryOpen"><span aria-hidden="true">{{queryOpen?'▾':'▸'}}</span> AI</button><SearchField id="ev-search" v-model="filters.search" placeholder="搜索 QQ 号、昵称或事件经过" label="搜索档案" shortcut/><select
                    id="ev-group-filter" v-model="filters.group" aria-label="筛选群聊"><option v-for="group in groups" :key="group" :value="group">{{groupLabel(group)}}</option>
                    <option value="">全部群聊</option>
                </select><select id="ev-type-filter" v-model="filters.type" aria-label="筛选处罚类型" :hidden="view==='bans'">
                    <option value="">全部处罚</option>
                    <option>警告</option>
                    <option>禁言</option>
                    <option>移出群聊</option>
                    <option>其他</option>
                </select><select id="ev-status-filter" v-model="filters.status" aria-label="禁言状态" :hidden="view!=='bans'">
                    <option value="">全部状态</option>
                    <option value="active">当前禁言</option>
                    <option>进行中</option>
                    <option>已结束</option>
                    <option>永久禁言</option>
                    <option>未注明结束</option>
                    <option>未开始</option>
                    <option>待核实</option>
                </select><button class="button subtle" id="ev-reset" :hidden="!hasFilters" @click="reset">清除筛选</button></div>

            <div v-if="extra.length||(filters.start&&filters.end&&filters.start>filters.end)" id="ev-active-filters"><span v-if="filters.start&&filters.end&&filters.start>filters.end" class="range-error">开始日期不能晚于结束日期</span><span v-for="text in extra" :key="text" class="filter-chip">{{text}}</span></div>
            <div v-if="view==='records'" v-show="queryOpen" id="archive-query-panel" class="archive-query"><ArchiveQuery @member="member=$event" @record="selected=$event"/></div>
            <div class="table-wrap">
                <table>
                    <thead>
                        <tr>
                            <th>成员 / 群聊</th>
                            <th>行为与处理</th>
                            <th>处理日期</th>
                            <th id="ev-fourth-column">{{view==='bans'?'禁言起止（北京时间）':'图片证据'}}</th>
                            <th><span class="sr-only">操作</span></th>
                        </tr>
                    </thead>
                    <tbody id="ev-record-list"><tr v-for="record in paged" :key="record.id" :data-record="record.id" @click="selected=record.id"><td><MemberIdentity :record="record" @click.stop @open="member=$event"/></td><td><span class="reason-text" :title="record.reason">{{record.reason}}</span><PunishmentBadge :record="record"/></td><td class="date-cell">{{record.event_date}}</td><td><BanLabel v-if="view==='bans'" :ban="record.ban"/><span v-else class="evidence-count"><template v-if="record.images.length">{{record.images.length}} 张</template><span v-else class="badge">—</span></span></td><td><button class="row-open" :aria-label="'查看 '+displayName(record)+' 的档案'">详情 →</button></td></tr></tbody>
                </table>
            </div>
            <div id="ev-empty-state" class="empty-state" :hidden="!loaded||filtered.length>0">
                <div class="empty-art"><EvidenceIcon name="archive"/><span class="art-check">✓</span></div>
                <h3>没有找到匹配的档案</h3>
                <p>换个关键词，或者清除筛选再看看。</p><button class="button" id="ev-empty-reset" @click="reset">清除筛选</button>
            </div>
            <div id="ev-error-state" class="error-state" :hidden="!error">档案暂时读取失败。<button id="ev-retry" @click="refresh">重新加载</button></div>
            <div class="panel-footer">
                <div class="pagination"><button id="ev-previous" aria-label="上一页" :disabled="page===1" @click="page--">←</button><span id="ev-page-number">{{page}} / {{pages}}</span><button id="ev-next" aria-label="下一页" :disabled="page===pages" @click="page++">→</button></div>
            </div>
        </section>
        <EvidenceSpecial v-if="['risks','policies','maintenance'].includes(view)" :view="view" @member="member=$event" @record="selected=$event" @rule="ruleIndex=$event"/>
<RecordDetail :id="selected" @close="selected=''" @edit="openEditor($event)" @member="member=$event"/>
<MemberHistory :id="member" @close="member=''" @record="selected=$event"/>
<RecordEditor v-if="editing" :open="editing" :record="editRecord" :batch="batch" :draft="editDraft" @close="editing=false" @saved="emit('saved',$event)"/>
<RuleEditor :index="ruleIndex" @close="ruleIndex=null"/>


    </div>
</template>

<style scoped>
.archive-query-toggle{height:42px;display:flex;align-items:center;gap:8px;padding:0 6px;border:0;border-radius:4px;background:transparent;color:var(--green);font:inherit;font-size:13px;white-space:nowrap;cursor:pointer}.archive-query-toggle[aria-expanded=true]{background:var(--surface-3)}.archive-filterbar{align-items:center;border-bottom:0}.archive-query{margin:0 20px 18px}.archive-query :deep(.query-panel){border:0;padding:0;margin:0;box-shadow:none;background:transparent}.archive-query :deep(#query-form){display:flex;gap:10px;align-items:center}.archive-query :deep(#query-input){min-height:42px;height:42px;flex:1;min-width:0;resize:none;padding:0 11px;margin:0;border:0;border-radius:0;background:transparent;font:inherit;color:var(--green)}.archive-query :deep(.query-actions){margin:0;display:flex;gap:6px}.archive-query :deep(#query-status:empty),.archive-query :deep(#query-answer:empty){display:none}
</style>
