<script setup>
import {ref,watch,onScopeDispose} from 'vue'
import {useWorkspace} from '../../../entities/monitor/model/workspace.js'
import SettingsRow from '../../../shared/ui/SettingsRow.vue'
const props=defineProps({active:Boolean})
const {api,notify,loadStatus}=useWorkspace()
const members=ref([]),loaded=ref(false),opened=ref(false),error=ref(''),busy=ref(false),saved=ref(false)
let polls=0
watch(()=>props.active,async active=>{
 if(!active||loaded.value)return
 try{members.value=(await api('/api/settings/whitelist')).members;loaded.value=true}catch(e){error.value=e.message}
},{immediate:true})
// Only fill names: polling must never overwrite QQ numbers being edited.
const polling=setInterval(async()=>{
 if(!props.active||!opened.value||!loaded.value||busy.value||document.hidden||polls>=12||!members.value.some(row=>!row.nickname))return
 polls++
 try{
  const data=await api('/api/settings/whitelist')
  for(const member of members.value){const found=data.members.find(row=>row.user_id===member.user_id);if(found?.nickname)member.nickname=found.nickname}
 }catch{/* Keep editable values while the connection is unavailable. */}
},5000)
onScopeDispose(()=>clearInterval(polling))
async function save(){
 if(busy.value)return
 busy.value=true;error.value='';saved.value=false
 try{
  const data=await api('/api/settings/whitelist',{accounts:members.value.map(row=>row.user_id.trim())})
  members.value=data.members;polls=0;saved.value=true;notify('白名单已保存')
  void loadStatus().catch(()=>{})
 }catch(e){error.value=e.message}finally{busy.value=false}
}
</script>
<template>
<details class="whitelist-details" @toggle="opened=$event.target.open">
 <summary><span>白名单</span><small>{{members.length}} 人</small></summary>
 <div v-if="opened" class="settings-grid">
  <section class="panel settings-panel">
   <div class="section-heading"><div><h2>两群共用</h2><p>按 QQ 号去重，显示 QQ 昵称。</p></div></div>
   <form @submit.prevent="save">
    <SettingsRow v-for="(member,i) in members" :key="i" pair>
     <span class="whitelist-name">{{member.nickname||'昵称暂未获取'}}</span>
     <label><span class="sr-only">QQ 号</span><input v-model="member.user_id" inputmode="numeric" placeholder="QQ 号" pattern="[1-9][0-9]{4,11}" maxlength="12" required :disabled="busy" @input="member.nickname='';saved=false"/></label>
     <button class="icon-button" type="button" :disabled="busy" :aria-label="'移除 '+(member.nickname||member.user_id||i+1)" @click="members.splice(i,1);saved=false">×</button>
    </SettingsRow>
    <button v-if="members.length<200" class="text-link" type="button" :disabled="busy" @click="members.push({user_id:'',nickname:''});saved=false">＋ 添加成员</button>
    <div class="form-actions"><button class="button primary" type="submit" :disabled="!loaded||busy">{{busy?'保存中…':'保存'}}</button></div>
    <p v-if="saved" class="form-feedback" role="status">已保存，已对两群生效。</p>
    <p v-if="error" class="form-feedback failed" role="status">{{error}}</p>
   </form>
  </section>
 </div>
</details>
</template>
<style scoped>
.whitelist-details>summary{display:flex;align-items:center;gap:12px;padding:15px 2px;margin-bottom:18px;border-top:1px solid var(--line);cursor:pointer;font-weight:600;list-style:none;color:var(--ink)}
.whitelist-details>summary::-webkit-details-marker{display:none}
.whitelist-details>summary::before{content:'›';font-size:21px;line-height:1;color:var(--subtle);transition:transform .2s}
.whitelist-details[open]>summary::before{transform:rotate(90deg)}
.whitelist-details>summary small{margin-left:auto;font-size:12px;font-weight:400;color:var(--subtle)}
.whitelist-name{font-size:13px;overflow-wrap:anywhere;color:var(--ink)}
</style>
