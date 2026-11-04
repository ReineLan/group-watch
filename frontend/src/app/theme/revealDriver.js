import {revealTimeForRadius} from './reveal.js'

// One logical Reveal, potentially several visual targets. Targets do not own
// independent completion, timeout or pause/resume state.
export function revealDriver({targetsFor,animate=(node,frames,options)=>node.animate(frames,options),setTimer=setTimeout,clearTimer=clearTimeout,timingEnabled=()=>globalThis.document?.documentElement?.dataset.themePerformanceRecording==='true'}){
  return {
    requestedAt:()=>timingEnabled()?performance.now():undefined,
    start(scene,{onStarted,onComplete=()=>{},diagnostic={},requestedAt}={}){
      const targets=targetsFor(scene)
      if(!targets.length)throw Error('Scene renderer did not mount the requested scene')
      const animations=[]
      let timer,finished=false,disposed=false
      function clearTimerOnly(){clearTimer(timer);timer=undefined}
      function finish(reason){if(finished||disposed)return;finished=true;clearTimerOnly();onComplete(reason)}
      function dispose(){
        if(disposed)return
        disposed=true;clearTimerOnly();for(const animation of animations)animation.cancel()
      }
      // Keep the primary target's existing WAAPI startup semantics. Once ready,
      // followers join that exact clock; no per-frame JS radius calculation.
      function syncClocks(){
        const primary=animations[0]
        if(animations.length<2)return
        Promise.resolve(primary.ready).then(()=>{
          if(disposed||primary.startTime==null)return
          for(const animation of animations.slice(1))animation.startTime=primary.startTime
        },()=>{})
      }
      try{
        for(const target of targets){
          const node=target.node||target,property=target.property||'--theme-reveal-radius'
          if(requestedAt!=null){node.sceneTimings??={};node.sceneTimings.requestedAt=requestedAt;node.sceneTimings.vueMountMs=performance.now()-requestedAt}
          const animation=animate(node,[{[property]:'0px'},{[property]:`${scene.radius}px`}],{duration:950,easing:'cubic-bezier(.22,.8,.2,1)',fill:'forwards'})
          animations.push(animation)
          // Secondary finished promises must not become unhandled rejections.
          if(animations.length>1)animation.finished.catch(()=>{})
        }
        onStarted?.()
        timer=setTimer(()=>finish('fallback'),2200)
        animations[0].finished.then(()=>finish('animation-finished'),()=>finish('animation-rejected'))
        syncClocks()
      }catch(error){dispose();throw error}
      const handle={
        get currentTime(){return animations[0].currentTime},
        get playState(){return animations[0].playState},
        pause(progress){
          if(finished||disposed)return
          clearTimerOnly()
          for(const animation of animations){animation.pause();if(progress!=null)animation.currentTime=revealTimeForRadius(progress)}
        },
        resume(){
          if(finished||disposed)return
          for(const animation of animations)animation.play()
          syncClocks();clearTimerOnly()
          timer=setTimer(()=>finish('fallback'),Math.max(0,950-Number(animations[0].currentTime||0))+1250)
        },
        promote({deferDispose=false}={}){
          for(const target of targets){if(target.property)continue;const node=target.node||target;node.style.clipPath='none';node.style.maskImage='none';node.style.webkitMaskImage='none'}
          if(!deferDispose)dispose()
        },
        dispose,
      }
      if(diagnostic.hold)handle.pause(diagnostic.holdProgress??.4)
      return handle
    },
  }
}
