<script setup>
import {onMounted,onUnmounted,ref} from 'vue'
import BackgroundScene from './BackgroundScene.vue'
import {scenes,registerSceneNode,registerSceneLifecycle,resources,sceneVideoEnabled} from '../../theme/theme.js'
import {pointerPosition,positionSceneLayers} from './parallax.js'
import {revealClip} from '../../theme/revealTargets.js'
defineProps({login:Boolean,introRect:Object,brandRect:Object,themeLineRect:Object})
const stage=ref(null)
let frame=0,target={x:0,y:0},now={x:0,y:0},motion,precision,hasPointer=false
// All instances share this epoch, including a scene entered again mid-transition.
const clock=document.timeline.currentTime??performance.now()
function position(){positionSceneLayers(stage.value,now)}
function allowed(){return !motion.matches&&precision.matches&&!document.hidden}
function animate(){
  frame=0
  if(!allowed())return
  now.x+=(target.x-now.x)*.075;now.y+=(target.y-now.y)*.075;position()
  if(Math.abs(target.x-now.x)+Math.abs(target.y-now.y)>.001)frame=requestAnimationFrame(animate)
}
function schedule(){if(!frame&&allowed())frame=requestAnimationFrame(animate)}
function move(event){
  if(event.pointerType==='touch'||!allowed())return
  target=pointerPosition(event.clientX,event.clientY,innerWidth,innerHeight)
  if(!hasPointer){now={...target};hasPointer=true;position()}
  schedule()
}
function change(){
  resources.videos.setVisible(!document.hidden)
  cancelAnimationFrame(frame);frame=0
  if(motion.matches||!precision.matches){now=target={x:0,y:0};hasPointer=false;position()}
  else schedule()
}
onMounted(()=>{
  motion=matchMedia('(prefers-reduced-motion: reduce)');precision=matchMedia('(hover: hover) and (pointer: fine)')
  window.addEventListener('pointermove',move,{passive:true});document.addEventListener('visibilitychange',change)
  motion.addEventListener('change',change);precision.addEventListener('change',change);change()
})
onUnmounted(()=>{
  cancelAnimationFrame(frame);window.removeEventListener('pointermove',move);document.removeEventListener('visibilitychange',change)
  motion?.removeEventListener('change',change);precision?.removeEventListener('change',change)
})
</script>
<template>
 <div ref="stage" class="scene-stage" aria-hidden="true" :style="{
  ...(introRect?{'--intro-left':introRect.left+'px','--intro-top':introRect.top+'px','--intro-width':introRect.width+'px','--intro-height':introRect.height+'px'}:{}),
  ...(brandRect?{'--brand-left':brandRect.left+'px','--brand-top':brandRect.top+'px'}:{}),
  ...(themeLineRect?{'--theme-line-left':themeLineRect.left+'px','--theme-line-top':themeLineRect.top+'px'}:{})
 }">
  <div class="scene-transition-host">
   <div v-for="scene in scenes" :key="scene.key" :ref="node=>registerSceneNode(scene.key,node)" class="theme-reveal-layer" :data-scene-key="scene.key" :data-theme="scene.theme" :data-scene-role="scene.ring?'ring':'base'" data-scene-structure="vue-scenes-e3-v1" :style="revealClip(scene)">
    <BackgroundScene :theme-id="scene.theme" :login="login" :intro-rect="introRect" :clock="clock" :videos="resources.videos" :video-enabled="sceneVideoEnabled" :lifecycle="kind=>registerSceneLifecycle(scene.key,kind)" :class="{'scene-transition-source':!scene.ring}" @ready="position"><slot :theme="scene.theme"/></BackgroundScene>
   </div>
  </div>
 </div>
</template>
