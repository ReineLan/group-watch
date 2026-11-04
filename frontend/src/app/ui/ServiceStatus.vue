<script setup>
import {useWorkspace} from '../../entities/monitor/model/workspace.js'
import {count,time} from '../../shared/lib/format.js'
const {status}=useWorkspace()
</script>
<template>
<details class="service-detail"><summary>监控状态 <span id="sidebar-status-inline"></span></summary><div id="group-list"><div v-for="(group,i) in status?.activity||[]" :key="group.group_id" class="group-row"><span class="group-avatar">{{String(i+1).padStart(2,'0')}}</span><div><strong>群 {{group.group_id}}</strong><small>最近消息 {{time(group.last_message)}}</small></div><span>{{count(group.messages)}} 条 / 24h</span></div></div><p><span class="dot" id="connection-dot"></span><span id="connection-text">{{status?.connected?'SnowLuma 已连接 · 最近接收 '+time(status.last_message):(status?.qq_port?'等待 SnowLuma 连接，请检查 '+status.qq_port+' 端口':'请配置 SnowLuma 监听端口')}}</span></p><p>等待复核 <b id="metric-pending">{{count(status?.counts.pending)}}</b> · 24 小时消息 <b id="metric-messages">{{count(status?.activity.reduce((n,g)=>n+g.messages,0))}}</b> · AI <b id="metric-calls">{{count(status?.calls_hour)}}</b> / <span id="metric-budget">每小时上限 {{status?.call_limit}} 次</span></p><p>通知 <span class="badge" id="push-badge">{{!status?.push_configured?'待配置':status.push_enabled?'已启用':'已暂停'}}</span></p><small>人工核对后登记；本工作台不执行 QQ 处罚。</small></details>
</template>
