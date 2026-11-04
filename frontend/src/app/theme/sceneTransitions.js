import {revealRadius} from './themes.js'

// Descriptors own identity; Vue owns their DOM. Promoting a ring never remounts it.
export function sceneTransitions({initialTheme,publish,flush,driver,changing=()=>{},observe}){
  let sequence=0,epoch=0,queue=Promise.resolve()
  const make=(theme,ring=false,point=null)=>({key:++sequence,theme,ring,point})
  let base=make(initialTheme),rings=[]
  const describe=scene=>({key:scene.key,theme:scene.theme,ring:scene.ring,done:!!scene.done,point:scene.point,radius:scene.radius,mask:!!scene.mask,clickId:scene.clickId,time:scene.motion?.currentTime,playState:scene.motion?.playState})
  const notify=(kind,detail={})=>{if(observe)observe({kind,...detail,base:describe(base),rings:rings.map(describe)})}
  const update=()=>{publish([base,...rings]);notify('published')}
  function release(scene){scene.resolve?.();scene.resolve=null}
  function stop(scene){release(scene);scene.motion?.dispose();scene.motion=null}
  function cancel(theme){
    notify('cancel',{target:theme??null})
    epoch++
    const keep=theme==null?[...rings].reverse().find(scene=>scene.committed)||base:[base,...rings].reverse().find(scene=>scene.theme===theme)
    for(const scene of [base,...rings])if(scene!==keep)stop(scene)
    base=keep||make(theme);stop(base);base.ring=false;base.done=false;rings=[]
    update();changing(false)
  }
  function complete(scene,reason){
    if(!rings.includes(scene)||scene.done)return
    notify('completed',{key:scene.key,reason})
    scene.done=true;release(scene)
    const promoted=[]
    // A later ring can finish first; it may not uncover an unfinished lower ring.
    while(rings[0]?.done){
      notify('will-promote',{key:rings[0].key,previousBase:base.key})
      stop(base);base=rings.shift();base.ring=false
      // The appearance renderer still references this radius until Vue patches
      // the new base/exclusions. Cancelling now resets it to zero too early.
      if(base.motion){base.motion.promote({deferDispose:true});promoted.push(base.motion);base.motion=null}
      notify('promoted',{key:base.key})
    }
    update();changing(rings.length>0)
    if(promoted.length){
      const dispose=()=>promoted.forEach(motion=>motion.dispose())
      Promise.resolve(flush()).then(dispose,dispose)
    }
  }
  function pause(progress){rings.forEach(scene=>{if(!scene.done)scene.motion?.pause(progress)})}
  function resume(){
    for(const scene of rings){
      if(!scene.done)scene.motion?.resume()
    }
  }
  function run(theme,commit,point,{width,height,reduced=false,diagnostic={},onStarted}={}){
    const requested=epoch
    const setup=queue.then(async()=>{
      if(requested!==epoch)return
      if(diagnostic.maxActive&&rings.length>=diagnostic.maxActive){notify('ignored',{clickId:diagnostic.clickId,theme,limit:diagnostic.maxActive});return}
      if(reduced){commit();cancel(theme);await flush();onStarted?.();return}
      const scene=make(theme,true,point||{x:width/2,y:height/2})
      scene.clickId=diagnostic.clickId
      scene.radius=revealRadius(scene.point.x,scene.point.y,width,height);scene.mask=!!diagnostic.mask
      const requestedAt=driver.requestedAt?.()
      const settled=new Promise(resolve=>scene.resolve=resolve)
      try{
        rings.push(scene);changing(true);commit();scene.committed=true;update();notify('accepted',{key:scene.key,clickId:scene.clickId});await flush()
        if(requested!==epoch)return {settled}
        scene.motion=driver.start(scene,{onStarted,onComplete:reason=>complete(scene,reason),diagnostic,requestedAt})
        notify('animation-started',{key:scene.key})
        return {settled}
      }catch(error){notify('setup-error',{key:scene.key,message:String(error)});cancel(theme);return {settled}}
    })
    queue=setup.then(()=>{},()=>{})
    return setup.then(result=>result?.settled)
  }
  update()
  return {run,cancel,pause,resume}
}
