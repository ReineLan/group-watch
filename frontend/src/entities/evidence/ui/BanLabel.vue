<script setup>
import {fmt} from '../../../shared/lib/format.js'
defineProps({ban:Object})
</script>
<template><template v-if="ban"><span class="badge" :class="{mute:['进行中','永久禁言'].includes(ban.status)}">{{ban.status==='进行中'?'剩余 '+ban.remaining_days+' 天':ban.status}}</span><small class="ban-range">{{fmt(ban.start)}}<br>至 {{ban.end?fmt(ban.end):ban.status==='永久禁言'?'永久':'未注明'}}</small></template></template>
