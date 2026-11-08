<script setup>
import {ref,computed,watch} from 'vue'
import {useWorkspace} from '../../../entities/monitor/model/workspace.js'
import PageHeading from '../../../shared/ui/PageHeading.vue'
import SettingsRow from '../../../shared/ui/SettingsRow.vue'
import SelectBox from '../../../shared/ui/SelectBox.vue'
const props=defineProps({active:Boolean})
const {api,status,notify,loadStatus}=useWorkspace()
const targets=ref([]),confidence=ref(.95),broadcastBusy=ref(false),broadcastFeedback=ref('')
const savedTargets=ref(''),broadcastDirty=computed(()=>JSON.stringify(targets.value.map(({id,kind})=>({id,kind})))!==savedTargets.value)
const recipients=ref([]),configured=ref(false),loaded=ref(false),dirty=ref(false),busy=ref(false),feedback=ref(''),failed=ref(false)
function changed(){dirty.value=true;feedback.value='有未保存的更改。';failed.value=false}
async function load(){if(loaded.value)return;const data=await api('/api/settings/notifications');configured.value=data.configured;recipients.value=(data.recipients||[]).map(r=>({...r,token:''}));targets.value=data.broadcast_targets||[];confidence.value=data.broadcast_confidence??.95;savedTargets.value=JSON.stringify(targets.value.map(({id,kind})=>({id,kind})));loaded.value=true}
watch(()=>props.active,async active=>{if(active)try{await load()}catch(e){feedback.value=e.message;failed.value=true}},{immediate:true})
async function save(){
 if(busy.value||!loaded.value)return
 if(recipients.value.some(r=>(!r.configured&&!r.token)||r.token&&!/^[\x21-\x7E]{8,256}$/.test(r.token))){feedback.value='Token 应为 8–256 位英文字符，不能含空格。';failed.value=true;return}
 busy.value=true;failed.value=false;feedback.value='正在保存…'
 try{await api('/api/settings/notifications',{recipients:recipients.value.map(({id,name,token})=>({id:id||'',name,token}))});dirty.value=false;loaded.value=false;await load();await loadStatus();feedback.value='';notify('通知设置已保存')}
 catch(e){feedback.value=e.message;failed.value=true}finally{busy.value=false}
}
async function test(){if(busy.value)return;if(dirty.value){feedback.value='请先保存，测试会使用已保存的配置。';failed.value=true;return}busy.value=true;failed.value=false;feedback.value='正在发送测试通知…';try{const data=await api('/api/settings/notifications/test',{});feedback.value=data.message+'。'}catch(e){feedback.value=e.message;failed.value=true}finally{busy.value=false}}
async function saveBroadcast(){if(broadcastBusy.value)return;broadcastBusy.value=true;broadcastFeedback.value='';try{const result=await api('/api/settings/broadcast',{targets:targets.value.map(({id,kind})=>({id:id.trim(),kind})),confidence:confidence.value});targets.value=result.targets;savedTargets.value=JSON.stringify(targets.value.map(({id,kind})=>({id,kind})));broadcastFeedback.value='';notify('通知目标已保存')}catch(e){broadcastFeedback.value=e.message}finally{broadcastBusy.value=false}}
async function testBroadcast(){
 if(broadcastBusy.value)return
 if(broadcastDirty.value){broadcastFeedback.value='请先保存，测试会使用已保存的目标。';return}
 broadcastBusy.value=true;broadcastFeedback.value='正在发送测试通知…'
 try{const result=await api('/api/settings/broadcast/test',{});broadcastFeedback.value=result.message}
 catch(e){broadcastFeedback.value=e.message}finally{broadcastBusy.value=false}
}
</script>
<template>
<PageHeading eyebrow="NOTIFY" title="通知"/><div class="settings-grid"><section class="panel settings-panel"><div class="section-heading"><div><h2>PushPlus 推送</h2><p>每位接收人一个 Token，最多 10 人</p></div></div><form id="notification-form" @submit.prevent="save"><SettingsRow v-for="(recipient,i) in recipients" :key="recipient.id||i" pair><label><span class="sr-only">接收人注释</span><input v-model="recipient.name" maxlength="100" placeholder="接收人备注" :disabled="busy||!loaded" @input="changed"></label><label><span class="sr-only">PushPlus Token</span><input v-model="recipient.token" type="password" autocomplete="new-password" maxlength="256" spellcheck="false" :placeholder="recipient.configured?'已保存，留空则不修改':'粘贴 PushPlus Token'" :disabled="busy||!loaded" @input="changed"></label><button type="button" class="icon-button" :disabled="busy" :aria-label="'移除接收人 '+(recipient.name||i+1)" @click="recipients.splice(i,1);changed()">×</button></SettingsRow><div class="recipient-tools"><button v-if="recipients.length<10" type="button" class="text-link" :disabled="busy||!loaded" @click="recipients.push({id:'',name:'',token:'',configured:false});changed()">＋ 添加接收人</button></div><div class="form-actions"><button class="button primary" type="submit" id="save-notifications" :disabled="busy||!loaded">保存</button><button class="button" type="button" id="test-notification" :disabled="busy||!loaded" @click="test">发一条测试</button></div><p v-if="feedback" id="save-feedback" class="form-feedback" :class="{failed}" role="status" aria-live="polite">{{feedback}}</p></form></section><section class="panel settings-panel"><div class="section-heading"><div><h2>QQ 高疑似线索</h2><p>DS 判定违规、置信度不低于 {{Math.round(confidence*100)}}% 的线索会发到这里</p></div></div><form @submit.prevent="saveBroadcast"><SettingsRow v-for="(target,i) in targets" :key="i"><label><span class="sr-only">目标类型</span><SelectBox v-model="target.kind" :options="[{value:'auto',label:'自动核对'},{value:'group',label:'群聊'},{value:'private',label:'联系人'}]" :disabled="broadcastBusy" @change="target.name=''"/></label><label><span class="sr-only">QQ 或群号</span><input v-model="target.id" @input="target.name=''" :disabled="broadcastBusy" placeholder="QQ 或群号" pattern="[1-9][0-9]{4,11}" required></label><button class="icon-button" type="button" :disabled="broadcastBusy" aria-label="移除此目标" @click="targets.splice(i,1)">×</button><small v-if="target.name">{{target.name}}</small></SettingsRow><button v-if="targets.length<10" class="text-link" type="button" :disabled="broadcastBusy" @click="targets.push({kind:'auto',id:'',name:''})">＋ 添加群聊或联系人</button><div class="form-actions"><button class="button primary" :disabled="broadcastBusy||!loaded">保存</button><button class="button" type="button" :disabled="broadcastBusy||!loaded||!targets.length" @click="testBroadcast">发一条测试</button></div><p v-if="broadcastFeedback" class="form-feedback" role="status">{{broadcastFeedback}}</p></form></section></div>
</template>

<style scoped>
.recipient-tools{display:flex;justify-content:space-between;gap:14px}.settings-grid{align-items:start}.settings-panel .field input[type=number]{max-width:130px}
</style>
