<script setup>
import {ref} from 'vue'
import {useSession} from '../../../shared/api/session.js'
import {useQuery} from '../model/query.js'
import QueryTable from './QueryTable.vue'
import SearchField from '../../../shared/ui/SearchField.vue'
const {api}=useSession(),{question,busy,status,answer,result,submit,cancel}=useQuery(api),input=ref()
const emit=defineEmits(['member','record'])
</script>
<template>
<section class="panel query-panel"><form id="query-form" @submit.prevent="submit"><SearchField id="query-input" v-model="question" label="问题或只读 SQL" maxlength="4000" placeholder="查询处罚档案" required/><div class="query-actions"><button class="button" type="button" id="query-cancel" :hidden="!busy" @click="cancel">停止</button><button class="button primary" id="query-submit" :disabled="busy">查询</button></div></form></section><p v-if="status" id="query-status" role="status">{{status}}</p><p v-if="answer" id="query-answer">{{answer}}</p><div id="query-results"><QueryTable v-for="(table,i) in result?.tables||[]" :key="result.as_of+'-'+i" :result="table" :index="i" @member="emit('member',$event)" @record="emit('record',$event)"/></div>
</template>
