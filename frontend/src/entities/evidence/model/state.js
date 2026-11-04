import {ref,reactive,computed,inject,onScopeDispose} from 'vue'
import {norm} from './records.js'
export const evidenceKey=Symbol('evidence')
export const useEvidence=()=>inject(evidenceKey)
export function createEvidence(api,notify,monitoredGroups=ref({})) {
  const records=ref([]),rules=ref([]),overview=ref({risks:[],audit:[],backup_count:0}),profiles=ref({}),error=ref(''),loaded=ref(false),interacting=ref(false)
  const totals=reactive({records:0,bans:0,risks:0}),draft=ref(null),view=ref('overview')
  let pending,alive=true,polling,profileTimer,profileBusy=false
  const groups=computed(()=>Object.keys(monitoredGroups.value))
  const groupLabel=id=>monitoredGroups.value[String(id)]||String(id)
  function publish(){Object.assign(totals,{records:records.value.length,bans:records.value.filter(r=>['进行中','永久禁言'].includes(r.ban?.status)).length,risks:overview.value.risks.filter(r=>r.status==='再犯预警').length})}
  async function load(){
    if(pending)return pending
    pending=(async()=>{
      try{const result=await Promise.all([api('/api/records',undefined,{evidence:true}),api('/api/rules',undefined,{evidence:true}),api('/api/overview',undefined,{evidence:true}),api('/api/profiles',undefined,{evidence:true}).catch(()=>({items:profiles.value}))]);if(!alive)return;[records.value,rules.value,overview.value]=result;profiles.value=result[3].items;loaded.value=true;error.value='';publish()}
      catch(e){if(alive){error.value=e.message;notify('读取失败：'+e.message)}throw e}
      finally{pending=null}
    })();return pending
  }
  function profileFor(r){const p=profiles.value[r.id||(r.record_ids||[])[0]]||r;return norm(p.member_id)===norm(r.member_id)?p:{}}
  function displayName(r){return profileFor(r).nickname??r.nickname??''}
  function start(){
    load().catch(()=>{})
    polling=setInterval(()=>{if(!document.hidden&&!interacting.value)load().catch(()=>{})},60000)
    profileTimer=setInterval(async()=>{if(profileBusy||document.hidden||!Object.values(profiles.value).some(p=>p.nickname_status===0||p.avatar_status===0))return;profileBusy=true;try{const result=await api('/api/profiles',undefined,{evidence:true});if(alive)profiles.value=result.items}catch{/* Cached profiles remain usable while offline. */}finally{profileBusy=false}},1500)
  }
  onScopeDispose(()=>{alive=false;clearInterval(polling);clearInterval(profileTimer)})
  return {totals,draft,view,records,rules,overview,profiles,groups,groupLabel,error,loaded,interacting,load,start,profileFor,displayName}
}
