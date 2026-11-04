<script setup>
defineProps({name:String})
const paths={plus:'M12 5v14M5 12h14',download:'M12 3v12m-4-4 4 4 4-4M4 16v5h16v-5',search:'m16 16 5 5',upload:'M12 16V3m-5 5 5-5 5 5M4 15v6h16v-6',archive:'M5 8v12h14V8M10 12h4'}
</script>
<template><span :data-icon="name"><svg viewBox="0 0 24 24" aria-hidden="true"><circle v-if="name==='search'" cx="10.5" cy="10.5" r="6.5"/><rect v-if="name==='archive'" x="3" y="3" width="18" height="5" rx="1.5"/><path :d="paths[name]||''"/></svg></span></template>
<style scoped>
span{display:inline-flex;align-items:center;flex:none}svg{display:block;width:18px;height:18px;fill:none;stroke:currentColor;stroke-width:1.7;stroke-linecap:round;stroke-linejoin:round}
</style>
