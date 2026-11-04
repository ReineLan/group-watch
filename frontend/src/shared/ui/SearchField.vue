<script setup>
import EvidenceIcon from './EvidenceIcon.vue'
defineOptions({inheritAttrs:false})
defineProps({modelValue:String,label:String,placeholder:String,shortcut:Boolean})
const emit=defineEmits(['update:modelValue'])
</script>
<template>
<label class="workbench-search"><EvidenceIcon name="search"/><input v-bind="$attrs" class="workbench-search-input" type="search" :value="modelValue" :placeholder="placeholder" :aria-label="label" @input="emit('update:modelValue',$event.target.value)"><kbd v-if="shortcut" aria-hidden="true">/</kbd></label>
</template>
<style scoped>
.workbench-search{box-sizing:border-box;display:flex;align-items:center;gap:9px;flex:1;min-width:180px;min-height:42px;height:42px;padding:0 12px;border:1px solid var(--line-2);border-radius:7px;background:var(--surface);color:var(--subtle);cursor:text;transition:border-color .18s,box-shadow .18s}.workbench-search:focus-within{border-color:var(--accent);box-shadow:0 0 0 3px color-mix(in srgb,var(--accent-2) 11%,transparent)}.workbench-search :deep(svg){position:static;transform:none;flex:none;width:16px;height:16px;margin:0}.workbench-search .workbench-search-input{box-sizing:border-box;display:block;flex:1;min-width:0;width:100%;height:100%;min-height:0;margin:0!important;padding:0!important;border:0!important;border-radius:0;outline:none!important;box-shadow:none!important;background:transparent;font:inherit;font-size:12px;line-height:normal;color:var(--ink)}.workbench-search-input::placeholder{color:var(--subtle);opacity:1}.workbench-search kbd{flex:none;font:11px sans-serif;color:var(--faint)}@media(max-width:760px){.workbench-search{flex-basis:100%}}
</style>
