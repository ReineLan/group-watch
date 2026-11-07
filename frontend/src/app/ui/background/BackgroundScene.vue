<script setup>
import {computed,onMounted,onUnmounted,ref,watch} from 'vue'
import {resolveTheme,petalField,sparkleField,meteorField,rippleField} from '../../theme/themes.js'
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
const petals=()=>petalField(lightweight.value?9:16).map(p=>({id:p.id,class:'petal tint-'+p.tint,style:{'--x':p.left+'vw','--size':p.size+'px','--fall':(lightweight.value?17:p.fall)+'s','--delay':p.delay+'s','--drift':(lightweight.value?Math.round(p.drift*.65):p.drift)+'px','--sway':p.sway+'s','--spin':p.spin+'deg','--alpha':lightweight.value?Math.min(p.opacity,.88):p.opacity,'--blur':lightweight.value?0:p.blur+'px'}}))
const skyVars={
  comet:m=>({'--ox':m.ox+'px','--oy':m.oy+'px','--r':m.radius+'px','--from':m.from+'deg','--to':m.to+'deg','--tail':m.tail+'deg'}),
  meteor:m=>({'--size':m.size+'px','--angle':m.angle+'deg'}),
  mote:m=>({'--size':m.size+'px','--drift':m.drift+'px','--rise':m.rise+'px'}),
  star:m=>({'--size':m.size+'px'}),
}
const bit=(name,d)=>({class:name,style:{'--dx':d.x+'px','--dy':d.y+'px','--size':d.size+'px','--delay':d.delay+'s'}})
const meteors=()=>meteorField(lightweight.value?13:30).map(m=>({id:m.id,class:{comet:'comet',meteor:'meteor',mote:'sun-mote',star:'star-glint'}[m.kind],
  style:{'--x':m.left+'%','--y':m.top+'%','--dur':m.duration+'s','--delay':m.delay+'s',...skyVars[m.kind](m)},
  star:m.kind==='star',
  bits:m.kind==='comet'?[...m.dust.map(d=>bit(d.spark?'comet-spark':'comet-dust',d)),bit('comet-flare',m.flare)]:[]}))
const ripples=()=>rippleField(lightweight.value?9:18).map(r=>({id:r.id,water:r.kind==='ripple',class:'pond-'+r.kind+' tint-'+r.tint,style:{'--x':r.left+'%','--y':r.top+'%','--size':r.size+'px','--dur':r.duration+'s','--delay':r.delay+'s','--drift':r.drift+'px','--rise':r.rise+'px'}}))
// The particle layer keeps the scene-petals class so parallax, reduced motion and the mobile layer apply to every effect.
const particles=computed(()=>({meteors,ripples}[current.value.effect]||petals)())
// Water-bound items sit on the scene art, so they get their own layer that moves with the background's parallax depth.
const water=computed(()=>particles.value.filter(item=>item.water)),air=computed(()=>particles.value.filter(item=>!item.water&&!item.star)),stars=computed(()=>particles.value.filter(item=>item.star))
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

// 徊夜's rays spin follows the radius breathe on the shared scene clock: the speed is a smooth
// sinusoid of the breathe phase (peak 15°/s at full radius), not stepped keyframe segments.
let spinAngle=0,spinLast=0,spinRaf=0
const breathePhase=now=>{const tri=(((now-props.clock)/11000)%2+2)%2;return(1-Math.cos(Math.PI*(tri<1?tri:2-tri)))/2}
function spinTick(now){
  const rays=!still.value&&current.value.effect==='meteors'?stage.value?.querySelector('.halo-rays'):null
  if(rays){
    if(spinLast)spinAngle+=(1.5+13.5*breathePhase(now))*Math.min(now-spinLast,100)/1000
    rays.style.rotate=spinAngle.toFixed(2)+'deg';spinLast=now
  }else spinLast=0
  spinRaf=requestAnimationFrame(spinTick)
}

onMounted(()=>{
  if(current.value.effect==='meteors')spinRaf=requestAnimationFrame(spinTick)
  compact.addEventListener('change',syncEffects);window.addEventListener('resize',syncEffects,{passive:true});syncEffects()
  const timed=document.documentElement.dataset.themePerformanceRecording==='true',before=timed?performance.now():0
  joinSceneClock(stage.value,props.clock)
  if(timed){const shell=stage.value.parentElement;shell.sceneTimings??={};shell.sceneTimings.animationClockMs=performance.now()-before}
  syncVideo();props.lifecycle?.('mount');emit('ready')
})
onUnmounted(()=>{cancelAnimationFrame(spinRaf);stopVideo();compact.removeEventListener('change',syncEffects);window.removeEventListener('resize',syncEffects);props.lifecycle?.('destroy')})
</script>
<template>
 <div ref="stage" class="background-scene scene-composite-group scene-theme-tokens" :data-theme="current.id" :class="['effect-'+current.effect,'scene-'+current.id,{'login-light':login,'scene-lightweight':lightweight}]">
    <div class="scene-media scene-layer">
      <div class="scene-art scene-still" :style="{backgroundImage:`url(${assets.image}),url(${assets.thumb})`}"></div>
      <canvas v-if="videoEnabled&&assets.video&&!still" ref="canvas" class="scene-art scene-video"></canvas>
    </div>
    <div class="wash scene-layer"></div>
    <!-- 徊夜's sunrise halo is part of the sky, so it stays (motionless) in still scenes and moves at the art's depth. -->
    <div v-if="current.effect==='meteors'" class="scene-halo scene-layer" :class="{'is-still':still}" data-depth="7"><i class="halo-glow"></i><i class="halo-rays"></i><i class="halo-bow"></i><i class="halo-shimmer"></i></div>
    <div v-if="!still" class="scene-haze scene-layer"></div>
    <div v-else-if="lightweight&&(current.effect==='sunlight'||current.sunbeam)" class="scene-mobile-sunlight scene-layer"></div>
    <div v-if="!still&&water.length" class="scene-petals scene-water scene-layer" data-depth="7"><i v-for="item in water" :key="item.id" :class="item.class" :style="item.style"><b></b></i></div>
    <div v-if="!still&&(current.effect==='sunlight'||current.sunbeam)" class="scene-beam scene-layer">
      <div class="sun-core"></div><div class="sun-shafts"></div><div class="canopy-shadows"></div>
      <div v-if="current.effect==='sunlight'" class="sun-sparkles"><i v-for="sparkle in sparkles" :key="sparkle.id" class="sparkle" :class="sparkle.kind" :style="sparkle.style"></i></div>
    </div>
    <!-- Stars get their own shallower parallax: less pointer travel than the comets but still free of the art. -->
    <div v-if="!still&&stars.length" class="scene-petals scene-stars scene-layer" data-depth="16"><i v-for="item in stars" :key="item.id" :class="item.class" :style="item.style"><b></b></i></div>
    <div v-if="!still&&current.effect!=='sunlight'" class="scene-petals scene-layer"><i v-for="item in air" :key="item.id" :class="item.class" :style="item.style"><b></b><s v-for="(bit,index) in item.bits" :key="index" :class="bit.class" :style="bit.style"></s></i></div>
    <!-- Lens ghosts sit on the camera, not the sky: they slide against the pointer. -->
    <div v-if="!still&&current.effect==='meteors'" class="scene-flares scene-layer" data-depth="-18"><i class="flare-ghost ghost-1"></i><i class="flare-ghost ghost-2"></i><i class="flare-ghost ghost-3"></i><i class="flare-ghost ghost-4"></i></div>
    <div v-if="lightweight&&current.effect!=='sunlight'" class="scene-petals scene-mobile-petals scene-layer"><i v-for="item in particles" :key="item.id" :class="item.class" :style="item.style"><b></b><s v-for="(bit,index) in item.bits" :key="index" :class="bit.class" :style="bit.style"></s></i></div>
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
.sun-core{position:absolute;left:calc(-22vmax + 30px);top:calc(-30vmax + 30px);width:78vmax;height:78vmax;border-radius:50%;opacity:var(--sun-core-opacity,1);background:radial-gradient(circle,var(--sun-core) 0,color-mix(in srgb,var(--sun-core) 70%,transparent) 9%,color-mix(in srgb,var(--sun-gold) 38%,transparent) 26%,color-mix(in srgb,var(--sun-gold) 10%,transparent) 44%,transparent 64%)}
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
/* Snow reuses the petal field: round, softer flakes that fall slower and only drift sideways. */
.effect-snow .petal{height:var(--size);animation-duration:calc(var(--fall)*1.5)}
.effect-snow .petal b,.effect-snow .petal.tint-1 b,.effect-snow .petal.tint-2 b{border-radius:50%;background:radial-gradient(circle,var(--petal-a) 0 30%,color-mix(in srgb,var(--petal-c) 70%,transparent) 48%,transparent 70%);box-shadow:none;transform:none;animation-name:snow-sway}
@keyframes snow-sway{from{transform:translateX(-10px)}to{transform:translateX(10px)}}
/* 徊夜 comets: the wrapper sits on the arc's centre and a quarter-circle box pivots around it, so the head
   glides along the arc. A conic gradient clipped to a thin ring draws the tail, a wider blurred ring its aura;
   glitter left on the path lights up as the head passes, and a four-point flare bursts where the arc ends. */
.comet{position:absolute;left:calc(var(--x) + var(--ox));top:calc(var(--y) + var(--oy));width:0;height:0}
.comet b{position:absolute;left:0;top:calc(var(--r)*-1);width:var(--r);height:var(--r);transform-origin:0 100%;opacity:0;background:radial-gradient(circle 10px at calc(var(--r)*.9848) calc(var(--r)*.8264),var(--meteor),color-mix(in srgb,var(--meteor-glow) 60%,transparent) 40%,transparent);animation:comet-glide var(--dur) linear var(--delay) infinite;will-change:transform,opacity}
.comet b::before,.comet b::after{content:"";position:absolute;inset:0;background:conic-gradient(from calc(80deg - var(--tail)) at 0 100%,transparent,color-mix(in srgb,var(--meteor-tail) 60%,transparent) calc(var(--tail)*.62),var(--meteor) var(--tail),transparent calc(var(--tail) + .4deg));mask-image:radial-gradient(circle at 0 100%,transparent calc(var(--r) - 2.5px),#000 calc(var(--r) - 1.5px),#000 calc(var(--r) + .5px),transparent calc(var(--r) + 1.5px))}
.comet b::after{opacity:.75;filter:blur(2px);background:conic-gradient(from calc(80deg - var(--tail)) at 0 100%,transparent,color-mix(in srgb,var(--meteor-glow) 45%,transparent) calc(var(--tail)*.7),color-mix(in srgb,var(--meteor-tail) 85%,transparent) var(--tail),transparent calc(var(--tail) + .4deg));mask-image:radial-gradient(circle at 0 100%,transparent calc(var(--r) - 9px),#000 calc(var(--r) - .5px),transparent calc(var(--r) + 8px))}
@keyframes comet-glide{0%{opacity:0;transform:rotate(var(--from))}2.5%,14%{opacity:1}17%,100%{opacity:0;transform:rotate(var(--to))}}
.comet s{position:absolute;left:var(--dx);top:var(--dy);width:var(--size);height:var(--size);margin:calc(var(--size)*-.5);border-radius:50%;opacity:0;background:radial-gradient(circle,var(--meteor) 0 32%,color-mix(in srgb,var(--meteor-dust) 70%,transparent) 55%,transparent 72%);animation:comet-dust var(--dur) linear var(--delay) infinite;will-change:transform,opacity}
.comet s.comet-spark{width:calc(var(--size)*3.4);height:calc(var(--size)*3.4);margin:calc(var(--size)*-1.7);border-radius:0;background:radial-gradient(circle,var(--meteor) 0 10%,transparent 34%),linear-gradient(90deg,transparent 45%,var(--meteor-dust) 50%,transparent 55%),linear-gradient(0deg,transparent 45%,var(--meteor-dust) 50%,transparent 55%)}
@keyframes comet-dust{0%{opacity:0;transform:scale(.2)}1%{opacity:1;transform:scale(1.3)}5%{opacity:.4;transform:translate3d(0,4px,0) scale(.8)}9%{opacity:.95;transform:translate3d(-2px,8px,0) scale(1.05)}26%,100%{opacity:0;transform:translate3d(-7px,24px,0) scale(.3)}}
.comet s.comet-flare{width:var(--size);height:var(--size);margin:calc(var(--size)*-.5);border-radius:0;background:radial-gradient(circle,var(--meteor) 0 3%,color-mix(in srgb,var(--meteor-glow) 55%,transparent) 8%,transparent 24%),linear-gradient(90deg,transparent,var(--meteor) 50%,transparent) center/100% 2px no-repeat,linear-gradient(0deg,transparent,var(--meteor) 50%,transparent) center/2px 100% no-repeat,linear-gradient(45deg,transparent 38%,color-mix(in srgb,var(--meteor-dust) 70%,transparent) 50%,transparent 62%) center/1.5px 44% no-repeat;filter:drop-shadow(0 0 6px var(--meteor-glow));animation-name:comet-flare}
@keyframes comet-flare{0%{opacity:0;transform:scale(.1) rotate(-25deg)}2%{opacity:1;transform:scale(1.15) rotate(0deg)}5%{opacity:.7;transform:scale(.82) rotate(6deg)}9%{opacity:1;transform:scale(1) rotate(10deg)}20%,100%{opacity:0;transform:scale(.3) rotate(28deg)}}
/* Open-sky meteors cross toward the sunrise; the bright head is the right end of the streak. */
.meteor{position:absolute;left:var(--x);top:var(--y);width:var(--size);height:2px;opacity:0;transform-origin:100% 50%;animation:meteor-run var(--dur) linear var(--delay) infinite;will-change:transform,opacity}
.meteor b{display:block;width:100%;height:100%;border-radius:2px;background:linear-gradient(90deg,transparent,color-mix(in srgb,var(--meteor-tail) 55%,transparent) 72%,var(--meteor));filter:drop-shadow(0 0 5px var(--meteor-glow))}
@keyframes meteor-run{0%{opacity:0;transform:rotate(var(--angle)) translateX(0)}2%{opacity:1}11%,100%{opacity:0;transform:rotate(var(--angle)) translateX(34vmax)}}
.sun-mote{position:absolute;left:var(--x);top:var(--y);width:var(--size);height:var(--size);margin:calc(var(--size)*-.5);border-radius:50%;opacity:0;background:radial-gradient(circle,var(--halo-core) 0 30%,color-mix(in srgb,var(--halo-warm) 60%,transparent) 55%,transparent 72%);animation:sun-mote var(--dur) ease-in-out var(--delay) infinite;will-change:transform,opacity}
@keyframes sun-mote{0%{opacity:0;transform:translate3d(0,0,0) scale(.5)}18%{opacity:.95;transform:translate3d(calc(var(--drift)*.15),calc(var(--rise)*.2),0) scale(1)}55%{opacity:.5;transform:translate3d(calc(var(--drift)*.6),calc(var(--rise)*.55),0) scale(1.2)}75%{opacity:.85}100%{opacity:0;transform:translate3d(var(--drift),var(--rise),0) scale(.7)}}
/* The sunrise sits below the bottom-right corner: breathing glow, slow rays, a rainbow arc and a glint running along it. */
.scene-halo{--sun-x:90%;--sun-y:118%;mix-blend-mode:screen;will-change:transform;transform:translate3d(0,0,0)}
.scene-halo i{position:absolute;left:var(--sun-x);top:var(--sun-y);width:var(--halo-size);height:var(--halo-size);margin:calc(var(--halo-size)*-.5);border-radius:50%}
.halo-glow{--halo-size:100vmax;opacity:.9;background:radial-gradient(circle closest-side,var(--halo-core),color-mix(in srgb,var(--halo-core) 72%,transparent) 14%,color-mix(in srgb,var(--halo-warm) 48%,transparent) 30%,color-mix(in srgb,var(--halo-rose) 20%,transparent) 48%,color-mix(in srgb,var(--halo-warm) 6%,transparent) 68%,transparent);animation:halo-breathe 11s ease-in-out infinite alternate,halo-radius 11s ease-in-out infinite alternate;will-change:transform,opacity}
.halo-rays{--halo-size:92vmax;background:repeating-conic-gradient(from 0deg,transparent,color-mix(in srgb,var(--halo-core) 24%,transparent) 2deg,transparent 6deg 11deg),repeating-conic-gradient(from 5deg,transparent,color-mix(in srgb,var(--halo-warm) 15%,transparent) 3deg,transparent 9deg 19deg);mask-image:radial-gradient(circle closest-side,transparent 64%,#000 76% 86%,transparent 96%);filter:blur(4px);animation:halo-rays-breathe 11s ease-in-out infinite alternate,halo-radius 11s ease-in-out infinite alternate;will-change:transform,opacity,filter}
.halo-bow,.halo-shimmer{--halo-size:86vmax}
.halo-bow{opacity:.6;background:radial-gradient(circle closest-side,transparent 79%,color-mix(in srgb,var(--bow-v) 40%,transparent) 81%,color-mix(in srgb,var(--bow-b) 42%,transparent) 83%,color-mix(in srgb,var(--bow-c) 44%,transparent) 85.5%,color-mix(in srgb,var(--bow-g) 42%,transparent) 88%,color-mix(in srgb,var(--bow-y) 46%,transparent) 90.5%,color-mix(in srgb,var(--bow-o) 44%,transparent) 93%,color-mix(in srgb,var(--bow-r) 36%,transparent) 95.5%,transparent 98.5%);mask-image:linear-gradient(100deg,transparent 6%,#000 36%);filter:blur(9px);animation:bow-glow 11s ease-in-out infinite alternate,halo-radius 11s ease-in-out infinite alternate;will-change:transform,opacity,filter}
.halo-shimmer{opacity:0;background:radial-gradient(circle closest-side,transparent 84%,color-mix(in srgb,var(--halo-core) 60%,transparent) 88.5%,transparent 93%);mask-image:conic-gradient(from 285deg,transparent,#000 14deg,transparent 30deg);filter:blur(4px);animation:bow-shimmer 13s ease-in-out infinite,halo-radius 11s ease-in-out infinite alternate;will-change:transform,opacity}
@keyframes halo-breathe{from{opacity:.72}to{opacity:1}}
/* Radius breath rides the scale property so it composes with each layer's rotate/transform animations. */
@keyframes halo-radius{from{scale:.8}to{scale:1}}
/* The rays' spin is driven per-frame from the shared clock (see spinTick in script): a smooth
   sinusoidal speed curve instead of stepped keyframes, phase-locked to the 11s breathe. */
/* Shares halo-radius' 11s alternate cycle: rays sharpen as the glow expands and soften as it contracts. */
@keyframes halo-rays-breathe{from{opacity:.06;filter:blur(7px)}to{opacity:.55;filter:blur(2px)}}
@keyframes bow-glow{from{opacity:1;filter:blur(6px) saturate(2.6)}to{opacity:.75;filter:blur(9px) saturate(1)}}
@keyframes bow-shimmer{0%{opacity:0;rotate:0deg}12%,52%{opacity:.9}66%,100%{opacity:0;rotate:88deg}}
.scene-halo.is-still i{animation:none}.scene-halo.is-still .halo-shimmer{display:none}
.scene-flares{mix-blend-mode:screen;will-change:transform;transform:translate3d(0,0,0)}
.flare-ghost{position:absolute;left:var(--gx);top:var(--gy);width:var(--gs);height:var(--gs);margin:calc(var(--gs)*-.5);border-radius:50%;animation:ghost-breathe 11s ease-in-out infinite alternate;will-change:transform,opacity}
.ghost-1{--gx:77%;--gy:94%;--gs:84px;background:radial-gradient(circle closest-side,transparent 55%,color-mix(in srgb,var(--halo-warm) 26%,transparent) 78%,color-mix(in srgb,var(--bow-c) 18%,transparent) 92%,transparent)}
.ghost-2{--gx:70%;--gy:83%;--gs:22px;background:radial-gradient(circle closest-side,color-mix(in srgb,var(--halo-core) 45%,transparent),transparent)}
.ghost-3{--gx:63%;--gy:71%;--gs:120px;border-radius:0;clip-path:polygon(25% 6%,75% 6%,100% 50%,75% 94%,25% 94%,0 50%);background:radial-gradient(circle closest-side,color-mix(in srgb,var(--bow-b) 9%,transparent) 60%,color-mix(in srgb,var(--bow-v) 22%,transparent) 96%)}
.ghost-4{--gx:56%;--gy:60%;--gs:46px;background:radial-gradient(circle closest-side,transparent 62%,color-mix(in srgb,var(--bow-v) 24%,transparent) 86%,transparent)}
@keyframes ghost-breathe{from{opacity:.3;transform:scale(.92)}to{opacity:1;transform:scale(1.06)}}
.star-glint{position:absolute;left:var(--x);top:var(--y);width:var(--size);height:var(--size);margin:calc(var(--size)*-.5);animation:star-twinkle var(--dur) ease-in-out var(--delay) infinite;will-change:transform,opacity}
.star-glint b{display:block;width:100%;height:100%;background:radial-gradient(circle,var(--meteor) 0 12%,transparent 42%),linear-gradient(90deg,transparent 46%,var(--meteor) 50%,transparent 54%),linear-gradient(0deg,transparent 46%,var(--meteor) 50%,transparent 54%);filter:drop-shadow(0 0 4px var(--meteor-glow))}
@keyframes star-twinkle{0%,100%{opacity:.15;transform:scale(.45)}50%{opacity:1;transform:scale(1)}}
/* Pond ripples spread as flattened rings, a second ring trailing the first; large bokeh drift above the water. */
.pond-ripple{position:absolute;left:var(--x);top:var(--y);width:var(--size);height:calc(var(--size)*.3);margin:calc(var(--size)*-.15) 0 0 calc(var(--size)*-.5)}
.pond-ripple::before,.pond-ripple b{content:"";position:absolute;inset:0;border-radius:50%;border:2.5px solid var(--ripple);box-shadow:0 0 0 1px color-mix(in srgb,var(--ripple-shade) 45%,transparent),0 0 14px var(--ripple-glow),inset 0 0 10px var(--ripple-glow);opacity:0;animation:ripple-spread var(--dur) ease-out var(--delay) infinite;will-change:transform,opacity}
.pond-ripple::before{animation-delay:calc(var(--delay) + .8s)}
@keyframes ripple-spread{0%{opacity:0;transform:scale(.12)}6%{opacity:.95}55%,100%{opacity:0;transform:scale(1)}}
/* Bokeh wander along a curved path (outer) while the disc sharpens out of a blur, breathes,
   then swells and diffuses away (inner); both share one duration so they stay in phase. */
.pond-bokeh{--tone:var(--bokeh-a);position:absolute;left:var(--x);top:var(--y);width:var(--size);height:var(--size);margin:calc(var(--size)*-.5);animation:pond-bokeh-drift var(--dur) ease-in-out var(--delay) infinite;will-change:transform}
.pond-bokeh.tint-1{--tone:var(--bokeh-b)}.pond-bokeh.tint-2{--tone:var(--bokeh-c)}
.pond-bokeh b{display:block;width:100%;height:100%;border-radius:50%;opacity:0;background:radial-gradient(circle,color-mix(in srgb,var(--bokeh-core) 34%,transparent) 0,color-mix(in srgb,var(--tone) 34%,transparent) 52%,color-mix(in srgb,var(--tone) 58%,transparent) 64%,transparent 72%);animation:pond-bokeh-life var(--dur) ease-in-out var(--delay) infinite;will-change:transform,opacity,filter}
@keyframes pond-bokeh-drift{0%{transform:translate3d(0,0,0)}30%{transform:translate3d(calc(var(--drift)*.5),calc(var(--rise)*-.22),0)}62%{transform:translate3d(calc(var(--drift)*.12),calc(var(--rise)*-.6),0)}100%{transform:translate3d(var(--drift),calc(var(--rise)*-1),0)}}
@keyframes pond-bokeh-life{0%{opacity:0;transform:scale(.55);filter:blur(12px)}22%{opacity:.88;transform:scale(1);filter:blur(2px)}48%{opacity:.7;transform:scale(1.1);filter:blur(5px)}70%{opacity:.85;transform:scale(1);filter:blur(2px)}100%{opacity:0;transform:scale(1.75);filter:blur(22px)}}
@keyframes pond-bokeh-life-lite{0%{opacity:0;transform:scale(.55)}22%{opacity:.85;transform:scale(1)}48%{opacity:.7;transform:scale(1.1)}70%{opacity:.8;transform:scale(1)}100%{opacity:0;transform:scale(1.6)}}
.scene-glow{position:absolute;inset:-10%;background:radial-gradient(ellipse at 15% 16%,var(--glow-a),transparent 38%),radial-gradient(ellipse at 80% 75%,var(--glow-b),transparent 45%);mix-blend-mode:screen;animation:forest-light 7s ease-in-out infinite alternate;will-change:opacity}
.scene-motes{position:absolute;inset:-10%;background-image:radial-gradient(circle at 14% 34%,var(--mote) 0 2px,transparent 4px),radial-gradient(circle at 73% 19%,var(--mote) 0 1px,transparent 3px),radial-gradient(circle at 52% 76%,var(--mote-b) 0 2px,transparent 5px),radial-gradient(circle at 88% 61%,var(--mote) 0 1px,transparent 3px),radial-gradient(circle at 32% 52%,var(--mote) 0 1px,transparent 3px),radial-gradient(circle at 63% 41%,var(--mote-b) 0 1px,transparent 3px);opacity:.6}
@keyframes forest-light{from{opacity:.5}to{opacity:.95}}
.scene-foreground{background:radial-gradient(ellipse at 2% 100%,var(--foreground-a),transparent 42%),radial-gradient(ellipse at 98% 20%,var(--foreground-b),transparent 37%)}
.scene-mobile-sunlight{background:radial-gradient(ellipse at 8% 0%,color-mix(in srgb,var(--sun-gold) 38%,transparent),transparent 49%),radial-gradient(circle at 18% 14%,color-mix(in srgb,var(--sun-core) 34%,transparent) 0 1px,transparent 15px),radial-gradient(circle at 64% 28%,color-mix(in srgb,var(--sun-gold) 28%,transparent) 0 1px,transparent 12px);opacity:.48}
.scene-mobile-points{position:absolute;inset:0;background-image:radial-gradient(circle at 13% 23%,color-mix(in srgb,var(--sun-gold) 72%,transparent) 0 2px,transparent 6px),radial-gradient(circle at 72% 18%,color-mix(in srgb,var(--sun-gold) 62%,transparent) 0 2px,transparent 6px),radial-gradient(circle at 46% 64%,color-mix(in srgb,var(--sun-core) 70%,transparent) 0 2px,transparent 7px),radial-gradient(circle at 86% 78%,color-mix(in srgb,var(--sun-gold) 62%,transparent) 0 2px,transparent 6px),radial-gradient(circle at 29% 72%,color-mix(in srgb,var(--sun-core) 62%,transparent) 0 1.5px,transparent 5px),radial-gradient(circle at 57% 42%,color-mix(in srgb,var(--sun-gold) 68%,transparent) 0 1.5px,transparent 5px);opacity:.5}
.scene-mobile-petals .petal{filter:none;will-change:transform}
.scene-mobile-petals .petal b{animation:none}
.scene-mobile-petals .pond-bokeh b{filter:blur(3px);animation-name:pond-bokeh-life-lite}
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
 .scene-lightweight .scene-mobile-petals .meteor{animation:meteor-run var(--dur) linear var(--delay) infinite!important}
 .scene-lightweight .scene-mobile-petals .comet b{animation:comet-glide var(--dur) linear var(--delay) infinite!important}
 .scene-lightweight .scene-mobile-petals .comet s{animation:comet-dust var(--dur) linear var(--delay) infinite!important}
 .scene-lightweight .scene-mobile-petals .comet s.comet-flare{animation-name:comet-flare!important}
 .scene-lightweight .scene-mobile-petals .sun-mote{animation:sun-mote var(--dur) ease-in-out var(--delay) infinite!important}
 .scene-lightweight .scene-mobile-petals .star-glint{animation:star-twinkle var(--dur) ease-in-out var(--delay) infinite!important}
 .scene-lightweight .scene-mobile-petals .pond-ripple b{animation:ripple-spread var(--dur) ease-out var(--delay) infinite!important}
 .scene-lightweight .scene-mobile-petals .pond-ripple::before{animation:ripple-spread var(--dur) ease-out calc(var(--delay) + .8s) infinite!important}
 .scene-lightweight .scene-mobile-petals .pond-bokeh{animation:pond-bokeh-drift var(--dur) ease-in-out var(--delay) infinite!important}
 .scene-lightweight .scene-mobile-petals .pond-bokeh b{animation:pond-bokeh-life-lite var(--dur) ease-in-out var(--delay) infinite!important}
}
</style>
