<script setup>
import {computed,ref,watch} from 'vue'
import {downloadCsv} from '../../../shared/lib/format.js'
import {useEvidence} from '../../../entities/evidence/model/state.js'
import {columnLabel,rowTarget,cellLabel} from '../model/queryPresentation.js'
const props=defineProps({result:Object,index:Number})
const emit=defineEmits(['member','record']),{records,displayName}=useEvidence()
function target(row){return rowTarget(props.result.columns,row,records.value)}
function open(row){const link=target(row);if(link)emit(link.kind,link.id)}
function label(row,index){return cellLabel(props.result.columns,row,index,records.value,displayName)}
const query=ref(''),page=ref(0),sort=ref(-1),direction=ref(1),visible=ref(props.result.columns.map((_,i)=>i))
const rows=computed(()=>{
  let rows=props.result.rows.filter(row=>row.some(x=>String(x??'').toLocaleLowerCase().includes(query.value.toLocaleLowerCase())))
  if(sort.value>=0)rows=rows.slice().sort((a,b)=>{const x=a[sort.value],y=b[sort.value];return direction.value*(typeof x==='number'&&typeof y==='number'?x-y:String(x??'').localeCompare(String(y??''),'zh-CN',{numeric:true}))})
  return rows
})
const pages=computed(()=>Math.max(1,Math.ceil(rows.value.length/25))),columns=computed(()=>visible.value.slice().sort((a,b)=>a-b))
watch(query,()=>page.value=0);watch(pages,n=>page.value=Math.min(page.value,n-1))
function order(i){direction.value=sort.value===i?-direction.value:1;sort.value=i}
function toggle(i,event){if(event.target.checked)visible.value.push(i);else if(visible.value.length>1)visible.value=visible.value.filter(x=>x!==i);else event.target.checked=true}
function csv(){downloadCsv([columns.value.map(i=>columnLabel(props.result.columns[i])),...rows.value.map(row=>columns.value.map(i=>label(row,i)))],'群管理查询-'+(props.index+1)+'.csv')}
</script>
<template>
<section class="panel query-table"><div class="table-toolbar"><input v-model="query" type="search" placeholder="筛选表格" :aria-label="'筛选查询结果 '+(index+1)"><span>{{rows.length}} 行{{result.truncated?' · 结果已截断':''}}</span><button class="button small" :disabled="!rows.length" @click="csv">导出 CSV</button></div>
<details class="column-menu"><summary>显示列</summary><label v-for="(name,i) in result.columns" :key="i"><input type="checkbox" :checked="visible.includes(i)" @change="toggle(i,$event)">{{columnLabel(name)}}</label></details>
<div class="table-wrap"><table><thead><tr><th v-for="i in columns" :key="i" :aria-sort="sort===i?(direction===1?'ascending':'descending'):'none'"><button type="button" @click="order(i)">{{columnLabel(result.columns[i])}}{{sort===i?(direction===1?' ↑':' ↓'):''}}</button></th></tr></thead><tbody><tr v-for="(row,n) in rows.slice(page*25,page*25+25)" :key="n" :class="{'query-linked-row':target(row)}" @click="open(row)"><td v-for="(i,col) in columns" :key="i"><button v-if="col===0&&target(row)" class="query-row-link" type="button" :aria-label="target(row).kind==='record'?'查看处理记录':'查看个人历史'" @click.stop="open(row)">{{label(row,i)}} ↗</button><template v-else>{{label(row,i)}}</template></td></tr></tbody></table></div>
<div class="pagination"><button class="button small" :disabled="page===0" @click="page--">上一页</button><span>{{page+1}} / {{pages}}</span><button class="button small" :disabled="page>=pages-1" @click="page++">下一页</button></div><details><summary>查看 SQL</summary><pre>{{result.sql}}</pre></details></section>
</template>
<style scoped>
.query-linked-row{cursor:pointer}.query-linked-row:hover{background:var(--surface-2)}.query-row-link{border:0;padding:0;background:none;color:var(--accent);font:inherit;text-align:left;text-decoration:underline;text-underline-offset:3px}
</style>
