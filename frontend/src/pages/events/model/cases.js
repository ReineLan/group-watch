import {reactive,ref,shallowRef,watch,onScopeDispose} from 'vue'
import {localDate,time} from '../../../shared/lib/format.js'
const chatShots=new Map()
export const cachedChatShot=id=>chatShots.get(id)
export const reviveChatShot=shot=>({...shot,preview:'data:'+(shot.type||'image/webp')+';base64,'+shot.data})
export function cacheChatShot(id,shot){const{preview,...rest}=shot;chatShots.delete(id);chatShots.set(id,rest);while(chatShots.size>2)chatShots.delete(chatShots.keys().next().value)}
export function caseDraft(c, policies) {
  const own=c.context.filter(m=>m.user_id===c.user_id&&c.evidence.includes(m.message_id))
  return {member_id:c.member_account||String(c.user_id),nickname:null,card:null,group_id:c.group_id,autoAnalyze:true,case_id:c.id,event_date:localDate(),reason:(policies?.[c.rule]?.[0]||c.rule)+'\n'+own.map(m=>`${time(m.time)} · ${m.name}：${m.text||'[无文本]'}`).join('\n').slice(0,6000),notes:'',punishment:''}
}
export function useCases(api, isActive, report) {
  const filters=reactive({state:'attention',group:'',resolution:'open',search:''}),offset=ref(0),rows=shallowRef([]),busy=ref(false),loaded=ref(false)
  let revision=0,controller,timer
  async function load(){
    if(!isActive())return
    const id=++revision;controller?.abort();controller=new AbortController();busy.value=true
    try{const query=new URLSearchParams({...filters,group:filters.group||'0',search:filters.search.trim(),offset:String(offset.value)});const data=await api('/api/cases?'+query,undefined,{signal:controller.signal});if(id===revision){rows.value=data;loaded.value=true}}
    catch(e){if(id===revision&&!controller.signal.aborted)report(e.message)}finally{if(id===revision)busy.value=false}
  }
  watch(()=>[filters.state,filters.group,filters.resolution],()=>{offset.value=0;load()})
  watch(()=>filters.search,()=>{clearTimeout(timer);timer=setTimeout(()=>{offset.value=0;load()},300)})
  function reset(){clearTimeout(timer);Object.assign(filters,{state:'attention',group:'',resolution:'open',search:''});offset.value=0;load()}
  function step(delta){offset.value=Math.max(0,offset.value+delta*50);load()}
  onScopeDispose(()=>{revision++;controller?.abort();clearTimeout(timer)})
  return {filters,offset,rows,busy,loaded,load,reset,step}
}
