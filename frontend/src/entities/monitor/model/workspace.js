import {inject, ref, onScopeDispose} from 'vue'
export const workspaceKey = Symbol('workspace')
export const useWorkspace = () => inject(workspaceKey)
export function createWorkspace(session) {
  const {api,toast,notify}=session
  const status=ref(null), error=ref(''), updated=ref(0), refreshing=ref(false)
  let polling, alive=true, refreshPage=async()=>{}
  async function loadStatus(){
    const data=await api('/api/status');if(!alive)return
    status.value=data;updated.value=Date.now()/1000
    error.value=[data.error&&'消息通道：'+data.error,data.review_error&&'DS 复核：'+data.review_error,data.notify_error&&'通知：'+data.notify_error,!data.ds_configured&&'DS 尚未配置，候选将保留在等待复核队列。',data.tasks?.some(t=>t.done)&&'后台任务已退出，请检查服务日志。'].filter(Boolean).join(' / ')
  }
  async function refresh(){if(refreshing.value||document.hidden)return;refreshing.value=true;try{await loadStatus();await refreshPage()}catch(e){if(alive)error.value=e.message}finally{refreshing.value=false}}
  function start(callback){refreshPage=callback;polling=setInterval(refresh,10000)}
  onScopeDispose(()=>{alive=false;clearInterval(polling)})
  return {api,status,error,updated,refreshing,toast,notify,loadStatus,refresh,start}
}
