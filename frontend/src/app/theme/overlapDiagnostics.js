import {nextTick} from 'vue'
import {themes} from './themes.js'
import {installPerformanceDiagnostics} from './performanceDiagnostics.js'

export function overlapSettings(search){
  const p=new URLSearchParams(search)
  if(!['overlap','queued','p3-ui','mobile'].includes(p.get('theme-debug')))return null
  const mobile=p.get('theme-debug')==='mobile'
  const queued=mobile||['queued','p3-ui'].includes(p.get('theme-debug'))
  const interval=mobile&&['260','300','400'].includes(p.get('queue-ms'))?Number(p.get('queue-ms')):260
  const capacity=mobile&&['4','6'].includes(p.get('queue-size'))?Number(p.get('queue-size')):6
  const implementation=['clip','mask','normal','e3'].includes(p.get('implementation'))?p.get('implementation'):'e3'
  const test=!queued&&['a','b','c'].includes(p.get('overlap-test'))?p.get('overlap-test'):'a'
  return {mobile,interval,capacity,appearanceScope:mobile&&p.get('appearance-scope')==='card'?'card':'viewport',glass:!mobile||p.get('card-glass')!=='off',edge:!mobile||p.get('card-edge')!=='off',effects:!mobile||p.get('scene-effects')!=='paused',backdrop:!mobile||p.get('card-blur')!=='off',test,implementation,sequence:p.get('overlap-sequence')==='pair'?'pair':'all',queued,uiAppearance:p.get('theme-debug')==='p3-ui'||(mobile&&p.get('appearance')!=='off'),maxActive:test==='b'?3:0,mask:implementation==='mask',e3:implementation==='e3',blend:test==='c'||implementation==='normal'?'normal':'screen',styles:mobile?p.get('audit-style')==='1':p.get('audit-style')!=='0'}
}

export function opacityGrouping(filter){return /^opacity\(\s*(?:1(?:\.0*)?|100%|)\s*\)$/.test(filter)}

// Tests an observed CSS state, independently of the controller's declared state.
export function inspectClip({radius,targetRadius,point,clipPath,maskImage,mask}){
  const range=Number.isFinite(radius)&&Number.isFinite(targetRadius)&&radius>=-.5&&radius<=targetRadius+1
  if(mask)return {valid:range&&maskImage!=='none'&&maskImage.includes('radial-gradient('),range}
  const numbers=clipPath.match(/^circle\(([-+\d.e]+)px at ([-+\d.e]+)px ([-+\d.e]+)px\)$/i)
  const circle=numbers?.slice(1).map(Number)
  return {valid:!!(range&&circle&&point&&Math.abs(circle[0]-radius)<=1&&Math.abs(circle[1]-point.x)<=1&&Math.abs(circle[2]-point.y)<=1),range}
}

export function installOverlapDiagnostics({selectTheme,resetTheme,prepareImages,pause,resume}){
  const settings=overlapSettings(location.search),root=document.documentElement
  root.dataset.themeDebug='overlap';root.dataset.overlapImplementation=settings.implementation;root.dataset.overlapBlend=settings.blend
  if(settings.mobile){root.dataset.mobileDiagnostic='true';root.dataset.appearanceScope=settings.appearanceScope}
  const style=document.createElement('style')
  style.textContent=`
    [data-theme-debug=overlap] .scene-composite-group{filter:none!important}
    [data-theme-debug=overlap][data-overlap-implementation=e3] .theme-reveal-layer[data-scene-role=ring]>.scene-composite-group{filter:opacity(1)!important}
    [data-theme-debug=overlap] .scene-glow{mix-blend-mode:var(--overlap-blend)!important}
    #theme-overlap-diagnostics{position:fixed;left:8px;bottom:8px;z-index:10000;max-width:min(470px,94vw);max-height:60vh;overflow:auto;padding:10px;border:1px solid var(--line-3);border-radius:8px;background:var(--surface);color:var(--ink);font:12px/1.6 system-ui}
    #theme-overlap-diagnostics :is(select,button,input){font:inherit;color:var(--ink);background:var(--surface-2);border:1px solid var(--line-3);margin:3px;padding:4px}
  `
  if(settings.mobile){
    style.textContent+=`
      #theme-overlap-diagnostics{max-height:34dvh;bottom:env(safe-area-inset-bottom,8px);max-width:calc(100vw - 16px)}
      #theme-overlap-diagnostics :is(select,button,input){min-height:36px;font-size:14px}
    `
    if(!settings.effects)style.textContent+='[data-mobile-diagnostic] .scene-composite-group,[data-mobile-diagnostic] .scene-composite-group *,[data-mobile-diagnostic] .scene-composite-group::before,[data-mobile-diagnostic] .scene-composite-group::after,[data-mobile-diagnostic] .scene-composite-group *::before,[data-mobile-diagnostic] .scene-composite-group *::after{animation-play-state:paused!important}'
    if(settings.appearanceScope==='card')style.textContent+='html[data-mobile-diagnostic][data-appearance-scope=card] .entry-card.p3-card,html[data-mobile-diagnostic][data-appearance-scope=card] .entry-card-visual{backdrop-filter:none!important;-webkit-backdrop-filter:none!important}'
    if(!settings.glass)style.textContent+='[data-mobile-diagnostic] .entry-appearance-glass{display:none!important}'
    if(!settings.edge)style.textContent+='[data-mobile-diagnostic] .entry-card-visual::after{display:none!important}'
    if(!settings.backdrop)style.textContent+='html[data-mobile-diagnostic] .entry-card,html[data-mobile-diagnostic] .entry-card *,html[data-mobile-diagnostic] .entry-card::before,html[data-mobile-diagnostic] .entry-card::after{backdrop-filter:none!important;-webkit-backdrop-filter:none!important}'
  }
  root.style.setProperty('--overlap-blend',settings.blend);document.head.append(style)
  const started=performance.now(),events=[],snapshots=[],markers=[],lifetimes=new Map()
  let model,clickId=0,eventId=0,round=0,poll=0,pendingSnapshot=false,status,queueStatus,dropped=0,recording=true,peak=0
  const pendingClicks=[]
  const now=()=>performance.now()-started
  function push(kind,detail={}){
    if(!recording)return
    events.push({eventId:++eventId,t:now(),round,kind,...detail})
    if(events.length>=20000){recording=false;clearTimeout(poll);if(status)status.textContent='已达20000事件上限，请导出后刷新。记录未静默截断。'}
  }
  const nodes=()=>[...document.querySelectorAll('.scene-transition-host > .theme-reveal-layer')]
  function read(node){
    const key=Number(node.dataset.sceneKey),description=model&&[model.base,...model.rings].find(scene=>scene.key===key)
    const result={key,theme:node.dataset.theme,role:node.dataset.sceneRole,controller:description||null}
    if(!settings.styles)return result
    const s=getComputedStyle(node),group=node.querySelector('.scene-composite-group'),g=group&&getComputedStyle(group),glow=node.querySelector('.scene-glow')
    const property=node.dataset.radiusProperty||'--theme-reveal-radius'
    const source=node.dataset.radiusProperty?node.parentElement:node
    const rect=node.getBoundingClientRect(),radius=parseFloat(s.getPropertyValue(property))
    Object.assign(result,{radius:Number.isFinite(radius)?radius:null,targetRadius:description?.radius,point:description?.point,mask:description?.mask,
      rect:{x:rect.x,y:rect.y,width:rect.width,height:rect.height},clipPath:s.clipPath,maskImage:s.maskImage,filter:g?.filter,e3Applied:opacityGrouping(g?.filter||''),blend:glow?getComputedStyle(glow).mixBlendMode:null,
      animation:source.getAnimations().filter(a=>!node.dataset.radiusProperty||a.effect?.getKeyframes().some(frame=>Object.hasOwn(frame,property))).map(a=>({time:a.currentTime,state:a.playState,progress:a.effect?.getComputedTiming?.().progress}))})
    if(result.role==='ring')result.clip=inspectClip(result)
    return result
  }
  function snapshot(label,relatedClickIds=[clickId]){
    if(!recording)return
    const children=nodes(),actual=children.map(read),rings=actual.filter(n=>n.role==='ring'),violations=[]
    if(children.length){
      if(actual.filter(n=>n.role==='base').length!==1)violations.push('base-count')
      const expected=model?[model.base,...model.rings].map(n=>n.key):[]
      if(JSON.stringify(actual.map(n=>n.key))!==JSON.stringify(expected))violations.push('DOM/controller-order')
      for(const ring of rings){
        if(settings.styles&&!ring.clip.valid)violations.push(`invalid-clip:${ring.key}`)
        if(settings.styles&&settings.e3&&!ring.e3Applied)violations.push(`missing-e3:${ring.key}`)
      }
    }
    const appearanceTargets=settings.uiAppearance?[...document.querySelectorAll('.ui-appearance-layer')].map(node=>{
      const value=read(node)
      if(settings.styles&&value.role==='ring'){
        value.point={x:value.controller.point.x-value.rect.x,y:value.controller.point.y-value.rect.y}
        value.clip=inspectClip({...value,mask:true})
        const background=actual.find(n=>n.key===value.key)
        const time=value.animation[0]?.time,backgroundTime=background?.animation[0]?.time
        value.radiusDifference=Number.isFinite(value.radius)&&Number.isFinite(background?.radius)?value.radius-background.radius:null
        value.clockDifferenceMs=typeof time==='number'&&typeof backgroundTime==='number'?time-backgroundTime:null
      }
      return value
    }):undefined
    const sample={t:now(),round,label,relatedClickIds,rootTheme:root.dataset.theme,activeRevealScenes:rings.length,baseKey:actual.find(n=>n.role==='base')?.key,appearanceTargets,
      controllerBase:model?.base,controllerRings:model?.rings,actual,violations}
    snapshots.push(sample)
    if(snapshots.length>=10000){recording=false;clearTimeout(poll)}
    if(status&&recording)status.textContent=`活动圆 ${rings.length}；本页峰值 ${peak}；点击 ${clickId}；标记 ${markers.length}；本次状态检查 ${violations.length?violations.join(', '):'无违规'}。`
    return sample
  }
  function scheduleSnapshot(){
    if(pendingSnapshot||!recording)return
    pendingSnapshot=true
    // A promotion event precedes publish(). Let the controller finish its
    // synchronous transaction before waiting for Vue; otherwise we'd sample
    // the new model against DOM that has not had a chance to update.
    Promise.resolve().then(()=>nextTick()).then(()=>{pendingSnapshot=false;snapshot('after-vue-flush',pendingClicks.splice(0))})
  }
  function schedulePoll(){
    if(poll||!recording||(settings.mobile&&!settings.styles))return
    poll=setTimeout(()=>{poll=0;snapshot('100ms-poll');if(model?.rings.length)schedulePoll()},100)
  }
  const api={
    queueOptions:settings.queued?{interval:settings.interval,capacity:settings.capacity}:null,
    queueEvent:event=>{
      push(event.kind,event)
      if(event.kind==='queue-dropped')dropped++
      if(queueStatus)queueStatus.textContent=`待执行 ${event.pending.length}/${settings.capacity}；已丢弃最早待执行项 ${dropped} 次。`
      if(event.kind==='queue-started')performance.mark?.(`theme-queue:${event.request.diagnostic.clickId}:started`)
    },
    revealOptions:()=>({mask:settings.mask,maxActive:settings.maxActive,clickId}),
    selectionRequested(theme,point){
      clickId++;push('click-request',{clickId,theme,point,sameAsCommitted:root.dataset.theme===theme,base:model?.base,rings:model?.rings})
      pendingClicks.push(clickId)
      scheduleSnapshot();schedulePoll()
    },
    sceneLifecycle(key,kind){
      const life=lifetimes.get(key)||{key}
      life[kind==='mount'?'mountedAt':'destroyedAt']=now();lifetimes.set(key,life)
      push(kind,{key});scheduleSnapshot()
    },
    sceneEvent(event){
      model={base:event.base,rings:event.rings};peak=Math.max(peak,event.rings.length)
      // Capture coverage before cancel() removes the animation or clears clipping.
      if(event.kind==='will-promote'){
        const node=nodes().find(n=>Number(n.dataset.sceneKey)===event.key),actual=node&&read(node)
        const coverage=settings.styles&&actual&&Number.isFinite(actual.radius)&&Number.isFinite(actual.targetRadius)?actual.radius>=actual.targetRadius-1:null
        push(event.kind,{...event,actual,fullyCovered:coverage})
      }else push(event.kind,event)
      scheduleSnapshot();if(event.rings.length)schedulePoll()
    },
  }
  function mark(){
    const state=snapshot('user-anomaly-marker')
    const marker={t:now(),round,clickId,activeRevealScenes:state?.activeRevealScenes,baseKey:state?.baseKey,snapshotIndex:snapshots.length-1}
    markers.push(marker);push('user-anomaly-marker',marker)
    if(status)status.textContent=`已标记异常：标记时 ${marker.activeRevealScenes} 个活动圆；该数量不等于异常首帧的自动判定。`
  }
  function download(){
    snapshot('export')
    const data={schema:'theme-overlap-audit-v1',architecture:'vue-scenes-e3-v1',appearanceArchitecture:settings.uiAppearance?'p3-card-full-v1':null,settings,queuePolicy:api.queueOptions,startedAt:new Date(performance.timeOrigin+started).toISOString(),
      environment:{staticScene:document.documentElement.hasAttribute?.('data-scene-static')??null,hidden:document.hidden,visualViewport:window.visualViewport?{width:window.visualViewport.width,height:window.visualViewport.height,scale:window.visualViewport.scale}:null},
      userAgent:navigator.userAgent,viewport:{width:innerWidth,height:innerHeight,dpr:devicePixelRatio},scripts:[...document.scripts].map(s=>s.src).filter(Boolean),recording,peak,
      lifetimes:[...lifetimes.values()],events,snapshots,markers,
      note:'结构/样式诊断，非性能验收；强制读样式会扰动合成时序。标记是用户点击时刻，不是异常首帧。无像素检测或GPU测量。clip/mask/normal/e3均为当前Vue架构的合成条件，不是历史clone架构。Base提升前fullyCovered=null表示未测，false需结合完成原因/中断分析。'}
    const url=URL.createObjectURL(new Blob([JSON.stringify(data,null,2)],{type:'application/json'}))
    const a=document.createElement('a');a.href=url;a.download=`theme-${settings.mobile?'mobile':settings.queued?'queued':'overlap'}-${settings.test}-${settings.implementation}-${Date.now()}.json`;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000)
  }
  const panel=document.createElement('details');panel.id='theme-overlap-diagnostics';panel.open=true
  const title=document.createElement('summary');title.textContent=settings.mobile?'手机闪烁诊断 · 点击折叠面板':settings.queued?`队列实验 · ${settings.interval}ms / 待执行${settings.capacity}项`:'连续点击诊断 · A/B/C';panel.append(title)
  function text(content){const node=document.createElement('div');node.textContent=content;panel.append(node)}
  function menu(label,choices,value,param){
    const row=document.createElement('label');row.textContent=label
    const input=document.createElement('select');input.setAttribute('aria-label',label)
    for(const [key,name] of Object.entries(choices)){const option=document.createElement('option');option.value=key;option.textContent=name;input.append(option)}
    input.value=value;input.onchange=()=>{const url=new URL(location.href);url.searchParams.set(param,input.value);location.assign(url.href)};row.append(input);panel.append(row)
  }
  if(!settings.queued)menu('实验',{a:'A · 不限制活动圆',b:'B · 已有3圆时忽略新选择',c:'C · 不限数量，辉光normal'},settings.test,'overlap-test')
  else text(`首次立即启动；后续实际启动至少间隔${settings.interval}ms；最多${settings.capacity}项待执行，满时丢弃队首。没有活动圆容量限制。`)
  if(settings.uiAppearance)text('P3.2：卡片玻璃背景、边框、阴影、文字、输入框和按钮外观共用Reveal。色层互斥避免透明叠色，真实表单只有一份；原生光标/选区/输入法仍由真实输入框绘制。')
  if(settings.queued){queueStatus=document.createElement('div');queueStatus.textContent=`待执行 0/${settings.capacity}；已丢弃 0 次。`;panel.append(queueStatus)}
  menu('合成条件（当前Vue）',{e3:'E3 · clip + 内部filter + screen',clip:'clip + screen（无E3）',mask:'mask + screen（无E3）',normal:'clip + normal（无E3）'},settings.implementation,'implementation')
  if(settings.mobile){
    text('先用默认条件复现，再每次只改一项；切换选项会刷新，先导出记录。登录状态下请先锁定工作台；本页只做样式测试，无需输入密码。')
    menu('启动间隔',{260:'260ms（正式）',300:'300ms',400:'400ms'},String(settings.interval),'queue-ms')
    menu('等待队列长度',{6:'6项（正式）',4:'4项'},String(settings.capacity),'queue-size')
    menu('卡片外观',{on:'P3开启（正式）',off:'关闭P3'},settings.uiAppearance?'on':'off','appearance')
    menu('P3绘制范围',{viewport:'全屏（原方案）',card:'卡片附近（同时移除父卡片backdrop）'},settings.appearanceScope,'appearance-scope')
    menu('P3玻璃层',{on:'保留',off:'关闭'},settings.glass?'on':'off','card-glass')
    menu('P3装饰边线',{on:'保留',off:'关闭'},settings.edge?'on':'off','card-edge')
    menu('场景动效',{running:'运行（正式）',paused:'暂停花瓣/光点/辉光'},settings.effects?'running':'paused','scene-effects')
    menu('卡片模糊',{on:'开启（正式）',off:'关闭backdrop'},settings.backdrop?'on':'off','card-blur')
    menu('状态采样',{0:'轻量记录（默认）',1:'读取样式 + 100ms采样'},settings.styles?'1':'0','audit-style')
    const prepare=document.createElement('button');prepare.textContent='预解码四主题图片';prepare.onclick=async()=>{prepare.disabled=true;const before=performance.now();push('image-prepare-start');try{await prepareImages(themes.map(t=>t.id));push('image-prepare-done',{durationMs:performance.now()-before});prepare.textContent='图片已准备（本页）'}catch(error){push('image-prepare-error',{message:String(error)});prepare.textContent='准备失败，可重试';prepare.disabled=false}};panel.append(prepare)
    text(`视口 ${innerWidth}×${innerHeight}，DPR ${devicePixelRatio}；静态场景 ${root.hasAttribute('data-scene-static')?'是':'否'}。轻量记录不自动判定闪烁；请配合录屏及异常标记。`)
  }
  menu('切换序列',{all:'四主题循环',pair:`仅前两主题交替：${themes[0].name} ↔ ${themes[1].name}`},settings.sequence,'overlap-sequence')
  text(`实际辉光：${settings.blend}；E3：${settings.e3?'启用':'关闭'}；${settings.maxActive?'最多3个活动圆，超出忽略，不改变主题、不提前完成圆':'自然完成所有圆'}。`)
  text(`先手动快速选择不同主题3/4/5/6次；或用下面按钮做固定圆心对照。按钮会先重置${themes[0].name}，${settings.sequence==='pair'?`再交替切换${themes[1].name}→${themes[0].name}`:'再从浮梦开始循环四主题'}。`)
  const gap=document.createElement('input');gap.type='number';gap.min='0';gap.max='500';gap.value='50';gap.setAttribute('aria-label','点击间隔ms')
  const gapLabel=document.createElement('label');gapLabel.append(document.createTextNode('目标点击间隔ms：'),gap);panel.append(gapLabel)
  let running=false
  const buttons=[]
  for(const count of settings.mobile?[1,6,12]:settings.queued?[3,4,5,6,12,20]:[3,4,5,6]){
    const button=document.createElement('button');button.textContent=`快速 ${count} 次`;buttons.push(button);panel.append(button)
    button.onclick=async()=>{
      if(running)return
      running=true;buttons.forEach(b=>b.disabled=true);round++
      const interval=Math.max(0,Math.min(500,Number(gap.value)||0)),choices=settings.sequence==='pair'?[themes[1].id,themes[0].id]:['feihua','shuizhong','mengxue','chunxi'],pending=[]
      push('round-start',{count,interval,sequence:settings.sequence,initialTheme:themes[0].id,choices:Array.from({length:count},(_,i)=>choices[i%choices.length])})
      try{
        await resetTheme(themes[0].id);await new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)))
        for(let i=0;i<count;i++){
          if(i)await new Promise(resolve=>setTimeout(resolve,interval))
          pending.push(selectTheme(choices[i%choices.length],{x:Math.round(innerWidth*.89),y:Math.round(innerHeight*.94)}))
        }
        await Promise.all(pending);await nextTick();snapshot('round-end');push('round-end')
      }catch(error){push('round-error',{message:String(error)})}
      finally{running=false;buttons.forEach(b=>b.disabled=false)}
    }
  }
  for(const [label,action] of [['标记首次异常',mark],['暂停当前圆',()=>{push('manual-pause');pause();scheduleSnapshot()}],['恢复',()=>{push('manual-resume');resume()}],['导出完整记录',download]]){
    const button=document.createElement('button');button.textContent=label;button.onclick=action;panel.append(button)
  }
  if(settings.uiAppearance){
    const button=document.createElement('button');button.textContent='单圆：40%半径暂停';panel.append(button)
    button.onclick=async()=>{
      if(running)return
      await resetTheme('chunxi')
      Promise.resolve(selectTheme('feihua',{x:Math.round(innerWidth*.89),y:Math.round(innerHeight*.94)})).catch(error=>push('round-error',{message:String(error)}))
      await new Promise(resolve=>requestAnimationFrame(resolve))
      pause(.4);push('manual-static',{radiusProgress:.4});scheduleSnapshot()
    }
  }
  status=document.createElement('div');status.textContent='等待主题操作；生命周期记录自动开启。';panel.append(status)
  if(!settings.mobile||settings.styles)text('100ms采样及每次点击后的合并快照用于查状态，不能识别每一帧闪烁。暂停也可能影响合成；请先标记再按需暂停。切换实验前先导出。')
  if(!settings.mobile)text('只记录结构：URL加 audit-style=0（裁剪/filter/覆盖率为未测）；默认读取实际样式。本轮数据不作性能验收。')
  if(settings.queued)installPerformanceDiagnostics(panel,{context:()=>({settings,queuePolicy:api.queueOptions})})
  const mount=()=>document.body.append(panel)
  if(document.body)mount();else document.addEventListener('DOMContentLoaded',mount,{once:true})
  for(const name of ['resize','hashchange','scroll'])window.addEventListener(name,()=>push('interruption',{name}),{passive:true})
  window.addEventListener('resize',()=>push('interruption',{name:'resize',width:innerWidth,height:innerHeight}))
  document.addEventListener('visibilitychange',()=>push('interruption',{name:'visibilitychange',hidden:document.hidden}))
  return api
}
