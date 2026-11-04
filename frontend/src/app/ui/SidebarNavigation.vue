<script setup>
import BrandGlyph from '../../shared/ui/BrandGlyph.vue'
import {computed} from 'vue'
import {pages} from '../navigation.js'
import AppIcon from '../../shared/ui/AppIcon.vue'
import RepositoryLink from '../../shared/ui/RepositoryLink.vue'
import {count} from '../../shared/lib/format.js'
const props=defineProps({active:String, connected:Boolean, pending:Number, activity:Array, qqPort:Number})
defineEmits(['close'])
const total=computed(()=>(props.activity||[]).reduce((sum,group)=>sum+group.messages,0))
const peak=computed(()=>Math.max(1,...(props.activity||[]).map(group=>group.messages)))
</script>
<template>
  <aside class="sidebar" id="workspace-sidebar" aria-label="工作台侧栏">
    <div class="brand"><a class="brand-mark" href="#overview" aria-label="Lan 首页"><BrandGlyph/></a><span class="brand-text"><span class="brand-name">Lan</span><small>群管理工作台<RepositoryLink/></small></span></div>
    <button id="close-navigation" class="icon-button" aria-label="收起导航" @click="$emit('close')">×</button>
    <nav aria-label="工作台导航">
      <span class="nav-label">工作台</span>
      <template v-for="page in pages" :key="page.key">
        <span v-if="page.settings" class="nav-label">设置</span>
        <a :href="'#'+page.key" :data-view="page.key" :aria-current="active===page.key?'page':undefined">
          <span class="nav-icon"><AppIcon :name="page.icon"/></span><span class="nav-text">{{page.label}}</span>
          <span v-if="page.key==='events'" class="nav-count" :class="{quiet:!pending}" id="nav-count">{{pending}}</span>
        </a>
      </template>
    </nav>
    <details class="sidebar-bottom connection-details">
      <summary>
        <span id="sidebar-dot" class="dot" :class="{online:connected}"></span>
        <span class="connection-copy"><strong id="sidebar-status">{{connected?'消息通道已连接':'消息通道未连接'}}</strong><small>{{connected?(activity||[]).length+' 个群 · 24 小时 '+count(total)+' 条':qqPort?'请检查 SnowLuma '+qqPort+' 端口':'请配置 SnowLuma 监听端口'}}</small></span>
      </summary>
      <div class="connection-groups">
        <div v-for="group in activity" :key="group.group_id" class="connection-group">
          <strong>{{group.group_name}}</strong><small>{{count(group.messages)}} 条</small>
          <i :style="{'--share':group.messages/peak}"></i>
        </div>
      </div>
    </details>
  </aside>
</template>
<style scoped>
.brand-text small{position:relative;width:max-content}.brand-text small :deep(.repository-link){position:absolute;left:calc(100% + 4px);top:50%;transform:translateY(-50%)}.brand-mark{text-decoration:none}
.connection-details.sidebar-bottom{display:block;width:100%;margin-top:auto}
.connection-details summary{display:flex;align-items:center;gap:11px;cursor:pointer;list-style:none}
.connection-details summary::-webkit-details-marker{display:none}
.connection-copy{display:flex;flex-direction:column;min-width:0;line-height:1.45}
.connection-copy strong{font-size:12px;font-weight:600;color:var(--ink)}
.connection-copy small{font-size:10.5px;color:var(--subtle);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.connection-groups{display:grid;gap:12px;padding:14px 2px 2px}
.connection-group{display:grid;grid-template-columns:1fr auto;gap:2px 10px;align-items:baseline}
.connection-group strong{font-size:11px;font-weight:500;color:var(--ink-2);overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.connection-group small{font:600 10.5px Barlow,system-ui;color:var(--subtle)}
.connection-group i{grid-column:1/-1;height:3px;border-radius:3px;background:linear-gradient(90deg,var(--accent-2),var(--highlight));transform-origin:left;transform:scaleX(var(--share));opacity:.75}
</style>
