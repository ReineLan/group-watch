<script setup>
import {onMounted,onUnmounted,ref,watch} from 'vue'
import {theme,setTheme,prepareThemeImage,prepareThemeThumbnails} from '../theme/theme.js'
import {themes} from '../theme/themes.js'
import {sceneAssets} from '../theme/assets.js'
import AppIcon from '../../shared/ui/AppIcon.vue'
const props=defineProps({variant:{type:String,default:'menu'}})
const open=ref(false),root=ref(null),toggle=ref(null)
let warmup
onMounted(()=>{warmup=setTimeout(prepareThemeThumbnails,150)})
function anticipate(id){void prepareThemeImage(id)}
function choose(id,event){
  let origin={x:event.clientX,y:event.clientY}
  if(!event.clientX&&!event.clientY){
    const rect=event.currentTarget.getBoundingClientRect()
    origin={x:rect.left+rect.width/2,y:rect.top+rect.height/2}
  }
  setTheme(id,origin)
  open.value=false
}
function outside(event){if(!root.value?.contains(event.target))open.value=false}
function key(event){if(event.key==='Escape'&&open.value){open.value=false;toggle.value?.focus()}}
watch(open,value=>{
  if(value){document.addEventListener('pointerdown',outside);document.addEventListener('keydown',key)}
  else{document.removeEventListener('pointerdown',outside);document.removeEventListener('keydown',key)}
})
onUnmounted(()=>{clearTimeout(warmup);open.value=false})
</script>
<template>
  <div v-if="props.variant==='strip'" class="theme-strip" role="radiogroup" aria-label="界面主题">
    <button v-for="item in themes" :key="item.id" type="button" role="radio" class="theme-orb" :aria-checked="theme===item.id" :title="item.name" @pointerenter="anticipate(item.id)" @focus="anticipate(item.id)" @click="choose(item.id,$event)">
      <img :src="sceneAssets[item.id].thumb" alt="" loading="lazy" decoding="async"><span>{{item.name}}</span>
    </button>
  </div>
  <div v-else ref="root" class="theme-menu">
    <button ref="toggle" class="icon-button theme-toggle" type="button" aria-label="切换主题" title="切换主题" aria-haspopup="true" :aria-expanded="open" @click="open=!open"><AppIcon name="palette"/></button>
    <div v-show="open" class="theme-popover" role="radiogroup" aria-label="界面主题">

      <div class="theme-grid">
        <button v-for="item in themes" :key="item.id" type="button" role="radio" class="theme-card" :aria-checked="theme===item.id" @pointerenter="anticipate(item.id)" @focus="anticipate(item.id)" @click="choose(item.id,$event)">
          <span class="theme-thumb"><img :src="sceneAssets[item.id].thumb" alt="" decoding="async"><i class="theme-check" aria-hidden="true">✓</i></span>
          <span class="theme-name">{{item.name}}</span>
          <span class="theme-line">{{item.line}}</span>
          <span class="theme-swatch" aria-hidden="true"><i v-for="color in item.swatch" :key="color" :style="{background:color}"></i></span>
        </button>
      </div>
    </div>
  </div>
</template>
<style>
.theme-menu{position:relative}
.theme-toggle{font-size:16px;display:grid;place-items:center;transition:transform .35s cubic-bezier(.3,1.4,.5,1),background .18s}
.theme-toggle:hover,.theme-toggle[aria-expanded=true]{transform:rotate(36deg);color:var(--highlight)}
.theme-popover{position:absolute;right:-6px;top:calc(100% + 12px);z-index:40;width:min(372px,calc(100vw - 32px));padding:16px;border-radius:18px;border:1px solid color-mix(in srgb,var(--glass-edge) 70%,transparent);background:color-mix(in srgb,var(--surface) 90%,transparent);backdrop-filter:blur(22px) saturate(1.2);box-shadow:0 24px 70px color-mix(in srgb,var(--shadow) 26%,transparent),inset 0 1px 0 color-mix(in srgb,var(--glass-edge) 60%,transparent);animation:theme-pop .28s cubic-bezier(.2,.8,.2,1) both;transform-origin:top right}
@keyframes theme-pop{from{opacity:0;transform:translateY(-6px) scale(.96)}to{opacity:1;transform:none}}
.theme-popover-title{display:flex;align-items:baseline;justify-content:space-between;font-size:13px;font-weight:600;color:var(--ink);margin:0 2px 12px}
.theme-popover-title small{font:600 9px Barlow,system-ui;letter-spacing:2.4px;color:var(--faint)}
.theme-grid{display:grid;grid-template-columns:1fr 1fr;gap:10px}
.theme-card{display:flex;flex-direction:column;gap:7px;padding:6px 6px 9px;border-radius:13px;border:1px solid transparent;background:transparent;text-align:left;color:var(--ink);transition:background .2s,border-color .2s,transform .2s}
.theme-card:hover{background:color-mix(in srgb,var(--surface-3) 70%,transparent);transform:translateY(-2px)}
.theme-card[aria-checked=true]{border-color:color-mix(in srgb,var(--accent) 45%,transparent);background:color-mix(in srgb,var(--surface-3) 55%,transparent)}
.theme-thumb{position:relative;display:block;width:100%;aspect-ratio:16/9;border-radius:9px;overflow:hidden;background:var(--surface-4);box-shadow:0 4px 14px color-mix(in srgb,var(--shadow) 18%,transparent)}
.theme-thumb img{width:100%;height:100%;object-fit:cover;display:block;transition:transform .5s cubic-bezier(.2,.7,.2,1)}
.theme-card:hover .theme-thumb img{transform:scale(1.07)}
.theme-check{position:absolute;right:6px;top:6px;display:grid;place-items:center;width:20px;height:20px;border-radius:50%;background:var(--accent);color:var(--on-accent);font:700 11px/1 system-ui;font-style:normal;opacity:0;transform:scale(.6);transition:opacity .2s,transform .25s cubic-bezier(.3,1.5,.5,1)}
.theme-card[aria-checked=true] .theme-check{opacity:1;transform:none}
.theme-name{display:flex;align-items:center;gap:7px;font-size:13px;font-weight:600;padding:0 3px}
.theme-line{font-size:10.5px;line-height:1.5;color:var(--subtle);padding:0 3px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.theme-swatch{display:flex;gap:4px;padding:0 3px}.theme-swatch i{width:14px;height:5px;border-radius:3px;box-shadow:0 0 0 1px color-mix(in srgb,var(--glass-edge) 45%,transparent)}
.theme-strip{display:flex;gap:10px;align-items:center}
.theme-orb{position:relative;display:flex;align-items:center;gap:0;height:38px;padding:3px;border-radius:999px;border:1px solid color-mix(in srgb,var(--glass-edge) 70%,transparent);background:color-mix(in srgb,var(--surface) 55%,transparent);color:var(--ink);backdrop-filter:blur(12px);transition:gap .35s cubic-bezier(.2,.8,.2,1),padding .35s cubic-bezier(.2,.8,.2,1),background .2s,box-shadow .2s}
.theme-orb img{width:30px;height:30px;border-radius:50%;object-fit:cover;flex-shrink:0}
.theme-orb span{max-width:0;overflow:hidden;white-space:nowrap;font-size:12px;font-weight:600;transition:max-width .4s cubic-bezier(.2,.8,.2,1)}
.theme-orb:hover,.theme-orb[aria-checked=true]{gap:8px;padding-right:13px;background:color-mix(in srgb,var(--surface) 82%,transparent);box-shadow:0 6px 20px color-mix(in srgb,var(--shadow) 16%,transparent)}
.theme-orb:hover span,.theme-orb[aria-checked=true] span{max-width:5em}
.theme-orb[aria-checked=true]{border-color:color-mix(in srgb,var(--accent) 50%,transparent)}
@media(prefers-reduced-motion:reduce){.theme-popover{animation:none}.theme-toggle,.theme-card,.theme-thumb img,.theme-orb,.theme-orb span{transition:none}}
@media(max-width:800px),(hover:none),(pointer:coarse){
 .theme-popover{box-sizing:border-box;position:fixed;inset:calc(env(safe-area-inset-top) + 76px) 12px auto;max-width:360px;width:auto;margin-left:auto;max-height:calc(100svh - 100px);overflow-y:auto;padding:12px;backdrop-filter:none;background:var(--surface)}
 .theme-grid{grid-template-columns:repeat(2,minmax(0,1fr));gap:8px}.theme-card{min-width:0;gap:5px;padding:5px 5px 8px}.theme-line{max-width:100%;font-size:10px}.theme-swatch i{width:12px}
 .theme-strip{gap:6px}.theme-orb{backdrop-filter:none}.theme-orb:hover:not([aria-checked=true]){gap:0;padding-right:3px}.theme-orb:hover:not([aria-checked=true]) span{max-width:0}
}
</style>
