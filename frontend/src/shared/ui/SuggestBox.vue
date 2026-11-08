<script setup>
import {ref,computed,useId} from 'vue'
defineOptions({inheritAttrs:false})
const props=defineProps({modelValue:String,options:{type:Array,default:()=>[]},disabled:Boolean})
const emit=defineEmits(['update:modelValue'])
const listId=useId(),open=ref(false),active=ref(-1)
const items=computed(()=>props.options.map(item=>typeof item==='string'?{value:item,label:item}:{value:item.value,label:item.label??item.value}))
const filtered=computed(()=>{
 const query=(props.modelValue||'').trim().toLowerCase()
 return query?items.value.filter(item=>item.label.toLowerCase().includes(query)||item.value.toLowerCase().includes(query)):items.value
})
function onInput(event){emit('update:modelValue',event.target.value);open.value=true;active.value=-1}
function pick(item){emit('update:modelValue',item.value);open.value=false;active.value=-1}
function onKeydown(event){
 if(event.isComposing)return
 if(event.key==='Escape'){open.value=false;return}
 if(event.key==='ArrowDown'||event.key==='ArrowUp'){
  if(!filtered.value.length)return
  event.preventDefault();open.value=true
  const step=event.key==='ArrowDown'?1:-1
  active.value=(active.value+step+filtered.value.length)%filtered.value.length
  document.getElementById(listId+'-'+active.value)?.scrollIntoView({block:'nearest'})
 }else if(event.key==='Enter'&&open.value&&active.value>=0&&filtered.value[active.value]){event.preventDefault();pick(filtered.value[active.value])}
}
</script>
<template>
<div class="suggest-box">
 <input v-bind="$attrs" :value="modelValue" :disabled="disabled" role="combobox" aria-autocomplete="list"
  :aria-expanded="open&&filtered.length>0" :aria-controls="listId" :aria-activedescendant="active>=0?listId+'-'+active:undefined"
  autocomplete="off" @input="onInput" @focus="open=true" @blur="open=false;active=-1" @keydown="onKeydown">
 <ul v-if="open&&filtered.length" :id="listId" class="suggest-list" role="listbox">
  <li v-for="(item,i) in filtered" :key="item.value" :id="listId+'-'+i" role="option" :aria-selected="i===active"
   :class="{active:i===active}" @pointerdown.prevent="pick(item)" @mousedown.prevent="pick(item)"><span class="suggest-label">{{item.label}}</span><span v-if="item.label!==item.value" class="suggest-value">{{item.value}}</span></li>
 </ul>
</div>
</template>
<style scoped>
.suggest-box{position:relative;display:block;width:100%}
.suggest-box input{display:block;width:100%;box-sizing:border-box;min-height:42px;padding:11px 12px;border:1px solid var(--line-1);border-radius:6px;background:var(--surface);color:var(--ink);font:inherit}
.suggest-list{position:absolute;top:calc(100% + 6px);left:0;right:0;z-index:30;list-style:none;margin:0;padding:4px;max-height:204px;overflow:auto;border:1px solid var(--line-2);border-radius:10px;background:var(--surface);box-shadow:0 8px 24px color-mix(in srgb,var(--shadow) 12%,transparent)}
.suggest-list li{display:flex;align-items:baseline;gap:10px;padding:11px 12px;border-radius:7px;font-size:13px;line-height:1.5;color:var(--ink);cursor:pointer;overflow-wrap:anywhere}
.suggest-list li.active,.suggest-list li:active{background:var(--surface-3)}
.suggest-list .suggest-value{margin-left:auto;flex:none;font-size:11px;color:var(--subtle)}
</style>
