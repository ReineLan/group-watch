import {ref, onScopeDispose} from 'vue'
export function useQuery(api) {
  const question=ref(''),busy=ref(false),status=ref(''),answer=ref(''),result=ref(null)
  let controller, sequence=0
  function cancel(){controller?.abort()}
  async function submit(){
    if(busy.value||!question.value.trim())return
    const revision=++sequence;controller=new AbortController();busy.value=true;status.value='正在查询…';answer.value='';result.value=null
    const timeout=setTimeout(cancel,130000)
    try{
      const data=await api('/query',{question:question.value.trim()},{evidence:true,signal:controller.signal})
      if(revision!==sequence)return
      result.value=data;answer.value=data.answer
      const schemas={messages:'群消息',cases:'监控线索',decisions:'人工判断',records:'处罚档案',rules:'处理办法'}
      const limited=Object.entries(data.coverage).filter(([,v])=>v.limited).map(([name,v])=>(schemas[name]||name)+'最新 '+v.rows+' / '+v.total+' 条')
      status.value=limited.length?'查询范围：'+limited.join('；'):''
    }catch(e){if(revision===sequence)status.value=controller.signal.aborted?'查询已停止。':e.message}
    finally{clearTimeout(timeout);if(revision===sequence){busy.value=false;controller=null}}
  }
  onScopeDispose(()=>{sequence++;cancel()})
  return {question,busy,status,answer,result,submit,cancel}
}
