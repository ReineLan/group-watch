<script setup>
import {reactive,ref,watch} from 'vue'
import {useWorkspace} from '../../../entities/monitor/model/workspace.js'
import FeedbackPanel from './FeedbackPanel.vue'
import WhitelistPanel from './WhitelistPanel.vue'
import PageHeading from '../../../shared/ui/PageHeading.vue'
const props=defineProps({active:Boolean}),{api,status,loadStatus}=useWorkspace()
const form=reactive({}),editing=ref(''),value=ref(''),loaded=ref(false),busy=ref(false),feedback=ref(''),failed=ref(false)
const vFocus={mounted:el=>el.focus()}
const groups=[
 {key:'filter',label:'候选筛选',fields:[['flood_seconds','刷屏统计窗口','秒',5,120,'只统计同一群内同一成员的消息。'],['flood_count','窗口内发言达到','条',3,100,'不要求内容相同；达到后生成刷屏候选，交给 DS 复核。'],['repeat_count','120 秒内相同内容达到','条',3,100,'同群同一成员；忽略空白和大小写，不比较纯图片。与刷屏窗口分开统计。'],['blocked_words','违禁词']]},
 {key:'retention',label:'数据保留',fields:[['retention_days','原始消息保留','天',1,365,'到期自动清理原始消息；线索快照和处罚档案不受影响。']]},
 {key:'ds',label:'DS 复核',fields:[['query_calls_hour','每小时调用上限','次',1,1000,'最近 60 分钟内，仅自动复核使用这个额度，失败的调用也计入；人工反馈整理、主动识图和档案查询不受上限限制，也不占额度。'],['batch_size','每批最多复核','条',1,10,'一次请求最多带上这么多条候选；上下文较长时会提前分批。']]},
]
async function load(){if(!loaded.value){Object.assign(form,await api('/api/settings/rules'));loaded.value=true}}
watch(()=>props.active,async active=>{if(active)try{await load()}catch(e){feedback.value=e.message;failed.value=true}},{immediate:true})
function edit(key){if(busy.value)return;editing.value=key;value.value=Array.isArray(form[key])?form[key].join('\n'):form[key];feedback.value='';failed.value=false}
async function save(key){
 if(busy.value||editing.value!==key)return
 const next=Array.isArray(form[key])?[...new Set(String(value.value).split(/\r?\n/).map(x=>x.trim()).filter(Boolean))]:Number(value.value)
 if(JSON.stringify(next)===JSON.stringify(form[key])){editing.value='';return}
 busy.value=true;failed.value=false
 try{const result=await api('/api/settings/rules',{...form,[key]:next});for(const [k,v] of Object.entries(result))if(k in form)form[k]=v;editing.value='';feedback.value='已保存，立即生效。';await loadStatus()}
 catch(e){feedback.value=e.message;failed.value=true}finally{busy.value=false}
}
</script>
<template>
<PageHeading eyebrow="RULES" title="监控规则"/>
<section class="panel rule-table-panel"><div class="section-heading"><div><h2>当前配置</h2><p>修改后按 Enter 或点击别处保存，Esc 放弃</p></div></div><table class="inline-rules"><tbody v-for="group in groups" :key="group.key"><tr class="rule-group"><th colspan="2">{{group.label}}</th></tr><tr v-if="group.key==='ds'"><th>复核模型</th><td><span class="rule-value rule-static">{{status?.ds_configured?status.ds_model:'尚未配置'}}</span></td></tr><tr v-for="[key,label,unit,min,max,hint] in group.fields" :key="key"><th><label :for="'rule-'+key" :title="hint">{{label}}</label></th><td><template v-if="editing===key"><textarea v-if="Array.isArray(form[key])" :id="'rule-'+key" v-model="value" v-focus rows="4" :disabled="busy" placeholder="每行一项" @blur="save(key)" @keydown.ctrl.enter="$event.target.blur()" @keydown.esc.prevent="editing=''"/><input v-else :id="'rule-'+key" v-model="value" v-focus type="number" :min="min" :max="max" :disabled="busy" @blur="save(key)" @keydown.enter.prevent="$event.target.blur()" @keydown.esc.prevent="editing=''"><small v-if="Array.isArray(form[key])">每行一项，最多 600 项，每项最多 80 字。</small></template><button v-else class="rule-value" :disabled="!loaded||busy" :aria-label="'编辑'+label" @click="edit(key)">{{Array.isArray(form[key])?(form[key].join('、')||'未配置'):form[key]}}<span>{{unit}} <span aria-hidden="true">✎</span></span></button></td></tr></tbody></table><p class="form-feedback" :class="{failed}" role="status">{{feedback}}</p></section>
<FeedbackPanel :active="active"/>
<section class="panel"><div class="section-heading"><div><h2>内置筛选规则</h2><p>DS 复核时会按这些行为分类判断</p></div></div><div id="policy-list"><div v-for="([label,advice],i) in Object.values(status?.policies||{})" :key="label" class="policy-row"><span class="policy-number">{{String(i+1).padStart(2,'0')}}</span><div><strong>{{label}}</strong><p>处理建议：{{advice}}</p></div></div></div></section>
<WhitelistPanel :active="active"/>
</template>
<style scoped>
.inline-rules .rule-group th{font-weight:600;color:var(--green);line-height:1.5;padding:22px 0 10px;border-bottom:0}.inline-rules tbody+tbody{border-top:1px solid var(--line)}.inline-rules tbody tr:last-child td,.inline-rules tbody tr:last-child th{border-bottom:0}.rule-table-panel{padding:22px 26px}.inline-rules{width:100%;border-collapse:collapse;font-size:13px}.inline-rules th,.inline-rules td{padding:13px 0;border-bottom:1px solid var(--line);text-align:left;vertical-align:top}.inline-rules th{width:36%;font-weight:400;color:var(--subtle);line-height:36px}.inline-rules td{color:var(--green)}.rule-value{display:flex;align-items:baseline;justify-content:space-between;gap:18px;min-height:36px;border:0;border-radius:6px;background:transparent;padding:7px 10px;width:100%;text-align:left;color:inherit;font:inherit;cursor:pointer;overflow-wrap:anywhere}.rule-value:hover{background:var(--surface-2)}.rule-static{cursor:default}.rule-static:hover{background:transparent}.rule-value>span{white-space:nowrap;color:var(--subtle);font-size:11px}.rule-value>span span{opacity:0;margin-left:10px}.rule-value:hover>span span,.rule-value:focus-visible>span span{opacity:1}.inline-rules input,.inline-rules textarea{width:100%;box-sizing:border-box;border:1px solid var(--line-2);padding:9px 11px;border-radius:6px;background:var(--surface);color:var(--green);font:inherit}.inline-rules small{display:block;margin-top:5px;font-size:11px;color:var(--subtle)}.budget-explanation{margin-top:17px;line-height:1.8}@media(max-width:600px){.inline-rules .rule-group th{font-weight:600;color:var(--green);line-height:1.5;padding:22px 0 10px;border-bottom:0}.inline-rules tbody+tbody{border-top:1px solid var(--line)}.inline-rules tbody tr:last-child td,.inline-rules tbody tr:last-child th{border-bottom:0}.rule-table-panel{padding:18px}.inline-rules th{width:43%;line-height:1.7;padding-top:21px}.rule-table-panel .section-heading{align-items:start;flex-direction:column}}
</style>
