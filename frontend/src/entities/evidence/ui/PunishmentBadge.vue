<script setup>
import {punishmentKind} from '../model/records.js'
defineProps({record:Object})
</script>
<template><span :class="['badge',punishmentKind(record.punishment)]">{{record.punishment}}</span><span v-if="(record.penalty_text)&&(record.penalty_text)!==record.punishment" class="duration-text">{{record.penalty_text}}</span></template>
