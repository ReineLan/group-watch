// Limits animation starts, not active circles. Already running circles are untouched.
export function selectionQueue({run,interval=260,capacity=5,now=()=>performance.now(),setTimer=setTimeout,clearTimer=clearTimeout,observe=()=>{}}){
  let pending=[],timer=null,launching=false,lastStart=-Infinity,epoch=0
  const notify=(kind,request,extra={})=>observe({kind,request,pending:pending.map(entry=>entry.request),...extra})
  function pump(){
    if(launching||!pending.length||timer!==null)return
    const wait=lastStart+interval-now()
    if(wait>0){timer=setTimer(()=>{timer=null;pump()},wait);return}
    const entry=pending.shift(),generation=epoch
    launching=true;let started=false
    notify('queue-dispatch',entry.request)
    const onStarted=()=>{
      if(started||generation!==epoch)return
      started=true;lastStart=now();launching=false
      notify('queue-started',entry.request,{startedAt:lastStart});pump()
    }
    try{
      Promise.resolve(run(entry.request,onStarted)).then(
        ()=>entry.resolve({status:started?'completed':'skipped'}),
        error=>{notify('queue-error',entry.request,{message:String(error)});entry.resolve({status:'failed'})},
      ).finally(()=>{if(generation===epoch&&!started){launching=false;pump()}})
    }catch(error){entry.resolve({status:'failed'});launching=false;notify('queue-error',entry.request,{message:String(error)});pump()}
  }
  return {
    enqueue(request){
      const promise=new Promise(resolve=>{
        if(pending.length===capacity){const oldest=pending.shift();oldest.resolve({status:'dropped'});notify('queue-dropped',oldest.request)}
        pending.push({request,resolve});notify('queue-enqueued',request)
      })
      pump();return promise
    },
    cancel(){
      epoch++;if(timer!==null)clearTimer(timer);timer=null;launching=false;lastStart=-Infinity
      const discarded=pending;pending=[]
      for(const entry of discarded){entry.resolve({status:'cancelled'});notify('queue-cancelled',entry.request)}
    },
  }
}
