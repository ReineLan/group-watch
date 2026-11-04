<script setup>
import {computed,onMounted,onUnmounted,ref,watch} from 'vue'
import {resolveTheme,petalField,sparkleField} from '../../theme/themes.js'
import {staticScene} from '../../theme/theme.js'
import {compactSceneQuery} from '../../theme/scenePolicy.js'
import {sceneAssets} from '../../theme/assets.js'
import {mirrorVideo} from '../../theme/videoMirror.js'
import {joinSceneClock} from '../../theme/sceneClock.js'
const props=defineProps({themeId:{type:String,required:true},login:Boolean,introRect:Object,clock:Number,videos:{type:Object,required:true},videoEnabled:{type:Boolean,default:true},lifecycle:Function})
const emit=defineEmits(['ready'])
const still=staticScene,stage=ref(null),canvas=ref(null)
const compact=matchMedia(compactSceneQuery),mobileEffects=ref(compact.matches),lightweight=computed(()=>still.value&&mobileEffects.value)
function syncEffects(){mobileEffects.value=compact.matches}
const current=computed(()=>resolveTheme(props.themeId)),assets=computed(()=>sceneAssets[current.value.id])
const petals=computed(()=>petalField(lightweight.value?9:16).map(p=>({id:p.id,tint:p.tint,style:{'--x':p.left+'vw','--size':p.size+'px','--fall':(lightweight.value?17:p.fall)+'s','--delay':p.delay+'s','--drift':(lightweight.value?Math.round(p.drift*.65):p.drift)+'px','--sway':p.sway+'s','--spin':p.spin+'deg','--alpha':lightweight.value?Math.min(p.opacity,.88):p.opacity,'--blur':lightweight.value?0:p.blur+'px'}})))
const sparkles=computed(()=>sparkleField(lightweight.value?5:16).map(s=>({id:s.id,kind:s.kind,style:{'--x':s.left+'%','--y':s.top+'%','--size':s.size+'px','--dur':s.duration*(current.value.sparkleDurationScale??1)+'s','--delay':s.delay+'s','--rise':s.rise}})))
let motion,lease,stopMirror=()=>{},activeCanvas
function stopVideo(){stopMirror();stopMirror=()=>{};lease?.release();lease=null;activeCanvas=null}
function syncVideo(){
  if(canvas.value===activeCanvas)return
  stopVideo()
  if(!canvas.value)return
  activeCanvas=canvas.value;lease=props.videos.acquire(assets.value.video)
  const shell=stage.value.parentElement,timed=document.documentElement.dataset.themePerformanceRecording==='true'
  const timings=timed?{}:undefined
  if(timed){shell.sceneTimings??={};shell.sceneTimings.videoMirrors=[timings];shell.sceneTimings.activeVideos=1}
  stopMirror=mirrorVideo(lease.video,canvas.value,{timings})
}
watch(canvas,syncVideo,{flush:'post'})

onMounted(()=>{
  compact.addEventListener('change',syncEffects);window.addEventListener('resize',syncEffects,{passive:true});syncEffects()
  const timed=document.documentElement.dataset.themePerformanceRecording==='true',before=timed?performance.now():0
  joinSceneClock(stage.value,props.clock)
  if(timed){const shell=stage.value.parentElement;shell.sceneTimings??={};shell.sceneTimings.animationClockMs=performance.now()-before}
  syncVideo();props.lifecycle?.('mount');emit('ready')
})
onUnmounted(()=>{stopVideo();compact.removeEventListener('change',syncEffects);window.removeEventListener('resize',syncEffects);props.lifecycle?.('destroy')})
</script>
<template>
 <div ref="stage" class="background-scene scene-composite-group scene-theme-tokens" :data-theme="current.id" :class="['effect-'+current.effect,'scene-'+current.id,{'login-light':login,'scene-lightweight':lightweight}]">
    <div class="scene-media scene-layer">
      <div class="scene-art scene-still" :style="{backgroundImage:`url(${assets.image}),url(${assets.thumb})`}"></div>
      <canvas v-if="videoEnabled&&assets.video&&!still" ref="canvas" class="scene-art scene-video"></canvas>
    </div>
    <div class="wash scene-layer"></div>
    <div v-if="!still" class="scene-haze scene-layer"></div>
    <div v-else-if="lightweight&&current.effect==='sunlight'" class="scene-mobile-sunlight scene-layer"></div>
    <div v-if="!still&&current.effect==='sunlight'" class="scene-beam scene-layer">
      <div class="sun-core"></div><div class="sun-shafts"></div><div class="canopy-shadows"></div>
      <div class="sun-sparkles"><i v-for="sparkle in sparkles" :key="sparkle.id" class="sparkle" :class="sparkle.kind" :style="sparkle.style"></i></div>
    </div>
    <div v-else-if="!still" class="scene-petals scene-layer"><i v-for="petal in petals" :key="petal.id" class="petal" :class="'tint-'+petal.tint" :style="petal.style"><b></b></i></div>
    <div v-if="lightweight&&current.effect==='petals'" class="scene-petals scene-mobile-petals scene-layer"><i v-for="petal in petals" :key="petal.id" class="petal" :class="'tint-'+petal.tint" :style="petal.style"><b></b></i></div>
    <div v-if="lightweight" class="scene-mobile-points scene-layer"></div>
    <template v-if="!still"><div class="scene-glow"></div><div class="scene-motes"></div></template>
    <div class="scene-foreground scene-layer"></div>
    <slot v-if="login&&introRect"/>
 </div>
</template>
<style>
.background-scene{position:fixed;inset:0;overflow:hidden;pointer-events:none;contain:strict;background:var(--scene-bg)}
.background-scene .scene-layer{position:absolute;inset:-42px;pointer-events:none}
.scene-media{will-change:transform;opacity:var(--scene-opacity);transform:translate3d(0,0,0)}
.login-light .scene-media{opacity:var(--scene-login-opacity)}
.scene-art{position:absolute;inset:0;width:100%;height:100%;object-fit:cover;object-position:var(--scene-position);filter:var(--scene-filter) blur(var(--scene-blur))}.login-light .scene-art{filter:var(--scene-filter) blur(0px)}
.scene-still{background-size:cover;background-position:var(--scene-position);transform:scale(1.035)}
.scene-video{opacity:0;transition:opacity .2s ease-out}.scene-video.is-ready{opacity:1}
.background-scene .wash{background:var(--wash)}
.login-light .wash{opacity:.72}
.scene-haze{background:radial-gradient(ellipse at 15% 9%,var(--haze-a),transparent 56%),radial-gradient(ellipse at 84% 88%,var(--haze-b),transparent 60%)}
/* Beam travels 56px, petals 46px in either axis. Keep 16px beyond that
   travel; the old 42px overscan exposed 14px/4px strips at pointer extremes. */
.background-scene .scene-beam{inset:-72px}
.background-scene .scene-petals{inset:-64px}
.scene-beam{overflow:hidden;opacity:var(--sun-strength);transform:translate3d(0,0,0)}
.sun-core{position:absolute;left:calc(-22vmax + 30px);top:calc(-30vmax + 30px);width:78vmax;height:78vmax;border-radius:50%;background:radial-gradient(circle,var(--sun-core) 0,color-mix(in srgb,var(--sun-core) 70%,transparent) 9%,color-mix(in srgb,var(--sun-gold) 38%,transparent) 26%,color-mix(in srgb,var(--sun-gold) 10%,transparent) 44%,transparent 64%)}
.sun-sparkles{position:absolute;inset:0}
.sparkle{position:absolute;left:var(--x);top:var(--y);width:var(--size);height:var(--size);margin:calc(var(--size)*-.5);pointer-events:none;will-change:transform,opacity}
.sparkle.glint{background:radial-gradient(circle,var(--sparkle) 0 14%,transparent 46%),linear-gradient(90deg,transparent 47%,var(--sparkle) 50%,transparent 53%),linear-gradient(0deg,transparent 47%,var(--sparkle) 50%,transparent 53%);filter:drop-shadow(0 0 4px var(--sun-gold)) drop-shadow(0 0 10px color-mix(in srgb,var(--sun-gold) 70%,transparent));animation:glint var(--dur) ease-in-out var(--delay) infinite}
@keyframes glint{0%,100%{opacity:0;transform:scale(.2) rotate(0deg)}45%{opacity:1;transform:scale(1) rotate(35deg)}60%{opacity:.85;transform:scale(.8) rotate(48deg)}}
.sparkle.bokeh{border-radius:50%;background:radial-gradient(circle,color-mix(in srgb,var(--sun-core) 55%,transparent) 0,color-mix(in srgb,var(--sun-gold) 26%,transparent) 55%,color-mix(in srgb,var(--sun-gold) 46%,transparent) 66%,transparent 70%);filter:blur(1.5px);animation:bokeh var(--dur) ease-in-out var(--delay) infinite}
@keyframes bokeh{0%,100%{opacity:0;transform:translate3d(0,0,0) scale(.85)}35%,65%{opacity:.75}100%{transform:translate3d(calc(var(--rise)*.25px),calc(var(--rise)*-1px),0) scale(1.08)}}
.scene-chunxi .sparkle.glint{animation-name:chunxi-glint}
@keyframes chunxi-glint{0%,100%{opacity:0;transform:translate3d(-5px,6px,0) scale(.2) rotate(0deg)}45%{opacity:1;transform:translate3d(4px,-6px,0) scale(1) rotate(35deg)}60%{opacity:.85;transform:translate3d(6px,-9px,0) scale(.8) rotate(48deg)}}
.scene-chunxi .sun-shafts{animation-duration:5.5s}
.sun-shafts{position:absolute;inset:-12%;transform-origin:8% 0;background:linear-gradient(118deg,transparent 20%,color-mix(in srgb,var(--sun-ray) 10%,transparent) 24%,var(--sun-ray) 27%,transparent 32%,transparent 39%,var(--sun-ray-soft) 43%,var(--sun-ray) 45%,transparent 51%,transparent 58%,var(--sun-ray-soft) 63%,transparent 68%);mask-image:linear-gradient(#000e,#000a 68%,transparent);animation:canopy-light 10s ease-in-out infinite alternate;will-change:opacity}
.canopy-shadows{position:absolute;inset:-15%;background:radial-gradient(ellipse at 24% 19%,var(--shade) 0 6%,transparent 19%),radial-gradient(ellipse at 68% 49%,var(--shade) 0 5%,transparent 18%),radial-gradient(ellipse at 43% 78%,var(--shade) 0 7%,transparent 23%);filter:blur(16px);opacity:.4;mix-blend-mode:multiply}
@keyframes canopy-light{from{opacity:.45}to{opacity:.9}}
.scene-petals{will-change:transform;transform:translate3d(0,0,0)}
.petal{position:absolute;top:0;left:var(--x);width:var(--size);height:calc(var(--size)*.72);opacity:var(--alpha);filter:blur(var(--blur)) drop-shadow(0 0 calc(var(--size)*.45) var(--petal-glow));animation:petal-fall var(--fall) linear var(--delay) infinite;will-change:transform}
.petal b{display:block;width:100%;height:100%;border-radius:150% 0 150% 0/100% 0 100% 0;background:linear-gradient(135deg,var(--petal-a),var(--petal-b) 62%,var(--petal-c));box-shadow:inset 0 0 0 .5px #fff6;animation:petal-sway var(--sway) ease-in-out var(--delay) infinite alternate;transform:rotate(var(--spin))}
.petal.tint-1 b{background:linear-gradient(135deg,var(--petal-a),var(--petal-c))}.petal.tint-2 b{background:linear-gradient(135deg,#fff,var(--petal-b));border-radius:100% 8% 100% 8%}
@keyframes petal-fall{from{transform:translate3d(0,-14vh,0)}to{transform:translate3d(var(--drift),114vh,0)}}
@keyframes petal-sway{from{transform:rotate(var(--spin)) rotate3d(1,.4,0,0deg) translateX(-14px)}to{transform:rotate(calc(var(--spin) + 140deg)) rotate3d(1,.4,0,62deg) translateX(14px)}}
.scene-glow{position:absolute;inset:-10%;background:radial-gradient(ellipse at 15% 16%,var(--glow-a),transparent 38%),radial-gradient(ellipse at 80% 75%,var(--glow-b),transparent 45%);mix-blend-mode:screen;animation:forest-light 7s ease-in-out infinite alternate;will-change:opacity}
.scene-motes{position:absolute;inset:-10%;background-image:radial-gradient(circle at 14% 34%,var(--mote) 0 2px,transparent 4px),radial-gradient(circle at 73% 19%,var(--mote) 0 1px,transparent 3px),radial-gradient(circle at 52% 76%,var(--mote-b) 0 2px,transparent 5px),radial-gradient(circle at 88% 61%,var(--mote) 0 1px,transparent 3px),radial-gradient(circle at 32% 52%,var(--mote) 0 1px,transparent 3px),radial-gradient(circle at 63% 41%,var(--mote-b) 0 1px,transparent 3px);opacity:.6}
@keyframes forest-light{from{opacity:.5}to{opacity:.95}}
.scene-foreground{background:radial-gradient(ellipse at 2% 100%,var(--foreground-a),transparent 42%),radial-gradient(ellipse at 98% 20%,var(--foreground-b),transparent 37%)}
.scene-mobile-sunlight{background:radial-gradient(ellipse at 8% 0%,color-mix(in srgb,var(--sun-gold) 38%,transparent),transparent 49%),radial-gradient(circle at 18% 14%,color-mix(in srgb,var(--sun-core) 34%,transparent) 0 1px,transparent 15px),radial-gradient(circle at 64% 28%,color-mix(in srgb,var(--sun-gold) 28%,transparent) 0 1px,transparent 12px);opacity:.48}
.scene-mobile-points{position:absolute;inset:0;background-image:radial-gradient(circle at 13% 23%,color-mix(in srgb,var(--sun-gold) 72%,transparent) 0 2px,transparent 6px),radial-gradient(circle at 72% 18%,color-mix(in srgb,var(--sun-gold) 62%,transparent) 0 2px,transparent 6px),radial-gradient(circle at 46% 64%,color-mix(in srgb,var(--sun-core) 70%,transparent) 0 2px,transparent 7px),radial-gradient(circle at 86% 78%,color-mix(in srgb,var(--sun-gold) 62%,transparent) 0 2px,transparent 6px),radial-gradient(circle at 29% 72%,color-mix(in srgb,var(--sun-core) 62%,transparent) 0 1.5px,transparent 5px),radial-gradient(circle at 57% 42%,color-mix(in srgb,var(--sun-gold) 68%,transparent) 0 1.5px,transparent 5px);opacity:.5}
.scene-mobile-petals .petal{filter:none;will-change:transform}
.scene-mobile-petals .petal b{animation:none}
/* The veil scrolls with its words; scene clones carry the same pseudo-element. */
.entry-intro::before{content:"";position:absolute;inset:-110px -140px;z-index:-1;pointer-events:none;background:var(--veil)}
/* The same circle clips the scene and this small, inert text copy. Keep the
   semantic original in the login layout; forms and autofill stay live. */
.scene-intro-copy.entry-intro{position:absolute;left:var(--intro-left);top:var(--intro-top);width:var(--intro-width);height:var(--intro-height);color:var(--ink);visibility:hidden}
.scene-brand-copy.entry-brand{position:absolute;left:var(--brand-left);top:var(--brand-top);color:var(--ink);visibility:hidden}
.scene-theme-line-copy.entry-theme-line{position:absolute;left:var(--theme-line-left);top:var(--theme-line-top);visibility:hidden}
/* Size the veil around the words, not the unused part of the grid column. */
.entry-layout>.entry-intro{width:fit-content;max-width:100%;justify-self:start}
[data-theme-changing] .scene-intro-copy,[data-theme-changing] .scene-brand-copy,[data-theme-changing] .scene-theme-line-copy{visibility:visible}
[data-theme-changing] .entry-gate>.entry-brand,[data-theme-changing] .entry-layout>.entry-intro,[data-theme-changing] .entry-footer>.entry-theme-line{opacity:0}
@media(prefers-reduced-motion:reduce),(hover:none),(pointer:coarse){.background-scene .scene-layer{transform:none!important;will-change:auto}}
@media(prefers-reduced-motion:reduce){.scene-glow,.scene-motes,.sun-shafts,.canopy-shadows,.scene-still,.login-light .scene-glow,.login-light .sun-shafts,.sun-core,.sun-rays{animation:none;will-change:auto}.scene-petals,.sun-sweep,.sun-sparkles,.scene-light-points{display:none}}.button,.icon-button,.panel,.upload-item{transition:transform .18s ease,box-shadow .18s ease,background .18s ease}.button:hover:enabled{transform:translateY(-1px)}.button:active:enabled{transform:translateY(0) scale(.98)}.modal{animation:workbench-enter .25s ease-out both}@keyframes workbench-enter{from{opacity:0;transform:translateY(7px)}to{opacity:1;transform:translateY(0)}}@media(prefers-reduced-motion:reduce){.view:not([hidden]),.modal{animation:none}.button,.icon-button,.panel,.upload-item{transition:none}.button:hover:enabled,.button:active:enabled{transform:none}}
@media(max-width:700px){.entry-intro::before{transform:translateX(-48px)}}
/* The user-requested mobile ambient effects stay gentle and explicit even
   when system-wide reduced motion disables every other scene animation. */
@media(prefers-reduced-motion:reduce){
 .scene-lightweight .scene-mobile-petals{display:block!important}
 .scene-lightweight .scene-mobile-petals .petal{animation:petal-fall var(--fall) linear var(--delay) infinite!important}
}
</style>
