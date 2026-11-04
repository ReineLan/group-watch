<script setup>
defineProps({pair:Boolean})
</script>
<template><div class="broadcast-target" :class="{'settings-pair':pair}"><slot/></div></template>
<style scoped>
.broadcast-target{display:grid;grid-template-columns:115px minmax(100px,1fr) 30px;gap:8px;margin-bottom:14px;align-items:center}
.settings-pair{grid-template-columns:minmax(90px,.6fr) minmax(140px,1.4fr) 30px}
.broadcast-target :deep(input),.broadcast-target :deep(select){width:100%;padding:10px;border:1px solid var(--line);border-radius:6px;background:var(--surface);font:inherit;color:var(--green);min-width:0}
.broadcast-target :deep(small){grid-column:1/-1;color:var(--subtle);font-size:12px}
.broadcast-target :deep(label){min-width:0}
@media(max-width:480px){.settings-pair{grid-template-columns:minmax(0,1fr) minmax(100px,1.2fr) 30px}}
</style>
