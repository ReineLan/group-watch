<script setup>
import BrandGlyph from '../shared/ui/BrandGlyph.vue'
import RepositoryLink from '../shared/ui/RepositoryLink.vue'
import {ref,computed,onMounted,onUnmounted,nextTick,watch} from 'vue'
import Workspace from './Workspace.vue'
import AppIcon from '../shared/ui/AppIcon.vue'
import SceneRenderer from './ui/background/SceneRenderer.vue'
import ThemeSwitcher from './ui/ThemeSwitcher.vue'
import EntryIntro from './ui/EntryIntro.vue'
import SceneThemeLine from './ui/SceneThemeLine.js'
import {workspacePalette} from './theme/workspacePalette.js'
import {theme} from './theme/theme.js'
import {resolveTheme} from './theme/themes.js'
const currentTheme=computed(()=>resolveTheme(theme.value))
// Start with a native password field so saved credentials are recognized.
const ready=ref(false),authenticated=ref(false),password=ref(''),busy=ref(false),error=ref(''),field=ref(),plainInput=ref(false)
const intro=ref(null),introRect=ref(null),brand=ref(null),brandRect=ref(null),themeLine=ref(null),themeLineRect=ref(null)
const fieldComposing=ref(false)
const card=ref(null)
let cardPalette
watch(card,node=>{cardPalette?.dispose();cardPalette=node?workspacePalette(node):null},{flush:'post'})
watch(theme,()=>cardPalette?.sync(),{flush:'post'})
watch(plainInput,()=>{fieldComposing.value=false})
let introObserver
function measureIntro(){
 const rect=intro.value?.getBoundingClientRect()
 introRect.value=rect?{left:rect.left,top:rect.top,width:rect.width,height:rect.height}:null
 const logo=brand.value?.getBoundingClientRect()
 brandRect.value=logo?{left:logo.left,top:logo.top,width:logo.width,height:logo.height}:null
 const line=themeLine.value?.getBoundingClientRect()
 themeLineRect.value=line?{left:line.left,top:line.top,width:line.width,height:line.height}:null
}
watch([intro,brand,themeLine],nodes=>{
 introObserver?.disconnect()
 introObserver=new ResizeObserver(measureIntro)
 for(const node of nodes)if(node)introObserver.observe(node)
 measureIntro()
},{flush:'post'})
async function check(){try{const response=await fetch('/api/auth/session',{signal:AbortSignal.timeout(10000)});if(!response.ok)throw new Error();authenticated.value=(await response.json()).authenticated}catch{error.value='暂时无法连接工作台，请重试。'}finally{ready.value=true}}
async function login(){
 if(busy.value)return
 password.value=field.value?.value||password.value
 if(!password.value)return
 busy.value=true;error.value='';await nextTick()
 try{const response=await fetch('/api/auth/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({token:password.value}),signal:AbortSignal.timeout(15000)});const data=await response.json();if(!response.ok)throw new Error(data.error||'暂时无法进入，请重试。');authenticated.value=true}
 catch(e){error.value=e.name==='TimeoutError'?'连接超时，请重试。':e.message;await nextTick();field.value?.focus()}
 finally{busy.value=false}
}
function lock(){authenticated.value=false;password.value='';error.value='';document.title='进入工作台 · Lan'}
onMounted(()=>{check();window.addEventListener('workspace-locked',lock);window.addEventListener('resize',measureIntro);window.addEventListener('scroll',measureIntro,{passive:true})})
onUnmounted(()=>{cardPalette?.dispose();introObserver?.disconnect();window.removeEventListener('workspace-locked',lock);window.removeEventListener('resize',measureIntro);window.removeEventListener('scroll',measureIntro)})
</script>
<template>
 <SceneRenderer v-slot="{theme:sceneTheme}" :login="!ready||!authenticated" :intro-rect="introRect" :brand-rect="brandRect" :theme-line-rect="themeLineRect">
  <div v-if="!ready||!authenticated" class="entry-brand scene-brand-copy" aria-hidden="true"><span class="entry-logo"><BrandGlyph/></span><span class="entry-brand-text"><span class="brand-name">Lan</span><small>群管理工作台<RepositoryLink tabindex="-1"/></small></span></div>
  <section v-if="!ready||!authenticated" class="entry-intro scene-intro-copy"><EntryIntro/></section>
  <SceneThemeLine v-if="!ready||!authenticated" :theme-id="sceneTheme"/>
 </SceneRenderer>
 <Workspace v-if="ready&&authenticated" @lock="lock"/>
 <main v-else class="entry-gate">
  <div ref="brand" class="entry-brand"><span class="entry-logo" aria-hidden="true"><BrandGlyph/></span><span class="entry-brand-text"><span class="brand-name">Lan</span><small>群管理工作台<RepositoryLink/></small></span></div>
  <div class="entry-layout">
   <section ref="intro" class="entry-intro"><EntryIntro/></section>
   <section ref="card" class="entry-card ui-palette" aria-labelledby="entry-heading"><span class="entry-card-mark" aria-hidden="true">↗</span><span class="entry-overline">WELCOME BACK</span><h2 id="entry-heading">进入工作台</h2>
    <form id="workspace-login" action="/api/auth/login" method="post" autocomplete="on" @submit.prevent="login"><div class="entry-password"><input ref="field" :class="{'is-composing':fieldComposing}" @compositionstart="fieldComposing=true" @compositionend="fieldComposing=false" id="workspace-password" name="password" v-model="password" :type="plainInput&&!busy?'text':'password'" aria-label="访问密码" autocomplete="current-password" spellcheck="false" autocapitalize="off" maxlength="512" placeholder="请输入访问密码" :readonly="busy" :aria-invalid="!!error" :aria-describedby="error?'entry-error':undefined" required><button type="button" :aria-label="plainInput?'隐藏密码':'显示密码并允许中文输入'" :title="plainInput?'隐藏密码':'显示密码并允许中文输入'" :aria-pressed="plainInput" :disabled="busy" @click="plainInput=!plainInput"><AppIcon :name="plainInput?'eye-off':'eye'"/></button></div><p v-if="error" id="entry-error" class="entry-error" role="alert">{{error}}</p><button class="entry-submit" type="submit" :disabled="busy||!ready"><span>{{!ready?'正在连接…':busy?'正在进入…':'进入工作台'}}</span><span aria-hidden="true">→</span></button></form>

   </section>
  </div>
  <footer class="entry-footer"><p ref="themeLine" class="entry-theme-line"><b>{{currentTheme.name}}</b><span>{{currentTheme.line}}</span></p><ThemeSwitcher variant="strip"/></footer>
 </main>
</template>
<style>
.entry-gate{position:relative;z-index:1;min-height:100svh;display:flex;flex-direction:column;padding:44px clamp(24px,5.5vw,88px) 26px;box-sizing:border-box;color:var(--ink)}.entry-brand{display:flex;align-items:center;gap:14.4px;font:600 26px/1 var(--font-num);letter-spacing:.01em}.brand-name{display:block;width:max-content;transform:scaleX(1.12);transform-origin:left center}.entry-brand-text{display:flex;flex-direction:column;gap:7.2px}.entry-brand small{position:relative;display:block;width:max-content;margin:0;font:500 12.6px/1 var(--font-ui);letter-spacing:.2em;color:var(--subtle)}.entry-logo{display:grid;place-items:center;flex:none;width:48px;height:48px;box-sizing:border-box;border:1px solid var(--accent);border-radius:12px;background:transparent;color:var(--ink);--brand-dot:var(--accent);font:500 32px/1 var(--font-num)}.entry-layout{width:min(1040px,100%);margin:auto;display:grid;grid-template-columns:minmax(0,1fr) minmax(300px,380px);align-items:center;gap:clamp(24px,4vw,88px);padding:60px 0}.entry-overline{font-size:10px;letter-spacing:2.5px;color:var(--muted)}.entry-intro h1{font-size:clamp(33px,4vw,52px);font-weight:500;line-height:1.55;letter-spacing:-1.5px;margin:27px 0 21px}.entry-intro{position:relative;isolation:isolate}.entry-intro h1 span{color:var(--highlight)}.entry-intro p{font-size:14px;line-height:2;color:var(--muted)}.entry-line{display:flex;gap:18px;align-items:center;margin-top:48px;font-size:9px;letter-spacing:2px;color:var(--muted)}.entry-line i{width:65px;height:1px;background:color-mix(in srgb,var(--accent-2) 44%,transparent)}.entry-card{position:relative;min-width:0;padding:42px clamp(24px,3vw,36px) 28px;border:1px solid color-mix(in srgb,var(--glass-edge) 85%,transparent);border-radius:24px;background:linear-gradient(140deg,color-mix(in srgb,var(--surface) 92%,transparent),color-mix(in srgb,var(--surface) 79%,transparent));backdrop-filter:blur(18px);-webkit-backdrop-filter:blur(18px);box-shadow:0 22px 85px color-mix(in srgb,var(--shadow) 19%,transparent),inset 0 1px 0 var(--glass-edge);animation:entry-arrive .7s cubic-bezier(.2,.7,.2,1) both}.entry-card-mark{position:absolute;right:27px;top:22px;color:var(--faint);font-size:27px}.entry-card h2{font-size:29px;letter-spacing:-.5px;margin:15px 0 10px}.entry-card>p{color:var(--subtle);font-size:12px;margin:0 0 33px}.entry-card form{margin-top:28px}.entry-card label{display:block;font-size:12px;margin-bottom:10px;color:var(--ink-2)}.entry-password{position:relative;display:flex;border:1px solid var(--line-2);background:var(--surface);border-radius:11px;transition:box-shadow .2s,border-color .2s}.entry-password:focus-within{border-color:var(--accent);box-shadow:0 0 0 4px color-mix(in srgb,var(--accent-2) 10%,transparent)}.entry-password input{width:100%;min-width:0;background:transparent;border:0;outline:0;padding:15px;font:inherit;font-size:14px;color:var(--ink)}.entry-password button{border:0;background:transparent;color:var(--subtle);padding:0 14px;font-size:11px;cursor:pointer}.entry-submit{display:flex;justify-content:space-between;align-items:center;width:100%;border:0;border-radius:11px;background:var(--accent);color:var(--on-accent);font:inherit;font-size:13px;padding:15px 18px;margin-top:24px;cursor:pointer;box-shadow:0 5px 15px color-mix(in srgb,var(--shadow) 13%,transparent);transition:transform .2s,background .2s,box-shadow .2s}.entry-submit:hover:enabled{transform:translateY(-2px);background:var(--accent-strong);box-shadow:0 8px 20px color-mix(in srgb,var(--shadow) 21%,transparent)}.entry-submit:disabled{opacity:.55;cursor:default}.entry-submit span:last-child{font-size:20px}.entry-error{font-size:12px;line-height:1.7;color:var(--danger);margin:9px 0 -10px}.entry-private{margin-top:30px;padding-top:21px;border-top:1px solid color-mix(in srgb,var(--line-2) 49%,transparent);font-size:10px;color:var(--faint);display:flex;gap:8px;align-items:center}.entry-footer{display:flex;justify-content:space-between;align-items:center;gap:18px;flex-wrap:wrap}.entry-theme-line{position:relative;isolation:isolate;display:flex;gap:14px;align-items:baseline;margin:0;font-size:12px;color:var(--muted);letter-spacing:1px}.entry-theme-line::before{content:"";position:absolute;inset:-42px -68px;z-index:-1;pointer-events:none;background:var(--veil)}.entry-theme-line b{font-size:13px;font-weight:600;letter-spacing:3px;color:var(--ink)}@keyframes entry-arrive{from{opacity:0;transform:translateY(18px)}to{opacity:1;transform:translateY(0)}}@media(max-width:700px){.entry-gate{padding:26px 24px 20px}.entry-layout{grid-template-columns:minmax(0,1fr);gap:48px;max-width:420px;padding:38px 0}.entry-intro h1{font-size:30px;margin:16px 0 9px;line-height:1.4}.entry-intro p{font-size:12px;margin:0}.entry-line{display:flex;margin-top:22px}.entry-intro .entry-overline{display:none}.entry-card{padding:30px 25px 23px}.entry-card>p{margin-bottom:24px}.entry-theme-line span{display:none}}@media(prefers-reduced-motion:reduce){.entry-card{animation:none}.entry-submit{transition:none}}
@media(max-width:700px){
 .entry-gate{padding:clamp(14px,3svh,26px) 24px 16px;overflow-x:clip}
 .entry-layout{gap:clamp(12px,3svh,26px);padding:clamp(12px,3svh,24px) 0;max-width:420px}
 .entry-intro h1{font-size:clamp(26px,4svh,30px);line-height:1.35;margin:10px 0 8px}
 .entry-intro .entry-line{margin-top:12px}
 .entry-card{padding:24px 20px 20px}.entry-card h2{font-size:26px;margin-top:12px}.entry-card form{margin-top:22px}
 .entry-password input{font-size:16px;padding:13px}.entry-submit{margin-top:16px;padding:13px 16px}
 .entry-footer{flex-wrap:nowrap;gap:8px}.entry-theme-line{flex-shrink:0}
}
:root[data-scene-static] .entry-card{background:color-mix(in srgb,var(--surface) 94%,transparent)}
</style>

<style>
/* Cover browser autofill paint with the same animated surface as the field. */
.entry-password{overflow:hidden;background:var(--surface)}
.entry-password input{appearance:none;border-radius:inherit;background:transparent;color:var(--ink);-webkit-text-fill-color:var(--ink);caret-color:var(--ink);color-scheme:only light}
.entry-password input:autofill,.entry-password input:-webkit-autofill{box-shadow:inset 0 0 0 1000px var(--surface);-webkit-text-fill-color:var(--ink);caret-color:var(--ink)}
</style>

<style scoped>
.entry-brand small :deep(.repository-link){position:absolute;left:calc(100% + 4px);top:50%;transform:translateY(-50%)}
</style>
