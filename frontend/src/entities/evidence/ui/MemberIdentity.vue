<script setup>
import {computed} from 'vue'
import {useEvidence} from '../model/state.js'
import {useAvatar} from '../model/avatar.js'
const props=defineProps({record:Object,avatarOnly:Boolean}),emit=defineEmits(['open'])
const {profileFor,displayName,groups,groupLabel,view}=useEvidence(),profile=computed(()=>profileFor(props.record)),name=computed(()=>displayName(props.record))
const {source:avatar,failed,fail}=useAvatar(profile,view)
const nameHint=computed(()=>profile.value.nickname_status===1?'该条档案留存的昵称':profile.value.nickname_status===0?'昵称正在获取':'昵称获取失败，可手动重试')
</script>
<template>
<component :is="avatarOnly?'span':'button'" :class="avatarOnly?'':'member-button'" :type="avatarOnly?undefined:'button'" @click="emit('open',record.id||(record.record_ids||[])[0])"><span class="avatar" :class="{'blank-avatar':!name}" :title="['头像正在获取','头像已留存','头像获取失败'][profile.avatar_status]">{{[...name][0]}}<img v-if="avatar&&!failed" :key="avatar" :src="avatar" alt="" decoding="async" @error="fail"></span><span v-if="!avatarOnly"><strong :title="nameHint">{{name}}</strong><small v-if="record.member_id!==name">{{record.member_id||'未记账号'}}</small><small v-if="groups.length>1">{{groupLabel(record.group_id)}}</small></span></component>
</template>
<style scoped>
.member-button{display:flex;align-items:center;gap:12px;min-width:0;text-align:left}.member-button>.avatar{flex:none}.member-button>span:last-child{min-width:0}
.avatar.blank-avatar{background:#000}
</style>
