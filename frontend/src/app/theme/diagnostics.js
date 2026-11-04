import {installPerformanceDiagnostics} from './performanceDiagnostics.js'
import {startupExperiment} from './startupExperiment.js'
import {installOverlapDiagnostics} from './overlapDiagnostics.js'
// Opt-in, one-variable experiments. No observers, sampling or styles on normal pages.
export const diagnosticModes={
  baseline:'当前正式合成条件',composite:'圆形与混合合成实验',glow:'辉光对比（四模式 + ×5）',colors:'分层底色',bounds:'容器边界',
  isolation:'仅统一 isolation',contain:'仅移除 contain',
  filter:'仅关闭 filter',blend:'仅关闭全部混合',
  'glow-blend':'仅关闭辉光 screen','shadow-blend':'仅关闭树影 multiply',
  backdrop:'仅关闭背景模糊',
  'no-clip':'A2 · screen，移除圆形裁剪',
  'no-will-change':'B1 · 仅移除辉光 will-change',
  'pause-glow':'B2 · 仅暂停辉光动画',
  'fixed-glow-opacity':'B3 · 保留动画，固定 opacity=.7',
  'glow-inset-zero':'C2 · 辉光 inset:0',
  'glow-inset-compensated':'C3 · inset:0，保留原渐变范围',
  'glow-viewport':'C4 · 辉光使用视口宽高',
  'pseudo-bounds':'D4 · 仅伪元素边界',
  'group-filter':'E1 · 内部合成组 filter:opacity(1)',
  'group-opacity':'E2 · 内部合成组 opacity:0.999',
  'ring-filter':'E3 · 仅圆形层内部组 filter:opacity(1)',
  'cold-double':'首次双圆 · 每轮刷新重置页面缓存',
  'image-startup':'独立对照 · 图片提前解码',
  'video-startup':'独立对照 · 同场景视频开关',
  overlap:'连续点击 · 数量/上限/混合与状态审计',
  mobile:'手机闪烁 · 正式条件与独立变量对照',
  queued:'260ms启动间隔 · 待执行队列6项',
  'p3-ui':'P3.2 · 登录卡片背景跟随同一Reveal',
}
export function installThemeDiagnostics({selectTheme,resetTheme,prepareImages,pause,resume}={}){
  const params=new URLSearchParams(location.search)
  const mode=params.get('theme-debug')
  if(!Object.hasOwn(diagnosticModes,mode))return
  if(['overlap','queued','p3-ui','mobile'].includes(mode))return installOverlapDiagnostics({selectTheme,resetTheme,prepareImages,pause,resume})
  const startupControl=startupExperiment(location.search)
  const autoReset=mode==='cold-double'||!!startupControl
  let preparationReady=!startupControl?.prepareImages,scenarioButtons=[]
  const implementations={clip:'原始 clip + screen',mask:'mask + screen',normal:'clip + normal',e3:'E3 · 圆形内部组 filter'}
  const implementation=Object.hasOwn(implementations,params.get('implementation'))?params.get('implementation'):'clip'
  const experiment={mask:mode==='cold-double'?implementation==='mask':params.get('circle-kind')==='mask',hold:false,blend:'screen',boundary:'none'}
  const controller={revealOptions:()=>['composite','cold-double'].includes(mode)?{mask:experiment.mask,hold:experiment.hold,holdProgress:experiment.holdProgress}:{}}
  let performanceScenario='moving',scenarioSequence=0
  const sampling=params.get('diag-sample')!=='0',showPanel=params.get('diag-ui')!=='0'
  const root=document.documentElement
  root.dataset.themeDebug=mode
  if(autoReset)root.dataset.coldImplementation=startupControl?'e3':implementation
  if(startupControl){root.dataset.imagePreparation=preparationReady?'not-prepared':'pending';root.dataset.videoControl=startupControl.videoEnabled?'enabled':'disabled'}
  const glowModes={original:'原始辉光（screen）',normal:'修改混合模式辉光（normal）',plain:'普通辉光（取消 screen）',off:'完全关闭'}
  let glowMode=Object.hasOwn(glowModes,params.get('glow-mode'))?params.get('glow-mode'):'original'
  let glowGain=params.get('glow-gain')==='5'?5:1
  if(mode==='cold-double'){glowMode=implementation==='normal'?'normal':'original';glowGain=1}
  function applyGlow(){
    if(!['glow','cold-double'].includes(mode))return
    root.dataset.glowMode=glowMode;root.dataset.glowGain=String(glowGain)
  }
  applyGlow()
  const style=document.createElement('style')
  style.textContent=`
    html[data-theme-debug=colors]{background:#ff00ff!important}
    [data-theme-debug=colors] .scene-stage{background:#ff0000!important}
    [data-theme-debug=colors] .scene-transition-host{background:#00ffff!important}
    [data-theme-debug=colors] .scene-transition-source{background:#00ff00!important}
    [data-theme-debug=colors] .theme-reveal-layer{background:#0000ff!important}
    [data-theme-debug=colors] .theme-reveal-layer[style*="circle("]{background:#ffff00!important}
    [data-theme-debug=bounds] .scene-transition-source{outline:3px solid #00ff00;outline-offset:-3px}
    [data-theme-debug=bounds] .theme-reveal-layer{outline:3px solid #ffff00;outline-offset:-6px}
    [data-theme-debug=bounds] .scene-intro-veil{outline:2px solid #ff00ff}
    [data-theme-debug=isolation] .background-scene{isolation:isolate!important}
    [data-theme-debug=contain] :is(.scene-stage,.background-scene,.scene-transition-host){contain:none!important}
    [data-theme-debug=filter] .scene-stage *{filter:none!important}
    [data-theme-debug=blend] .scene-stage *{mix-blend-mode:normal!important}
    [data-theme-debug=glow-blend] .scene-glow{mix-blend-mode:normal!important}
    [data-theme-debug=shadow-blend] .canopy-shadows{mix-blend-mode:normal!important}
    [data-theme-debug=backdrop] body *{backdrop-filter:none!important;-webkit-backdrop-filter:none!important}
    [data-theme-debug=group-filter] .scene-composite-group{filter:opacity(1)!important}
    [data-theme-debug=group-opacity] .scene-composite-group{opacity:.999!important}
    [data-theme-debug=ring-filter] .theme-reveal-layer[style*="circle("]>.scene-composite-group{filter:opacity(1)!important}
    :is([data-theme-debug=image-startup],[data-theme-debug=video-startup]) .theme-reveal-layer[style*="circle("]>.scene-composite-group{filter:opacity(1)!important}
    [data-theme-debug=cold-double][data-cold-implementation=e3] .theme-reveal-layer[style*="circle("]>.scene-composite-group{filter:opacity(1)!important}
    [data-theme-debug=composite] .scene-glow{mix-blend-mode:var(--diagnostic-blend,screen)!important}
    [data-theme-debug=composite] [data-diagnostic-boundary]{outline:1px solid red!important}
    [data-theme-debug=no-clip] .theme-reveal-layer{clip-path:none!important}
    [data-theme-debug=no-will-change] .scene-glow{will-change:auto!important}
    [data-theme-debug=pause-glow] .scene-glow{animation-play-state:paused!important}
    [data-theme-debug=fixed-glow-opacity] .scene-glow{opacity:.7!important}
    [data-theme-debug=glow-inset-zero] .scene-glow{inset:0!important}
    [data-theme-debug=glow-inset-compensated] .scene-glow{inset:0!important;background-size:120% 120%;background-position:center;background-repeat:no-repeat}
    [data-theme-debug=glow-viewport] .scene-glow{inset:auto!important;left:0;top:0;width:100vw;height:100vh}
    [data-theme-debug=pseudo-bounds] .scene-transition-source::after,
    [data-theme-debug=pseudo-bounds] .theme-reveal-layer::after,
    [data-theme-debug=pseudo-bounds] .scene-intro-veil::after{content:'';position:absolute;inset:0;pointer-events:none;box-sizing:border-box;border:3px solid #00ff00}
    [data-theme-debug=pseudo-bounds] .theme-reveal-layer::after{border-color:#ffff00;inset:3px}
    [data-theme-debug=pseudo-bounds] .scene-intro-veil::after{border:2px solid #ff00ff}
    :is([data-theme-debug=glow],[data-theme-debug=cold-double])[data-glow-mode=normal] .scene-glow{mix-blend-mode:normal!important}
    :is([data-theme-debug=glow],[data-theme-debug=cold-double])[data-glow-mode=plain] .scene-glow{mix-blend-mode:initial!important}
    :is([data-theme-debug=glow],[data-theme-debug=cold-double])[data-glow-mode=off] .scene-glow{display:none!important}
    :is([data-theme-debug=glow],[data-theme-debug=cold-double])[data-glow-gain="5"] .scene-glow{background:radial-gradient(ellipse at 15% 16%,rgb(from var(--glow-a) r g b / clamp(0,calc(alpha * 5),1)),transparent 38%),radial-gradient(ellipse at 80% 75%,rgb(from var(--glow-b) r g b / clamp(0,calc(alpha * 5),1)),transparent 45%)!important}
    #theme-diagnostics{position:fixed;left:8px;bottom:8px;z-index:10000;max-width:min(430px,94vw);padding:10px;border:1px solid var(--line-3);border-radius:8px;background:var(--surface);color:var(--ink);font:12px/1.6 system-ui}
    #theme-diagnostics select,#theme-diagnostics button{font:inherit;color:var(--ink);background:var(--surface-2);border:1px solid var(--line-3);margin:4px;padding:4px}
  `
  document.head.append(style)
  // Quiet links have no panel, click listeners, timers or layout reads.
  if(!sampling&&!showPanel)return controller
  const records=[]
  const ids=new WeakMap();let nodeSequence=0
  let sequence=0,current=null
  const box=node=>{
    const r=node.getBoundingClientRect(),s=getComputedStyle(node)
    if(!ids.has(node))ids.set(node,++nodeSequence)
    return {id:ids.get(node),tag:node.tagName,classes:node.className,theme:node.dataset.theme||node.closest('.background-scene')?.dataset.theme,
      rect:{x:r.x,y:r.y,width:r.width,height:r.height},position:s.position,
      clipPath:s.clipPath,maskImage:s.maskImage,outline:s.outline,contain:s.contain,isolation:s.isolation,overflow:s.overflow,
      background:s.backgroundColor,backgroundImage:s.backgroundImage,backgroundSize:s.backgroundSize,
      inset:s.inset,willChange:s.willChange,animationPlayState:s.animationPlayState,
      filter:s.filter,blend:s.mixBlendMode,opacity:s.opacity,
      transform:s.transform,backdrop:s.backdropFilter,
      animations:node.getAnimations({subtree:true}).map(a=>({name:a.animationName||a.transitionProperty||'reveal',time:a.currentTime,state:a.playState}))}
  }
  function sample(record,label){
    record.samples.push({label,elapsed:performance.now()-record.start,theme:root.dataset.theme,glowMode,glowGain,experiment:{...experiment},
      viewport:{width:innerWidth,height:innerHeight,dpr:devicePixelRatio},
      nodes:[...document.querySelectorAll('.scene-stage,.scene-transition-source,.scene-transition-host,.theme-reveal-layer,.scene-composite-group,.scene-intro-veil,.scene-glow,.canopy-shadows,.entry-card')].map(box)})
  }
  function recordSelection(selection,eventTime,point){
    if(!sampling)return
    const record={id:++sequence,start:performance.now(),
      selection,eventTime,point,from:root.dataset.theme,samples:[]}
    records.push(record);if(records.length>12)records.shift()
    current=record
    sample(record,'before')
    for(const delay of [100,300,500,700,1200])setTimeout(()=>{
      if(!records.includes(record))return
      sample(record,`${delay}ms`)
      if(current===record&&showPanel)status.textContent=`已记录 ${records.length} 次切换，最近采样 ${delay}ms`
    },delay)
  }
  if(sampling)document.addEventListener('click',event=>{
    const button=event.target.closest('[role=radio]')
    if(!button||button.getAttribute('aria-checked')==='true')return
    recordSelection(button.textContent.trim(),event.timeStamp,{x:event.clientX,y:event.clientY})
  },true)
  function exportReport(){
    const data={mode,glowMode,glowGain,experiment:{...experiment},sampling,showPanel,userAgent:navigator.userAgent,
      viewport:{width:innerWidth,height:innerHeight,dpr:devicePixelRatio},hidden:document.hidden,
      scripts:[...document.scripts].map(s=>s.src).filter(Boolean),records,
      note:'诊断采样会强制读取布局和样式，不适合作为性能验收数据；elapsed 是实际采样时刻。'}
    const url=URL.createObjectURL(new Blob([JSON.stringify(data,null,2)],{type:'application/json'}))
    const a=document.createElement('a');a.href=url;a.download=`theme-diagnostic-${mode}-${Date.now()}.json`;a.click()
    setTimeout(()=>URL.revokeObjectURL(url),1000)
  }
  if(!showPanel)return controller
  const panel=document.createElement('details');panel.id='theme-diagnostics';panel.open=true
  const title=document.createElement('summary');title.textContent='主题诊断 · 单变量实验';panel.append(title)
  const select=document.createElement('select');select.setAttribute('aria-label','主题诊断实验')
  for(const [value,label] of Object.entries(diagnosticModes)){
    const option=document.createElement('option');option.value=value;option.textContent=label;select.append(option)
  }
  select.value=mode;select.onchange=()=>{
    const url=new URL(location.href);url.searchParams.set('theme-debug',select.value);location.assign(url.href)
  };panel.append(select)
  const sampleLabel=document.createElement('label'),sampleToggle=document.createElement('input')
  sampleToggle.type='checkbox';sampleToggle.checked=sampling
  sampleToggle.onchange=()=>{
    const url=new URL(location.href);url.searchParams.set('diag-sample',sampleToggle.checked?'1':'0');location.assign(url.href)
  }
  sampleLabel.append(sampleToggle,document.createTextNode('记录尺寸（关闭后无采样开销）'));panel.append(sampleLabel)
  const performanceRecorder=['composite','glow','group-filter','group-opacity','ring-filter','cold-double','image-startup','video-startup'].includes(mode)?
    installPerformanceDiagnostics(panel,{coldReset:autoReset?()=>resetTheme('chunxi'):null,coldStorageKey:startupControl?`theme-${mode}-runs-v1`:undefined}):null
  if(startupControl){
    const label=document.createElement('label');label.textContent='独立对照条件：'
    const menu=document.createElement('select');menu.setAttribute('aria-label','独立对照条件')
    const options=mode==='image-startup'?{none:'不提前准备目标图片',decoded:'提前decode目标图片'}:{'1':'澄漪视频启用','0':'澄漪视频禁用'}
    for(const [value,text] of Object.entries(options)){const option=document.createElement('option');option.value=value;option.textContent=text;menu.append(option)}
    menu.value=mode==='image-startup'?(startupControl.prepareImages?'decoded':'none'):(startupControl.videoEnabled?'1':'0')
    menu.onchange=()=>{const url=new URL(location.href);url.searchParams.set(mode==='image-startup'?'image-preparation':'video-enabled',menu.value);location.assign(url.href)}
    label.append(menu);panel.append(label)
    const explanation=document.createElement('div')
    explanation.textContent=mode==='image-startup'?'固定E3、无视频、春熙→浮梦→晴庭，只改变目标图片是否提前decode。':'固定E3、春熙→浮梦→澄漪，两种条件都先decode相同图片，只改变澄漪视频开关。'
    panel.append(explanation)
    if(startupControl.prepareImages){
      const prepare=document.createElement('button');prepare.textContent='准备本轮目标图片'
      const state=document.createElement('div');state.textContent='先准备图片，成功后才能运行双圆。准备不切换主题、不启动视频。'
      prepare.onclick=async()=>{
        prepare.disabled=true
        try{
          const before=performance.now(),results=await prepareImages(startupControl.images)
          if(!results.every(Boolean))throw Error('目标图片decode未全部成功')
          root.dataset.imagePreparation='decoded';root.dataset.imagePreparationMs=String(performance.now()-before)
          preparationReady=true;for(const button of scenarioButtons)button.disabled=false
          state.textContent='图片decode完成，可以运行双圆。该准备时间不计入启动指标。'
        }catch(error){prepare.disabled=false;state.textContent=`准备失败：${error.message}，请重试。`}
      }
      panel.append(prepare,state)
    }
  }
  if(mode==='composite'){
    function menu(label,options,value,change){
      const row=document.createElement('label');row.textContent=label
      const input=document.createElement('select');input.setAttribute('aria-label',label)
      for(const [key,text] of Object.entries(options)){
        const option=document.createElement('option');option.value=key;option.textContent=text;input.append(option)
      }
      input.value=value;input.onchange=()=>change(input.value);row.append(input);panel.append(row)
    }
    menu('圆形实现',{clip:'原始 clip-path',mask:'径向 mask-image'},experiment.mask?'mask':'clip',value=>{
      experiment.mask=value==='mask'
      const url=new URL(location.href);url.searchParams.set('circle-kind',value);history.replaceState(null,'',url.href)
    })
    menu('性能场景',{moving:'正常扩散',static60:'静态60%：稳定500ms后记录3秒'},'moving',value=>performanceScenario=value)
    const holdLabel=document.createElement('label'),hold=document.createElement('input')
    hold.type='checkbox';hold.onchange=()=>experiment.hold=hold.checked
    holdLabel.append(hold,document.createTextNode('新圆暂停在半径40%'));panel.append(holdLabel)
    for(const [text,action] of [['当前圆暂停',()=>pause?.()],['当前圆定位半径40%并暂停',()=>pause?.(.4)],['恢复原动画',()=>resume?.()]]){
      const button=document.createElement('button');button.textContent=text;button.onclick=action;panel.append(button)
    }
    menu('辉光混合',{screen:'screen（原始）',lighten:'lighten','plus-lighter':'plus-lighter',overlay:'overlay',normal:'normal（对照）'},'screen',value=>{
      experiment.blend=value;root.style.setProperty('--diagnostic-blend',value)
    })
    let outlined
    function markBoundary(){
      const host=document.querySelector('.scene-transition-host'),first=host?.firstElementChild,last=host?.lastElementChild
      const node=experiment.boundary==='glow'?(last||document.querySelector('.scene-transition-source'))?.querySelector('.scene-glow'):
        experiment.boundary==='old'?first:experiment.boundary==='new'?(last!==first?last:null):experiment.boundary==='host'?host:null
      if(node===outlined)return
      outlined?.removeAttribute('data-diagnostic-boundary');outlined=node
      outlined?.setAttribute('data-diagnostic-boundary','')
    }
    menu('单节点描边',{none:'关闭',glow:'最上层场景的辉光',old:'底层旧场景副本',new:'最上层新圆副本',host:'transition host'},'none',value=>{
      experiment.boundary=value;markBoundary()
    })
    const observer=new MutationObserver(()=>{if(experiment.boundary!=='none')markBoundary()})
    observer.observe(document.body,{childList:true,subtree:true})
    const hint=document.createElement('div')
    hint.textContent='一次只改一项。圆形实现与自动暂停作用于下一次切换；暂停不停止辉光/花瓣，不重建动画，恢复后沿原进度继续。40%指最终半径，已反解原缓动。描边只标记一个节点，副本清理后随目标更新。'
    panel.append(hint)
  }
  if(selectTheme&&resetTheme){
    let running=false
    async function runScenario(count,withoutVideo=false,event){
      if(running)return
      if(!preparationReady)return
      if(startupControl){count=2;withoutVideo=mode==='image-startup'}
      if(autoReset)performanceRecorder.start(event)
      running=true;single.disabled=double.disabled=triple.disabled=noVideoDouble.disabled=true
      const savedHold=experiment.hold,savedProgress=experiment.holdProgress
      const staticMode=performanceScenario==='static60',scenarioId=++scenarioSequence
      const prefix=`circle-${scenarioId}-${experiment.mask?'mask':'clip'}-${count}-${staticMode?'static60':'moving'}`
      const phase=(name,extra={})=>{
        performance.mark(`${prefix}:${name}`)
        window.dispatchEvent(new CustomEvent('theme-performance-phase',{detail:{name,scenarioId,prefix,count,kind:experiment.mask?'mask':'clip',staticMode,...extra}}))
      }
      const staticState=()=>[...document.querySelector('.scene-transition-host').children].map(node=>({
        theme:node.dataset.theme,radius:getComputedStyle(node).getPropertyValue('--theme-reveal-radius'),
        animations:node.getAnimations().filter(animation=>animation.effect?.getKeyframes().some(frame=>frame['--theme-reveal-radius']))
          .map(animation=>({playState:animation.playState,currentTime:animation.currentTime}))
      }))
      try{
        await resetTheme('chunxi')
        await new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)))
        if(staticMode){experiment.hold=true;experiment.holdProgress=.6}
        phase('start',{videoScenario:startupControl?`${mode}:${root.dataset.imagePreparation}:${root.dataset.videoControl}`:withoutVideo||count===1?'without-video':'includes-shuizhong',choices:withoutVideo?['feihua','huadian']:['feihua','shuizhong','huadian'].slice(0,count)})
        const point={x:Math.round(innerWidth*.89),y:Math.round(innerHeight*.94)}
        const choices=withoutVideo?['feihua','huadian']:['feihua','shuizhong','huadian'].slice(0,count),pending=[]
        for(const [index,id] of choices.entries()){
          if(index)await new Promise(resolve=>setTimeout(resolve,200))
          recordSelection(id,performance.now(),point)
          pending.push(selectTheme(id,point))
        }
        if(staticMode){
          await new Promise(resolve=>setTimeout(resolve,500))
          phase('static-start',{layers:document.querySelector('.scene-transition-host')?.children.length,state:staticState()})
          await new Promise(resolve=>setTimeout(resolve,3000))
          phase('static-end',{state:staticState()})
          performance.measure(`${prefix}:static`,`${prefix}:static-start`,`${prefix}:static-end`)
          resume?.()
        }
        await Promise.all(pending)
        phase('end');performance.measure(prefix,`${prefix}:start`,`${prefix}:end`)
      }finally{
        experiment.hold=savedHold;experiment.holdProgress=savedProgress
        running=false;single.disabled=double.disabled=triple.disabled=noVideoDouble.disabled=false
      }
    }
    const single=document.createElement('button');single.textContent='固定圆心：单次';single.onclick=event=>runScenario(1,false,event)
    const double=document.createElement('button');double.textContent='固定圆心：双圆';double.onclick=event=>runScenario(2,false,event)
    const triple=document.createElement('button');triple.textContent='固定圆心：三圆';triple.onclick=event=>runScenario(3,false,event)
    const noVideoDouble=document.createElement('button');noVideoDouble.textContent='固定圆心：双圆（无视频）';noVideoDouble.onclick=event=>runScenario(2,true,event)
    panel.append(single,double,triple,noVideoDouble)
    scenarioButtons=[single,double,triple,noVideoDouble]
    if(startupControl){single.hidden=triple.hidden=noVideoDouble.hidden=true;double.disabled=!preparationReady}
    if(mode==='cold-double'){single.hidden=true;triple.hidden=true}
    const explanation=document.createElement('div')
    explanation.textContent='圆心固定为视口 (89%,94%)；重置春熙后依次浮梦→澄漪→晴庭，取前1/2/3项，间隔目标200ms。双圆（无视频）改为浮梦→晴庭；普通双圆包含澄漪。实际镜像数与视频就绪状态见JSON。静态场景保留暂停动画，特效继续运行，测量3秒后自动恢复并清理。Trace 可搜索 circle- 标记。'
    panel.append(explanation)
  }
  if(mode==='cold-double'){
    const label=document.createElement('label');label.textContent='对比方案：'
    const implementationSelect=document.createElement('select');implementationSelect.setAttribute('aria-label','对比方案')
    for(const [value,text] of Object.entries(implementations)){
      const option=document.createElement('option');option.value=value;option.textContent=text;implementationSelect.append(option)
    }
    implementationSelect.value=implementation
    implementationSelect.onchange=()=>{
      const url=new URL(location.href);url.searchParams.set('implementation',implementationSelect.value)
      for(const key of ['circle-kind','glow-mode','glow-gain'])url.searchParams.delete(key)
      location.assign(url.href)
    }
    label.append(implementationSelect);panel.append(label)
  }
  if(mode==='glow'){
    const row=document.createElement('div')
    const label=document.createElement('label');label.textContent='辉光模式：'
    const glowSelect=document.createElement('select');glowSelect.setAttribute('aria-label','辉光模式')
    for(const [value,text] of Object.entries(glowModes)){
      const option=document.createElement('option');option.value=value;option.textContent=text;glowSelect.append(option)
    }
    glowSelect.value=glowMode
    function updateGlow(){
      applyGlow()
      const url=new URL(location.href);url.searchParams.set('glow-mode',glowMode);url.searchParams.set('glow-gain',String(glowGain))
      history.replaceState(null,'',url.href)
    }
    glowSelect.onchange=()=>{glowMode=glowSelect.value;updateGlow()}
    label.append(glowSelect);row.append(label)
    const gainLabel=document.createElement('label'),gain=document.createElement('input')
    gain.type='checkbox';gain.checked=glowGain===5
    gain.onchange=()=>{glowGain=gain.checked?5:1;updateGlow()}
    gainLabel.append(gain,document.createTextNode('辉光强度 ×5'));row.append(gainLabel);panel.append(row)
    const hint=document.createElement('div')
    hint.textContent='实时切换，无需刷新。第 2、3 项视觉等价。×5 放大渐变颜色的透明度（上限 1），保留动画；完全关闭优先。'
    panel.append(hint)
  }
  const download=document.createElement('button');download.textContent='导出记录';download.onclick=exportReport;panel.append(download)
  const exit=document.createElement('button');exit.textContent='退出诊断';exit.onclick=()=>{
    const url=new URL(location.href);for(const key of ['theme-debug','glow-mode','glow-gain','diag-sample','diag-ui','circle-kind'])url.searchParams.delete(key);location.assign(url.href)
  };panel.append(exit)
  const status=document.createElement('div');status.textContent=sampling?'请切换主题；记录最近 12 次切换。':'尺寸采样已关闭。';panel.append(status)
  const note=document.createElement('div');note.textContent='诊断采样影响性能；此页只用于判断色块和边界。';panel.append(note)
  const mount=()=>document.body.append(panel)
  if(document.body)mount();else document.addEventListener('DOMContentLoaded',mount,{once:true})
  return controller
}
