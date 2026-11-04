<script setup>
import { computed, ref, shallowRef, watch } from 'vue'
import { useWorkspace } from '../../../entities/monitor/model/workspace.js'
import { useEvidence } from '../../../entities/evidence/model/state.js'
import RecordEditor from '../../../entities/evidence/ui/RecordEditor.vue'
import AppIcon from '../../../shared/ui/AppIcon.vue'
import { time, states, count } from '../../../shared/lib/format.js'
const props = defineProps({ active: Boolean, pending: Number, totals: Object, scene: Object })
const { api, status, notify, loadStatus } = useWorkspace(), { draft, records, load, loaded, interacting } = useEvidence()
const recent = shallowRef([]), editing = ref(false), batch = ref(false), editDraft = ref(null)
const metrics = computed(() => [
    { key: 'open', href: '#events', icon: 'inbox', tone: 'accent', label: '待人工核查', value: props.pending, hint: 'DS 已筛出，等你确认' },
    { key: 'bans', href: '#bans', icon: 'clock', tone: 'info', label: '当前禁言', value: props.totals.bans, hint: '仍在禁言期内的成员' },
    { key: 'risks', href: '#risks', icon: 'shield', tone: 'warn', label: '再犯预警', value: props.totals.risks, hint: '再次违规将升级处理' },
    { key: 'records', href: '#records', icon: 'folder', tone: 'highlight', label: '处罚档案', value: props.totals.records, hint: '累计留档的处理记录' },
])
async function refresh() { recent.value = await api('/api/cases?state=attention&resolution=open&limit=3&summary=true') }
function register(isBatch = false, value = null) { batch.value = isBatch; editDraft.value = value; editing.value = true }
async function consumeDraft() {
    if (!props.active || !draft.value) return
    if (!loaded.value) { try { await load() } catch { return } }
    const value = draft.value; if (!value) return; draft.value = null
    if (value.source && records.value.some(r => r.source === value.source)) { notify('这条线索已经登记过了'); location.hash = 'records'; return }
    register(false, value)
}
watch(() => props.active, active => { if (active) { consumeDraft() } else editing.value = false }, { immediate: true })
watch(draft, consumeDraft)
watch(editing, value => interacting.value = value)
async function saved({ source }) {
    if (!source?.startsWith('group-watch:')) return
    try { await api('/api/cases/' + encodeURIComponent(source.slice(12)) + '/decision', { resolution: 'confirmed' }); await loadStatus(); await refresh() }
    catch (e) { notify('档案已保存，但线索状态没有同步：' + e.message) }
}
defineExpose({ refresh })
</script>
<template>
    <div class="panel hero">
        <div class="hero-art" aria-hidden="true"></div>
        <div class="hero-copy">
            <span class="hero-kicker"><AppIcon name="sparkle"/>{{ scene?.name }} · {{ scene?.line }}</span>
            <h1>群管理工作台<span>。</span></h1>
            <p class="hero-summary" v-if="pending">有 <b>{{ count(pending) }}</b> 条线索等你核查<template v-if="totals.bans">，<b>{{ count(totals.bans) }}</b> 位成员仍在禁言中</template>。</p>
            <p class="hero-summary" v-else>暂时没有待核查线索<template v-if="totals.bans">，<b>{{ count(totals.bans) }}</b> 位成员仍在禁言中</template>。</p>
            <div class="hero-actions">
                <button id="quick-record" class="button primary" @click="register()">登记处理 <AppIcon name="arrow"/></button>
                <a v-if="pending" class="button ghost" href="#events">开始核查</a>
            </div>
        </div>
    </div>
    <nav class="metric-cards" aria-label="工作概况">
        <a v-for="metric in metrics" :key="metric.key" :href="metric.href" class="metric-card" :class="'tone-' + metric.tone">
            <span class="metric-icon"><AppIcon :name="metric.icon"/></span>
            <span class="metric-label">{{ metric.label }}</span>
            <strong :id="'metric-' + metric.key">{{ count(metric.value) }}</strong>
            <AppIcon class="metric-go" name="out"/>
        </a>
    </nav>
    <section class="panel recent-panel">
        <div class="section-heading">
            <div><h2>需要关注</h2><p>最近的待核查线索</p></div>
            <a class="text-link" href="#events">全部线索 <AppIcon name="arrow"/></a>
        </div>
        <div id="recent-cases">
            <a v-for="item in recent" :key="item.id" class="recent-row" href="#events">
                <span class="recent-avatar" aria-hidden="true">{{ [...(item.member_name || '?')][0] }}</span>
                <div class="row-copy">
                    <h3>{{ status?.policies[item.rule]?.[0] || item.rule }}</h3>
                    <p>{{ item.member_name }} · {{ item.group_name }} · {{ time(item.created) }}</p>
                </div>
                <span :class="['badge', item.state]">{{ states[item.state] || item.state }}</span>
                <AppIcon class="recent-go" name="arrow"/>
            </a>
            <div v-if="!recent.length" key="empty" class="empty-state">
                <div class="empty-symbol"><AppIcon name="check"/></div>
                <h3>暂时没有待办</h3>
                <p>新的可疑发言出现时，会先经过 DS 复核，再出现在这里。</p>
            </div>
        </div>
    </section>
    <div class="evidence-workspace">
        <RecordEditor v-if="editing" :open="editing" :batch="batch" :draft="editDraft" @close="editing = false"
            @saved="saved" />
    </div>
</template>
