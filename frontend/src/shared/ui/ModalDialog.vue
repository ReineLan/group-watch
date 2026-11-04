<script setup>
import {ref,watch,nextTick,onBeforeUnmount} from 'vue'
import {backdropDismiss} from '../lib/backdrop.js'
const props=defineProps({open:Boolean,label:String,id:String}),emit=defineEmits(['close'])
const dialog=ref()
const backdrop=backdropDismiss(()=>dialog.value,()=>emit('close'))
watch(()=>props.open,async()=>{await nextTick();if(!dialog.value)return;if(props.open&&!dialog.value.open){dialog.value.showModal();const body=dialog.value.querySelector('.modal-body');if(body)body.scrollTop=0}else if(!props.open&&dialog.value.open)dialog.value.close()},{immediate:true})
onBeforeUnmount(()=>dialog.value?.close())
defineExpose({element:dialog})
</script>
<template><dialog :id="id" ref="dialog" :aria-label="label" @cancel.self.prevent="emit('close')" @close="backdrop.cancel();open&&emit('close')" @pointerdown="backdrop.down" @pointercancel="backdrop.cancel" @click="backdrop.click"><slot/></dialog></template>
