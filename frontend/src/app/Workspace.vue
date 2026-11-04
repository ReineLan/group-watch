<script setup>
import {computed, nextTick, onMounted, onUnmounted, provide, ref, watch} from 'vue'
import SidebarNavigation from './ui/SidebarNavigation.vue'
import ThemeSwitcher from './ui/ThemeSwitcher.vue'
import {OverviewPage} from '../pages/overview/index.js'
import {EventsPage} from '../pages/events/index.js'
import {MaintenancePage} from '../pages/maintenance/index.js'
import {NotificationsPage} from '../pages/notifications/index.js'
import {RulesPage} from '../pages/rules/index.js'
import {EvidenceWorkspace} from '../pages/evidence/index.js'
import {pages, resolvePage, evidencePages, greeting} from './navigation.js'
import AppIcon from '../shared/ui/AppIcon.vue'
import {theme,scenes} from './theme/theme.js'
import {workspacePalette,paletteColors} from './theme/workspacePalette.js'
import {paletteWave} from './theme/paletteWave.js'
import {syncPaletteRegions} from './theme/paletteRegions.js'
import {resolveTheme} from './theme/themes.js'
import {createWorkspace,workspaceKey} from '../entities/monitor/model/workspace.js'
import {createEvidence,evidenceKey} from '../entities/evidence/model/state.js'
import {createSession,sessionKey} from '../shared/api/session.js'
import {time} from '../shared/lib/format.js'
import {afterPaint} from '../shared/lib/afterPaint.js'

const active=ref(resolvePage(location.hash)), menuOpen=ref(false), narrow=ref(false)
const emit=defineEmits(['lock'])
const token=document.querySelector('meta[name="csrf-token"]').content
const session=createSession(token),workspace=createWorkspace(session),evidence=createEvidence(workspace.api,workspace.notify,computed(()=>workspace.status.value?.group_names||{}))
provide(sessionKey,session);provide(workspaceKey,workspace);provide(evidenceKey,evidence)
const status=computed(()=>workspace.status.value||{connected:false,open_cases:0}),totals=evidence.totals
const paletteHost=ref(null)
let palette
const regionPalettes=new Map(),wave=paletteWave()
let seenScene=0
function paletteRegions(){
  return syncPaletteRegions(paletteHost.value,regionPalettes)
}
function updatePalette(value){
  if(!palette)return
  const newest=value.at(-1),regions=paletteRegions(),colors=paletteColors()
  if(newest?.ring){
    if(newest.key<=seenScene)return
    seenScene=newest.key
    wave.run(regions,newest,colors,{immediate:matchMedia('(prefers-reduced-motion: reduce)').matches})
  }else{
    wave.cancel();palette.sync(colors)
    wave.run(regions,null,colors,{immediate:true})
  }
}
watch(scenes,updatePalette,{flush:'post'})
watch(active,async()=>{await nextTick();paletteRegions()},{flush:'post'})
const {error,updated,refreshing,toast}=workspace
const refreshTurns=ref(false)
function refreshFromButton(){refreshTurns.value=true;void workspace.refresh()}
function resetRefreshMotion(){refreshTurns.value=false}
const overview=ref(),events=ref(),maintenance=ref(),archive=ref()
async function refreshPage(){
  if(active.value==='overview')await overview.value?.refresh()
  else if(active.value==='events')await events.value?.refresh()
  else if(active.value==='maintenance')await Promise.all([maintenance.value?.refresh(),archive.value?.refresh()])
  else if(evidencePages.includes(active.value))await archive.value?.refresh()
}
async function lock(){try{await workspace.api('/api/auth/logout',{});emit('lock')}catch(e){error.value=e.message}}
const evidenceVisible=computed(()=>evidencePages.includes(active.value))
const title=computed(()=>pages.find(page=>page.key===active.value).label)
const clock=ref(new Date())
const hello=computed(()=>greeting(+new Intl.DateTimeFormat('en-US',{timeZone:'Asia/Shanghai',hour:'numeric',hourCycle:'h23'}).format(clock.value)))
const today=computed(()=>new Intl.DateTimeFormat('zh-CN',{timeZone:'Asia/Shanghai',month:'long',day:'numeric',weekday:'short'}).format(clock.value))
let media,ticker
function closeMenu(focus=true) {
  const opened=menuOpen.value;menuOpen.value=false
  document.body.classList.remove('navigation-open')
  if(opened&&focus) document.getElementById('open-navigation').focus()
}
async function openMenu() {
  menuOpen.value=true;document.body.classList.add('navigation-open')
  await nextTick();document.getElementById('close-navigation').focus()
}
function resize(){narrow.value=media.matches;closeMenu(false)}
function route(){
  active.value=resolvePage(location.hash)
  if(location.hash==='#archive')history.replaceState(null,'','#maintenance')
}
function keyboard(event){
  if(!menuOpen.value)return
  if(event.key==='Escape'){event.preventDefault();closeMenu()}
  else if(event.key==='Tab'){
    const targets=[...document.querySelectorAll('#workspace-sidebar a,#workspace-sidebar button')].filter(node=>node.getClientRects().length)
    const first=targets[0],last=targets.at(-1)
    if(event.shiftKey&&document.activeElement===first){event.preventDefault();last.focus()}
    else if(!event.shiftKey&&document.activeElement===last){event.preventDefault();first.focus()}
  }
}
watch(active,async()=>{
  const destination=active.value
  evidence.view.value=active.value
  closeMenu(false);document.title=title.value+' · Lan'
  await nextTick();await afterPaint()
  if(active.value!==destination)return
  try{await refreshPage()}catch(e){error.value=e.message}
})
onMounted(async()=>{
  palette=workspacePalette(paletteHost.value)
  updatePalette(scenes.value)
  media=matchMedia('(max-width:800px)');resize();media.addEventListener('change',resize)
  ticker=setInterval(()=>clock.value=new Date(),60000)
  window.addEventListener('hashchange',route);document.addEventListener('keydown',keyboard)
  evidence.view.value=active.value;evidence.start();workspace.start(refreshPage)
  document.title=title.value+' · Lan'
  try{await Promise.all([workspace.loadStatus(),refreshPage()])}catch(e){error.value=e.message}
})
onUnmounted(()=>{
  wave.cancel();palette?.dispose();for(const region of regionPalettes.values())region.dispose();regionPalettes.clear()
  clearInterval(ticker);window.removeEventListener('hashchange',route)
  document.removeEventListener('keydown',keyboard);media?.removeEventListener('change',resize)
  document.body.classList.remove('navigation-open')
})
</script>
<template>
 <div ref="paletteHost" class="workspace-palette ui-palette">
  <div class="workspace">
    <SidebarNavigation :active="active" :pending="status.open_cases" :connected="status.connected" :qq-port="status.qq_port" :activity="status.activity||[]" :inert="narrow&&!menuOpen" @close="closeMenu()"/>
    <button id="navigation-scrim" aria-label="关闭导航" :hidden="!menuOpen" @click="closeMenu()"></button>
    <main>
      <header class="topbar">
        <button id="open-navigation" class="icon-button" aria-label="展开导航" aria-controls="workspace-sidebar" :aria-expanded="menuOpen" @click="openMenu"><AppIcon name="menu"/></button>
        <strong id="breadcrumb" class="sr-only">{{title}}</strong>
        <p class="topbar-greeting"><strong>{{hello}}</strong><span>{{today}}</span></p>
        <div class="topbar-right"><span id="update-time" :class="{syncing:refreshing||!updated}"><i aria-hidden="true"></i>{{updated?'同步于 '+time(updated).split(' ').pop().slice(0,5):'正在同步'}}</span><button class="icon-button" id="refresh" aria-label="刷新工作台" title="刷新工作台" :disabled="refreshing" @click="refreshFromButton"><AppIcon name="refresh" :class="{'refresh-nudge':refreshTurns}" @animationend="resetRefreshMotion"/></button><ThemeSwitcher/><button class="icon-button" aria-label="锁定工作台" title="锁定工作台" @click="lock"><AppIcon name="lock"/></button></div>
      </header>
      <div class="page">
        <div class="error-banner" id="error" role="alert" :hidden="!error">{{error}}</div>
        <section id="view-overview" class="view" :hidden="active!=='overview'"><OverviewPage ref="overview" :active="active==='overview'" :pending="status.open_cases" :totals="totals" :scene="resolveTheme(theme)"/></section>
        <section id="view-events" class="view" :hidden="active!=='events'"><EventsPage ref="events" :active="active==='events'"/></section>
        <section id="view-records" class="view" :hidden="!evidenceVisible"></section>
        <section id="view-maintenance" class="view" :hidden="active!=='maintenance'"><MaintenancePage ref="maintenance" :active="active==='maintenance'"/></section>
        <section id="view-notifications" class="view" :hidden="active!=='notifications'"><NotificationsPage :active="active==='notifications'"/></section>
        <section id="view-rules" class="view" :hidden="active!=='rules'"><RulesPage :active="active==='rules'"/></section>

      </div>
    </main>
  </div>
  <Teleport defer :to="active==='maintenance'?'#maintenance-archive':'#view-records'"><EvidenceWorkspace ref="archive" :view="active" :active="evidenceVisible||active==='maintenance'"/></Teleport>
  <div id="toast" role="status" aria-live="polite" :hidden="!toast">{{toast}}</div>
 </div>
</template>
