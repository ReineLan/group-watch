<script setup>
import {ref,computed,useId} from 'vue'
import {usePopup} from './popup.js'
defineOptions({inheritAttrs:false})
const props=defineProps({modelValue:String,options:{type:Array,default:()=>[]},disabled:Boolean})
const emit=defineEmits(['update:modelValue'])
const listId=useId(),active=ref(-1),field=ref()
const {open,target:popupTarget,style:popupStyle,show,hide}=usePopup(()=>field.value)
const items=computed(()=>props.options.map(item=>typeof item==='string'?{value:item,label:item}:{value:item.value,label:item.label??item.value}))
const filtered=computed(()=>{
 const query=(props.modelValue||'').trim().toLowerCase()
 return query?items.value.filter(item=>item.label.toLowerCase().includes(query)||item.value.toLowerCase().includes(query)):items.value
})
function onInput(event){emit('update:modelValue',event.target.value);show();active.value=-1}
function pick(item){emit('update:modelValue',item.value);hide();active.value=-1}
function onKeydown(event){
 if(event.isComposing)return
 if(event.key==='Escape'){hide();return}
 if(event.key==='ArrowDown'||event.key==='ArrowUp'){
  if(!filtered.value.length)return
  event.preventDefault();show()
  const step=event.key==='ArrowDown'?1:-1
  active.value=(active.value+step+filtered.value.length)%filtered.value.length
  document.getElementById(listId+'-'+active.value)?.scrollIntoView({block:'nearest'})
 }else if(event.key==='Enter'&&open.value&&active.value>=0&&filtered.value[active.value]){event.preventDefault();pick(filtered.value[active.value])}
}
</script>
<template>
<div class="suggest-box">
 <input ref="field" v-bind="$attrs" :value="modelValue" :disabled="disabled" role="combobox" aria-autocomplete="list"
  :aria-expanded="open&&filtered.length>0" :aria-controls="listId" :aria-activedescendant="active>=0?listId+'-'+active:undefined"
  autocomplete="off" @input="onInput" @focus="show" @blur="hide();active=-1" @keydown="onKeydown">
 <Teleport :to="popupTarget"><ul v-if="open&&filtered.length" :id="listId" class="suggest-list" role="listbox" :style="popupStyle" @mousedown.prevent>
  <li v-for="(item,i) in filtered" :key="item.value" :id="listId+'-'+i" role="option" :aria-selected="i===active"
   :class="{active:i===active}" @click="pick(item)"><span class="suggest-label">{{item.label}}</span><span v-if="item.label!==item.value" class="suggest-value">{{item.value}}</span></li>
 </ul></Teleport>
</div>
</template>
<style scoped>
.suggest-box{display:block;width:100%}
.suggest-box input{display:block;width:100%}
.suggest-list li{display:flex;align-items:baseline;gap:10px}
.suggest-list .suggest-value{margin-left:auto;flex:none;font-size:11px;color:var(--subtle)}
</style>
