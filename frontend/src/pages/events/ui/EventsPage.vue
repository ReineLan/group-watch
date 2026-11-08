<script setup>
import {computed} from 'vue'
import {useWorkspace} from '../../../entities/monitor/model/workspace.js'
import {useCases} from '../model/cases.js'
import CaseCard from './CaseCard.vue'
import SearchField from '../../../shared/ui/SearchField.vue'
import PageHeading from '../../../shared/ui/PageHeading.vue'
import AppIcon from '../../../shared/ui/AppIcon.vue'
import SelectBox from '../../../shared/ui/SelectBox.vue'
const props=defineProps({active:Boolean})
const {api,status,error}=useWorkspace(),{filters,offset,rows,busy,loaded,load,reset,step}=useCases(api,()=>props.active,message=>error.value=message)
const groupFilterOptions=computed(()=>[{value:'',label:'全部群聊'},...(status.value?.groups||[]).map(group=>({value:group,label:status.value?.group_names?.[group]||'群聊名称待确认'}))])
defineExpose({refresh:load})
</script>
<template>
<PageHeading eyebrow="INBOX" title="待办线索"/>
<div class="panel filter-panel events-panel">
 <div class="filterbar"><SearchField id="search" v-model="filters.search" maxlength="200" placeholder="搜索消息内容、QQ 号或复核理由" label="搜索线索"/><label class="sr-only" for="filter">复核结果</label><SelectBox id="filter" v-model="filters.state" :options="[{value:'attention',label:'需要关注'},{value:'',label:'全部结果'},{value:'violation',label:'DS 认为违规'},{value:'pending',label:'等待复核'},{value:'clear',label:'未见违规'}]"/><label class="sr-only" for="group-filter">监控群</label><SelectBox id="group-filter" v-model="filters.group" :options="groupFilterOptions"/><label class="sr-only" for="resolution-filter">处理状态</label><SelectBox id="resolution-filter" v-model="filters.resolution" :options="[{value:'open',label:'未处理'},{value:'',label:'全部状态'},{value:'handled',label:'已处理'}]"/><button class="button small subtle" id="reset-filters" @click="reset">重置</button></div>
</div>
<div id="cases" class="case-list" :aria-busy="busy">
 <CaseCard v-for="item in rows" :key="item.id" :item="item" @saved="load"/>
 <div v-if="loaded&&!rows.length" class="panel empty-state"><div class="empty-symbol"><AppIcon name="check"/></div><h3>没有符合条件的线索</h3><p>换个筛选条件试试，或者稍后再来看看。</p></div>
</div>
<div class="panel-footer case-pager"><div class="pagination"><button id="prev" aria-label="上一页" :disabled="busy||offset===0" @click="step(-1)">←</button><span>第 {{Math.floor(offset/50)+1}} 页</span><button id="next" aria-label="下一页" :disabled="busy||rows.length<50" @click="step(1)">→</button></div></div>
</template>
