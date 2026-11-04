<script setup>
import {ref,computed,watch,onMounted,onBeforeUnmount} from 'vue'
import {useSession} from '../../../shared/api/session.js'
import {time} from '../../../shared/lib/format.js'
import PageHeading from '../../../shared/ui/PageHeading.vue'
import AppIcon from '../../../shared/ui/AppIcon.vue'
const props=defineProps({active:Boolean})
const {api,notify}=useSession(),data=ref(null),busy=ref(false)
async function refresh(){if(busy.value)return;busy.value=true;try{data.value=await api('/api/maintenance')}catch(e){notify(e.message)}finally{busy.value=false}}
watch(()=>props.active,active=>{if(active)refresh()},{immediate:true})
const state=computed(()=>data.value?[['refresh','自动更新',data.value.update.status],['clock','最近备份',data.value.last_backup?time(data.value.last_backup):'等待首次备份'],['disk','备份占用',(data.value.backup_bytes/1048576).toFixed(1)+' MB']]:[])
onMounted(()=>window.addEventListener('workbench-backups-changed',refresh))
onBeforeUnmount(()=>window.removeEventListener('workbench-backups-changed',refresh))
defineExpose({refresh})
</script>
<template>
<PageHeading eyebrow="SYSTEM" title="运行与恢复"/>
<div id="maintenance-status" class="stat-tiles"><div v-for="[icon,label,value] in state" :key="label" class="stat-tile panel"><span class="stat-icon"><AppIcon :name="icon"/></span><span class="stat-label">{{label}}</span><strong>{{value}}</strong></div></div>
<div id="maintenance-archive"></div>
</template>
