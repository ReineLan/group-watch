<script setup>
import {ref,computed,useId} from 'vue'
import {usePopup} from './popup.js'
defineOptions({inheritAttrs:false})
const props=defineProps({modelValue:String,options:{type:Array,default:()=>[]},placeholder:{type:String,default:''},disabled:Boolean,required:Boolean})
const emit=defineEmits(['update:modelValue','change'])
const listId=useId(),active=ref(-1),button=ref()
const {open,target:popupTarget,style:popupStyle,show,hide}=usePopup(()=>button.value)
const items=computed(()=>props.options.map(item=>typeof item==='string'?{value:item,label:item}:{value:item.value,label:item.label??item.value,disabled:!!item.disabled}))
const current=computed(()=>items.value.find(item=>item.value===props.modelValue))
const display=computed(()=>current.value?current.value.label:(props.modelValue||props.placeholder))
const sizers=computed(()=>{const set=new Set(items.value.map(item=>item.label));if(props.placeholder)set.add(props.placeholder);set.add(display.value);return[...set]})
function scrollActive(){if(active.value>=0)document.getElementById(listId+'-'+active.value)?.scrollIntoView({block:'nearest'})}
async function toggle(){if(props.disabled)return;if(open.value){hide();return}await show();active.value=items.value.findIndex(item=>!item.disabled&&item.value===props.modelValue);if(active.value<0)active.value=items.value.findIndex(item=>!item.disabled);scrollActive()}
function pick(item){if(item.disabled)return;emit('update:modelValue',item.value);emit('change',item.value);hide();active.value=-1;button.value?.focus()}
function move(step){for(let i=active.value,n=0;n<items.value.length;n++){i=(i+step+items.value.length)%items.value.length;if(!items.value[i].disabled){active.value=i;break}}scrollActive()}
function onKeydown(event){
 if(event.isComposing)return
 if(!open.value){if(event.key==='ArrowDown'||event.key==='ArrowUp'){event.preventDefault();toggle()}return}
 if(event.key==='Escape')hide()
 else if(event.key==='ArrowDown'){event.preventDefault();move(1)}
 else if(event.key==='ArrowUp'){event.preventDefault();move(-1)}
 else if(event.key==='Enter'||event.key===' '){event.preventDefault();const item=items.value[active.value];item&&pick(item)}
 else if(event.key==='Tab')hide()
}
</script>
<template>
<div class="select-box" :class="{open}" :hidden="$attrs.hidden">
 <input class="select-value" :name="$attrs.name" :value="modelValue" :required="required||undefined" tabindex="-1" aria-hidden="true">
 <button ref="button" type="button" v-bind="$attrs" class="select-button" :disabled="disabled" aria-haspopup="listbox"
  :aria-expanded="open" :aria-controls="listId" :aria-activedescendant="open&&active>=0?listId+'-'+active:undefined"
  @click="toggle" @blur="hide();active=-1" @keydown="onKeydown"><span class="select-text-wrap"><span :class="{placeholder:!current&&!modelValue}">{{display}}</span><span v-for="text in sizers" :key="text" class="select-sizer" aria-hidden="true">{{text}}</span></span><svg viewBox="0 0 24 24" aria-hidden="true"><path d="m5.5 8.5 6.5 7 6.5-7"/></svg></button>
 <Teleport :to="popupTarget"><ul v-if="open" :id="listId" class="select-list" role="listbox" :style="popupStyle" @pointerdown.prevent>
  <li v-for="(item,i) in items" :key="item.value" :id="listId+'-'+i" role="option" :aria-selected="item.value===modelValue" :aria-disabled="item.disabled||undefined"
   :class="{active:i===active,disabled:item.disabled}" @pointerdown.prevent="pick(item)" @mousedown.prevent="pick(item)">{{item.label}}</li>
 </ul></Teleport>
</div>
</template>
<style scoped>
.select-box{position:relative;display:flex}
.select-value{position:absolute;inset:0;width:100%;height:100%;margin:0;padding:0;border:0;opacity:0;pointer-events:none}
.select-button{display:flex;align-items:center;gap:8px;width:100%;text-align:left;cursor:pointer}
.select-button:disabled{cursor:not-allowed;opacity:.5}
.select-button:focus-visible{outline:none;border-color:var(--line-3);box-shadow:0 0 0 3px color-mix(in srgb,var(--shadow) 6%,transparent)}
.select-text-wrap{display:grid;flex:1;min-width:0}
.select-text-wrap>span{grid-area:1/1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.select-sizer{visibility:hidden}
.select-button .placeholder{color:var(--faint)}
.select-button svg{flex:none;width:16px;height:16px;stroke:currentColor;stroke-width:2.4;fill:none;stroke-linecap:round;stroke-linejoin:round;color:var(--subtle);transition:transform .15s}
.select-box.open .select-button svg{transform:rotate(180deg)}
.select-list li.disabled{color:var(--faint);cursor:default}
</style>
