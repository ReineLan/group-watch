// User-operated, opt-in measurements. Does not drive theme changes.
export function installPerformanceDiagnostics(panel,{coldReset,coldStorageKey,context=()=>null}={}){
  let stopRecording=null,report=null
  let recordScenarioClick=null
  const coldKey=coldStorageKey||'theme-cold-double-implementations-v2'
  const startupControl=()=>({imagePreparation:document.documentElement.dataset.imagePreparation??null,
    imagePreparationMs:Number(document.documentElement.dataset.imagePreparationMs||0),videoControl:document.documentElement.dataset.videoControl??null})
  let coldRuns=[],resetPending=false
  if(coldReset){try{coldRuns=JSON.parse(sessionStorage.getItem(coldKey)||'[]')}catch{coldRuns=[]}}
  const start=document.createElement('button'),stop=document.createElement('button'),download=document.createElement('button')
  const status=document.createElement('div')
  start.textContent='开始新记录';stop.textContent='停止记录';download.textContent='导出性能 JSON'
  stop.disabled=download.disabled=true
  if(coldReset&&coldRuns.length)download.disabled=false
  const percentile=(values,p)=>values.length?[...values].sort((a,b)=>a-b)[Math.ceil(values.length*p)-1]:null
  function summarize(batch){
    const values=batch.frames
    return {kind:batch.kind,clicks:batch.clicks.length,rings:batch.rings.length,frameCount:values.length,
      frameP50:percentile(values,.5),frameP95:percentile(values,.95),frameMax:values.length?Math.max(...values):null,
      over50:values.filter(n=>n>50).length,over50Fraction:values.length?values.filter(n=>n>50).length/values.length:null,
      peakLayers:batch.peakLayers,longTaskCount:batch.longTasks.length,
      longTaskMs:batch.longTasks.reduce((sum,t)=>sum+t.duration,0)}
  }
  function staticSummary(batch){
    if(!batch.staticWindow?.end)return null
    const {start,end}=batch.staticWindow
    const tasks=batch.longTasks.filter(t=>t.start<end&&t.start+t.duration>start)
      .map(t=>({...t,duration:Math.min(end,t.start+t.duration)-Math.max(start,t.start)}))
    return summarize({...batch,frames:batch.staticFrames||[],longTasks:tasks})
  }
  start.onclick=()=>{
    if(stopRecording)return
    const host=document.querySelector('.scene-transition-host')
    const activeNodes=()=>[...host.children].filter(node=>node.dataset?.sceneRole!=='base')
    if(!host||activeNodes().length){status.textContent='请等当前圆形扩散结束，再开始记录。';return}
    report={startedAt:new Date().toISOString(),userAgent:navigator.userAgent,diagnosticMode:document.documentElement.dataset.themeDebug,
      startupControl:startupControl(),
      implementation:document.documentElement.dataset.coldImplementation??null,
      coldReset:coldReset?{method:'page-reload',resets:['application image preloader maps','DOM and CSS animation instances','video element and canvas mirrors'],notGuaranteed:['HTTP cache','browser decoded image cache','GPU cache','decoder internals']}:null,
      glowMode:document.documentElement.dataset.glowMode??null,glowGain:Number(document.documentElement.dataset.glowGain??1),
      viewport:[innerWidth,innerHeight,devicePixelRatio],scripts:[...document.scripts].map(s=>s.src).filter(Boolean),
      appearanceArchitecture:document.querySelector('.ui-appearance-layer')?'p3-card-full-v1':null,diagnosticContext:context(),
      sceneArchitecture:'vue-scenes-e3-v1',batches:[],interruptions:[],note:'帧间隔是RAF调度指标；首帧是首次观测到正半径，不是像素呈现时间。未测GPU或总CPU。Vue版底层常驻，完成的圆原位提升，promoted表示成为底层，并非移除。sceneSetups的vueMountMs包含从状态发布到nextTick后的Vue更新及挂载钩子，与旧版captureMs不能直接比较或相加；animationClockMs为本实例CSS动画加入公共时钟的同步调用耗时。视频draw只表示JS绘制调用。requestedAt为performance.now绝对时间，其余事件相对本记录起点。'}
    let batch=null,previous=null,raf,taskObserver
    const tracked=new Map(),waiting=new Set(),mountedAt=new WeakMap(),origin=performance.now()
    const now=()=>performance.now()-origin
    function begin(){
      if(batch)return
      batch={kind:(coldReset?document.documentElement.dataset.coldImplementation==='mask':new URLSearchParams(location.search).get('circle-kind')==='mask')?'mask':'clip',diagnosticMode:document.documentElement.dataset.themeDebug,
        startupControl:startupControl(),
        implementation:document.documentElement.dataset.coldImplementation??null,
        glowMode:document.documentElement.dataset.glowMode??null,glowGain:Number(document.documentElement.dataset.glowGain??1),
        start:now(),viewport:[innerWidth,innerHeight,devicePixelRatio],hidden:document.hidden,
        glowBlend:getComputedStyle(document.querySelector('.scene-glow')).mixBlendMode,
        clicks:[],rings:[],sceneSetups:[],frames:[],longTasks:[],peakLayers:0}
      report.batches.push(batch);previous=null
    }
    recordScenarioClick=event=>{
      if(batch?.clicks.length)return
      begin()
      batch.clicks.push({selection:event.target.textContent.trim(),eventTime:event.timeStamp-origin,handler:now()})
    }
    function click(event){
      const radio=event.target.closest('[role=radio]'),button=event.target.closest('button')
      if(radio&&radio.getAttribute('aria-checked')==='true')return
      if(!radio&&!button?.textContent.startsWith('固定圆心：'))return
      begin()
      batch.clicks.push({selection:(radio||button).textContent.trim(),eventTime:event.timeStamp-origin,handler:now()})
    }
    document.addEventListener('click',click,true)
    function phase(event){
      if(event.detail.name==='start')begin()
      if(!batch)return
      const time=now(),detail=event.detail
      if(detail.name==='start'){batch.videoScenario=detail.videoScenario;batch.choices=detail.choices}
      ;(batch.phases??=[]).push({...detail,time})
      if(detail.name==='static-start'){
        batch.staticWindow={start:time,expectedRadiusProgress:.6,expectedRings:detail.count,actualLayers:detail.layers,startState:detail.state}
        batch.staticFrames=[]
      }
      if(detail.name==='static-end'&&batch.staticWindow){
        const window=batch.staticWindow
        window.end=time;window.endState=detail.state
        const paused=state=>state?.filter(node=>node.animations.length===1&&node.animations[0].playState==='paused')
        const before=paused(window.startState),after=paused(window.endState)
        window.valid=window.actualLayers===window.expectedRings+1&&before?.length===window.expectedRings&&after?.length===window.expectedRings&&
          before.every((node,index)=>node.radius===after[index].radius&&node.animations[0].currentTime===after[index].animations[0].currentTime)
      }
    }
    window.addEventListener('theme-performance-phase',phase)
    function mounted(node){
      if(tracked.has(node)||node.dataset?.sceneRole==='base')return true
      const animation=node.getAnimations().find(a=>a.effect?.getKeyframes().some(k=>k['--theme-reveal-radius']))
      // Vue's DOM insertion can precede the controller's post-nextTick animation.
      if(!animation)return false
      begin()
      if(node.sceneTimings)batch.sceneSetups.push({theme:node.dataset.theme,role:'ring',...node.sceneTimings})
      const ring={theme:node.dataset.theme,sceneStructure:node.dataset.sceneStructure||'root-clip',kind:node.style.maskImage&&node.style.maskImage!=='none'?'mask':'clip',mounted:mountedAt.get(node)??now(),duration:animation.effect.getTiming().duration}
      batch.rings.push(ring);tracked.set(node,ring)
      animation.finished.then(()=>ring.finished=now(),()=>ring.cancelled=now())
      return true
    }
    const observer=new MutationObserver(records=>{
      for(const record of records){
        for(const node of record.addedNodes){
          if(node.nodeType!==1)continue
          mountedAt.set(node,now())
          if(!mounted(node))waiting.add(node)
        }
        for(const node of record.removedNodes){waiting.delete(node);const ring=tracked.get(node);if(ring)ring.removed=now()}
      }
      if(batch)batch.peakLayers=Math.max(batch.peakLayers,host.children.length)
    })
    observer.observe(host,{childList:true})
    try{
      taskObserver=new PerformanceObserver(list=>{
        for(const entry of list.getEntries()){
          const time=entry.startTime-origin
          const owner=[...report.batches].reverse().find(b=>time>=b.start&&(b.end==null||time<=b.end))
          if(owner)owner.longTasks.push({start:time,duration:entry.duration})
        }
      });taskObserver.observe({type:'longtask',buffered:false})
      report.longTasksSupported=true
    }catch{report.longTasksSupported=false}
    function interruption(type){report.interruptions.push({type,time:now(),viewport:[innerWidth,innerHeight,devicePixelRatio],hidden:document.hidden})}
    const visibility=()=>interruption('visibilitychange'),resize=()=>interruption('resize')
    document.addEventListener('visibilitychange',visibility);window.addEventListener('resize',resize)
    function frame(time){
      for(const node of waiting)if(mounted(node))waiting.delete(node)
      if(batch){
        if(previous!=null)batch.frames.push(time-previous)
        if(previous!=null&&batch.staticWindow&&previous-origin>=batch.staticWindow.start&&batch.staticWindow.end==null)batch.staticFrames.push(time-previous)
        previous=time
        for(const [node,ring] of tracked){
          if(node.dataset?.sceneRole==='base'&&ring.promoted==null)ring.promoted=now()
          if(ring.firstFrame!=null||ring.removed!=null)continue
          if(parseFloat(getComputedStyle(node).getPropertyValue('--theme-reveal-radius'))>0)ring.firstFrame=time-origin
        }
        if(batch.rings.length&&!activeNodes().length){
          batch.end=now();batch.summary=summarize(batch);batch.staticSummary=staticSummary(batch)
          status.textContent=`已记录 ${report.batches.length} 轮；最近 ${batch.kind}，${batch.rings.length} 圆，帧间隔 P95 ${batch.summary.frameP95?.toFixed(1)}ms。`
          batch=null;tracked.clear();previous=null
          if(coldReset&&!resetPending){
            resetPending=true
            for(const button of panel.querySelectorAll('button'))button.disabled=true
            // Allow the final long-task callback to arrive before sealing this run.
            setTimeout(async()=>{
              stopRecording?.()
              coldRuns.push(report)
              try{sessionStorage.setItem(coldKey,JSON.stringify(coldRuns))}
              catch{status.textContent='保存累计记录失败，已停止自动刷新；请先导出性能 JSON。';download.disabled=false;resetPending=false;return}
              try{await coldReset()}catch{status.textContent='重置失败，记录已保存；请导出后刷新。';download.disabled=false;resetPending=false;return}
              location.reload()
            },100)
          }
        }
      }
      raf=requestAnimationFrame(frame)
    }
    raf=requestAnimationFrame(frame)
    stopRecording=()=>{
      cancelAnimationFrame(raf);observer.disconnect();taskObserver?.disconnect()
      document.removeEventListener('click',click,true);document.removeEventListener('visibilitychange',visibility);window.removeEventListener('resize',resize)
      window.removeEventListener('theme-performance-phase',phase)
      if(batch){batch.incomplete=true;batch.end=now()}
      report.endedAt=new Date().toISOString();report.remainingLayers=activeNodes().length;report.baseLayers=host.children.length-report.remainingLayers
      // Recompute after the final long-task callback, which can arrive after a batch ends.
      for(const item of report.batches){
        item.summary=summarize(item)
        item.staticSummary=staticSummary(item)
        for(const ring of item.rings){
          ring.firstFrameFromMount=ring.firstFrame!=null?ring.firstFrame-ring.mounted:null
          ring.finishedFromMount=ring.finished!=null?ring.finished-ring.mounted:null
        }
        item.firstFrameFromClick=item.rings[0]?.firstFrame!=null&&item.clicks.length?item.rings[0].firstFrame-item.clicks[0].eventTime:null
      }
      stopRecording=null;start.disabled=false;stop.disabled=true;download.disabled=false
      recordScenarioClick=null
      delete document.documentElement.dataset.themePerformanceRecording
      status.textContent=`记录已停止，共 ${report.batches.length} 轮，可导出。`
    }
    document.documentElement.dataset.themePerformanceRecording='true'
    start.disabled=true;stop.disabled=false;download.disabled=true;status.textContent='正在记录：请手动切换主题；可在两种圆形实现之间切换，无需刷新。'
  }
  stop.onclick=()=>stopRecording?.()
  download.onclick=()=>{
    if((!report&&!coldRuns.length)||stopRecording)return
    const runs=coldReset?[...coldRuns,...(report&&!coldRuns.includes(report)?[report]:[])]:[]
    const data=coldReset?{...(report||coldRuns.at(-1)),
      batches:runs.flatMap((run,index)=>run.batches.map(batch=>({...batch,pageRun:index+1,recordingStartedAt:run.startedAt}))),
      interruptions:runs.flatMap((run,index)=>run.interruptions.map(event=>({...event,pageRun:index+1}))),
      pageRuns:runs.map(run=>({startedAt:run.startedAt,endedAt:run.endedAt,interruptions:run.interruptions,remainingLayers:run.remainingLayers,baseLayers:run.baseLayers,scripts:run.scripts})),
      timeNote:'Each pageRun has an independent recording time origin. Every run is a first double-circle trial after page reload; do not discard a warmup per group.'}:report
    const url=URL.createObjectURL(new Blob([JSON.stringify(data,null,2)],{type:'application/json'}))
    const link=document.createElement('a');link.href=url;link.download=`circle-performance-${Date.now()}.json`;link.click()
    setTimeout(()=>URL.revokeObjectURL(url),1000)
  }
  panel.append(start,stop,download,status)
  const note=document.createElement('div')
  note.textContent='每种实现、每种场景先预热，再各做3轮1/2/3圆。静态60%单独导出staticSummary（不含建层、稳定等待和恢复）；保持窗口前台及尺寸不变，轮间等待清理。Trace请关闭本记录器与尺寸采样，使用浏览器Performance录制，搜索circle-标记。'
  panel.append(note)
  if(coldReset){
    const clear=document.createElement('button');clear.textContent='清空本实验累计记录'
    clear.onclick=()=>{if(stopRecording||resetPending)return;sessionStorage.removeItem(coldKey);coldRuns=[];report=null;download.disabled=true;status.textContent='累计记录已清空。'}
    panel.append(clear)
    status.textContent=`页面级冷启动：已保存 ${coldRuns.length} 轮；点击双圆即可自动记录，结束后自动刷新。`
    note.textContent='每轮自动刷新，重建页面缓存与视频元素；不保证清空HTTP、浏览器解码或GPU缓存。记录保存在本标签页，刷新后可累计导出；每轮都是首次双圆，不作预热剔除。'
  }
  return {start:event=>{if(!stopRecording&&!resetPending)start.onclick();if(event&&stopRecording)recordScenarioClick?.(event)}}
}
