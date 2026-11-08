<script setup>
import {ref,reactive,watch,computed} from 'vue'
import SuggestBox from '../../../shared/ui/SuggestBox.vue'
import {useWorkspace} from '../../../entities/monitor/model/workspace.js'
const props=defineProps({active:Boolean}),{api,status}=useWorkspace()
const points=ref([]),editing=ref(null),limit=ref(12),loaded=ref(false),busy=ref(false),message=ref(''),failed=ref(false)
const draft=reactive({source:'',rule:'',verdict:'clear',summary:''})
const vFocus={mounted:el=>el.focus()}
const ruleName=key=>status.value?.policies?.[key]?.[0]||key||'通用判断'
const ruleOptions=computed(()=>Object.entries(status.value?.policies||{}).map(([value,policy])=>({value,label:policy[0]})))
watch(()=>props.active,async active=>{if(active&&editing.value===null)try{points.value=(await api('/api/settings/feedback')).points;loaded.value=true}catch(e){message.value=e.message;failed.value=true}},{immediate:true})
function edit(point=null){if(busy.value)return;Object.assign(draft,point?{source:point.source,rule:point.rule,verdict:point.verdict,summary:point.summary}:{source:'',rule:'',verdict:'clear',summary:''});editing.value=point?.source||'new';message.value='';failed.value=false}
async function save(){if(busy.value||!draft.summary.trim())return;busy.value=true;failed.value=false;try{const result=await api('/api/settings/feedback',{...draft});points.value=result.points;editing.value=null;message.value='已保存，后续 DS 判断即时使用。'}catch(e){message.value=e.message;failed.value=true}finally{busy.value=false}}
async function remove(point){if(busy.value)return;busy.value=true;failed.value=false;try{points.value=(await api('/api/settings/feedback/delete',{source:point.source})).points;message.value='已移除此条判断摘要。'}catch(e){message.value=e.message;failed.value=true}finally{busy.value=false}}
</script>
<template>
<section class="panel feedback-panel" aria-labelledby="feedback-heading">
 <div class="section-heading"><div><h2 id="feedback-heading">反馈摘要</h2></div><button class="button small" type="button" :disabled="busy||!loaded||editing!==null||points.length>=160" @click="edit()">＋ 添加条目</button></div>
 <ol class="feedback-points">
  <li v-for="point in points.slice(0,limit)" :key="point.source">
   <template v-if="editing!==point.source"><div class="point-label"><span class="badge" :class="point.verdict==='clear'?'clear':'violation'">{{point.verdict==='clear'?'不算违规':'算违规'}}</span><span>{{ruleName(point.rule)}}</span></div><p>{{point.summary}}</p><div class="point-actions"><button type="button" class="text-link" :disabled="busy||editing!==null" @click="edit(point)">修改</button><button type="button" class="text-link" :disabled="busy||editing!==null" @click="remove(point)">移除</button></div></template>
   <form v-else class="point-editor" @submit.prevent="save"><div class="point-fields"><label>判断边界<select v-model="draft.verdict" :disabled="busy"><option value="clear">不算违规</option><option value="violation">算违规</option></select></label><label>适用行为<SuggestBox v-model="draft.rule" :options="ruleOptions" maxlength="80" :disabled="busy" placeholder="通用判断"/></label></div><label>判断摘要<textarea v-model="draft.summary" v-focus maxlength="480" rows="3" :disabled="busy" required/></label><div class="point-actions"><button class="button primary small" :disabled="busy||!draft.summary.trim()">保存</button><button class="button small" type="button" :disabled="busy" @click="editing=null">取消</button><small>{{draft.summary.length}} / 480</small></div></form>
  </li>
 </ol>
 <form v-if="editing==='new'" class="point-editor new-point" @submit.prevent="save"><div class="point-fields"><label>判断边界<select v-model="draft.verdict" :disabled="busy"><option value="clear">不算违规</option><option value="violation">算违规</option></select></label><label>适用行为<SuggestBox v-model="draft.rule" :options="ruleOptions" maxlength="80" :disabled="busy" placeholder="通用判断"/></label></div><label>判断摘要<textarea v-model="draft.summary" v-focus maxlength="480" rows="3" :disabled="busy" placeholder="例如：针对工作或公司的抱怨，不等于辱骂群友。" required/></label><div class="point-actions"><button class="button primary small" :disabled="busy||!draft.summary.trim()">保存</button><button class="button small" type="button" :disabled="busy" @click="editing=null">取消</button><small>{{draft.summary.length}} / 480</small></div></form>
 <p v-if="loaded&&!points.length&&editing===null" class="muted">暂无判断纠正。可直接添加，或在处理时填写判断依据。</p>
 <button v-if="points.length>limit" type="button" class="text-link" @click="limit+=12">查看更多（还剩 {{points.length-limit}} 条）</button>
 <p class="form-feedback" :class="{failed}" role="status">{{message}}</p>
</section>
</template>
<style scoped>
.feedback-panel .section-heading{align-items:start}.feedback-points{list-style:none;counter-reset:point;padding:0;margin:0}.feedback-points>li{counter-increment:point;position:relative;padding:20px 0 19px 38px;border-top:1px solid var(--line)}.feedback-points>li::before{content:counter(point,decimal-leading-zero);position:absolute;left:0;top:23px;color:var(--subtle);font:600 12px Barlow,sans-serif}.point-label{display:flex;align-items:center;gap:10px;font-size:12px;color:var(--muted);flex-wrap:wrap}.point-label small{font-size:10px;margin-left:auto;color:var(--subtle)}.feedback-points p{font-size:13px;line-height:1.95;margin:12px 0;white-space:pre-wrap;overflow-wrap:anywhere}.point-actions{display:flex;align-items:center;gap:18px;margin-top:12px}.point-actions small{margin-left:auto;font-size:10px;color:var(--muted)}.point-actions .text-link{font-size:11px}.feedback-limit{font-size:11px;color:var(--muted);padding-top:19px;margin-top:10px;border-top:1px solid var(--line)}.point-editor label{display:block;font-size:12px;color:var(--muted)}.point-fields{display:grid;grid-template-columns:120px 1fr;gap:12px;margin-bottom:12px}.point-editor input,.point-editor select,.point-editor textarea,.point-editor :deep(.suggest-box) input{display:block;width:100%;padding:10px 12px;background:var(--surface);border:1px solid var(--line-2);border-radius:7px;font:inherit;color:var(--green);margin-top:7px;box-sizing:border-box}.point-editor textarea{resize:vertical;line-height:1.8;min-height:90px}.new-point{padding:20px;border:1px solid var(--line);border-radius:10px;background:var(--surface-2);margin-bottom:18px}@media(max-width:600px){.feedback-panel .section-heading{flex-direction:column}.feedback-points>li{padding-left:29px}.point-fields{grid-template-columns:105px 1fr}.point-label small{margin-left:0}}
</style>
