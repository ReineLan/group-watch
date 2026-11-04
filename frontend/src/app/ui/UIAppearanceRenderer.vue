<script setup>
import {ref,onMounted,onUnmounted,watch} from 'vue'
import {scenes,registerRevealTarget} from '../theme/theme.js'
import {appearanceMasks} from '../theme/appearanceMasks.js'
defineProps({ready:Boolean,busy:Boolean,error:String,password:String,focused:Boolean,hovered:Boolean,composing:Boolean,scrollLeft:Number})
const host=ref(),rect=ref(null)
const masks=appearanceMasks(name=>{
  try{CSS.registerProperty({name,syntax:'<length>',inherits:true,initialValue:'0px'})}
  catch(error){if(error.name!=='InvalidModificationError')throw error}
})
watch(scenes,value=>masks.sync(value),{immediate:true,flush:'sync'})
function register(scene,node){registerRevealTarget(scene.key,'entry-appearance',node&&scene.ring?{node:node.parentElement,property:masks.property(scene.key)}:null)}
let observer
function measure(){const r=host.value?.parentElement.getBoundingClientRect();if(r)rect.value={left:r.left+'px',top:r.top+'px',width:r.width+'px',height:r.height+'px'}}
onMounted(()=>{observer=new ResizeObserver(measure);observer.observe(host.value.parentElement);measure();window.addEventListener('resize',measure);window.addEventListener('scroll',measure,{passive:true})})
onUnmounted(()=>{observer?.disconnect();window.removeEventListener('resize',measure);window.removeEventListener('scroll',measure)})
</script>
<template>
 <div ref="host" class="ui-appearance-host" aria-hidden="true" inert>
  <div v-for="(scene,index) in scenes" :key="scene.key" :ref="node=>register(scene,node)" class="ui-appearance-layer scene-theme-tokens" :data-scene-key="scene.key" :data-theme="scene.theme" :data-scene-role="scene.ring?'ring':'base'" :data-radius-property="scene.ring?masks.property(scene.key):null" :style="masks.style(scene,index,scenes)">
   <section v-if="rect" class="entry-card entry-card-visual" :style="rect">
    <span class="entry-card-mark">↗</span><span class="entry-overline">WELCOME BACK</span><h2>进入工作台</h2>
    <div class="entry-appearance-form">
     <div class="entry-password" :class="{'is-focused':focused}"><span class="appearance-input" :class="{'is-placeholder':!password,'is-editing':composing}"><span class="appearance-input-text" :style="password?{transform:`translateX(-${scrollLeft||0}px)`}:null">{{password||'请输入访问密码'}}</span></span></div>
     <p v-if="error" class="entry-error">{{error}}</p>
     <span aria-hidden="true" class="entry-submit entry-submit-placeholder" :class="{'is-disabled':busy||!ready||!password,'is-hovered':hovered&&!busy&&ready&&password}"><span>{{!ready?'正在连接…':busy?'正在进入…':'进入工作台'}}</span><span>→</span></span>
    </div>
   </section>
  </div>
 </div>
</template>
<style>
.ui-appearance-host{position:fixed;inset:0;pointer-events:none;z-index:0}
.ui-appearance-layer{position:absolute;inset:0;pointer-events:none;color:var(--ink)}
.entry-card.entry-card-visual{position:absolute;box-sizing:border-box;animation:none;pointer-events:none;backdrop-filter:none}
.entry-appearance-form{margin-top:28px}
.entry-password .appearance-input{display:block;box-sizing:border-box;width:100%;min-width:0;padding:15px;font:inherit;font-size:14px;color:var(--ink);white-space:pre;overflow:hidden}
.appearance-input.is-placeholder{color:var(--subtle)}
.appearance-input-text{display:block}
.appearance-input.is-editing{visibility:hidden}
.entry-card-visual .entry-password.is-focused{border-color:var(--accent);box-shadow:0 0 0 4px color-mix(in srgb,var(--accent-2) 10%,transparent)}
.entry-card-visual .entry-submit.is-disabled{opacity:.55}
.entry-card-visual .entry-submit{box-sizing:border-box}
.entry-card-visual .entry-submit.is-hovered{transform:translateY(-2px);background:var(--accent-strong);box-shadow:0 8px 20px color-mix(in srgb,var(--shadow) 21%,transparent)}
.entry-card.p3-card{background:none;border-color:transparent;box-shadow:none;backdrop-filter:none;animation:none;isolation:isolate}
.entry-card.p3-card::after{display:none}
.entry-card.p3-card>:is(.entry-overline,h2,form){position:relative;z-index:1}
.entry-card.p3-card>.entry-card-mark{z-index:1}
.p3-card>:is(.entry-overline,h2,.entry-card-mark),.p3-card>form .entry-error,.p3-card>form .entry-submit{color:transparent}
.p3-card>form .entry-password,.p3-card>form .entry-submit{background:transparent;border-color:transparent;box-shadow:none}
.p3-card>form .entry-password:focus-within{border-color:transparent;box-shadow:none}
.p3-card>form input{color:transparent;caret-color:var(--ink)}
.p3-card>form input.is-composing{color:var(--ink)}
.p3-card>form input::placeholder{color:transparent}
/* The real submit button owns its color; scene copies only reserve its space. */
.entry-submit-placeholder{visibility:hidden}
.entry-card.p3-card>form .entry-submit{background:var(--accent);color:var(--on-accent);box-shadow:0 5px 15px color-mix(in srgb,var(--shadow) 13%,transparent);transition:background-color .26s ease,color .26s ease,transform .2s,box-shadow .2s}
.entry-card.p3-card>form .entry-submit:hover:enabled{background:var(--accent-strong);box-shadow:0 8px 20px color-mix(in srgb,var(--shadow) 21%,transparent)}
:root[data-scene-static] .entry-card.p3-card{background:none}
@media(max-width:700px){.entry-appearance-form{margin-top:22px}.entry-password .appearance-input{padding:13px;font-size:16px}}
</style>
