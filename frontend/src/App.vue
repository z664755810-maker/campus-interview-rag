<script setup>
import { ref, onMounted, computed } from 'vue'
import { getStats, getAnalytics, getUsage, deleteBySource, clearLibrary } from './api.js'
import UploadPanel from './components/UploadPanel.vue'
import ChatPanel from './components/ChatPanel.vue'
import SubjectBrowser from './components/SubjectBrowser.vue'
import InterviewMode from './components/InterviewMode.vue'

const MODE_CHAT = 'chat'
const MODE_BROWSE = 'browse'
const MODE_INTERVIEW = 'interview'
const mode = ref(MODE_CHAT)

const uploads = ref([])
const libraryCount = ref(0)
const analytics = ref({
  total_chunks: 0,
  source_count: 0,
  subject_count: 0,
  top_k_default: 5,
  business_modes: 4,
  format_support: 14,
  top_subjects: [],
})

const overviewCards = computed(() => [
  { label: '知识覆盖', value: `${analytics.value.subject_count || 0} 个主题`, tone: 'blue' },
  { label: '知识片段', value: `${analytics.value.total_chunks || libraryCount.value || 0} 条`, tone: 'green' },
  { label: '业务模式', value: `${analytics.value.business_modes || 4} 类`, tone: 'orange' },
  { label: '检索上下文', value: `Top-k ${analytics.value.top_k_default || 5}`, tone: 'purple' },
])

function onUploaded(payload) {
  const idx = uploads.value.findIndex((u) => u.source === payload.source)
  if (idx !== -1) {
    libraryCount.value -= uploads.value[idx].ingested
    uploads.value.splice(idx, 1)
  }
  uploads.value.unshift(payload)
  libraryCount.value += payload.ingested
  refreshStats()
}

async function refreshStats() {
  try {
    const s = await getStats()
    libraryCount.value = s.count || 0
    uploads.value = (s.sources || []).map((x) => ({
      source: x.source,
      ingested: x.chunks,
    }))
  } catch (e) {
    console.warn('题库状态拉取失败：', e.message)
  }

  try {
    const a = await getAnalytics()
    analytics.value = a || analytics.value
  } catch (e) {
    console.warn('运营指标拉取失败：', e.message)
  }
}

async function handleDelete(source) {
  if (!confirm(`确定要删除「${source}」吗？该操作不可撤销。`)) return
  try {
    await deleteBySource(source)
    await refreshStats()
  } catch (e) {
    alert('删除失败：' + e.message)
  }
}

async function handleClearAll() {
  if (!confirm('⚠️ 这会清空整个知识库，确定吗？\n此操作不可撤销。')) return
  if (!confirm('再确认一次：真的要清空所有文档吗？')) return
  try {
    await clearLibrary()
    await refreshStats()
  } catch (e) {
    alert('清空失败：' + e.message)
  }
}

const usage = ref({ used: 0, limit: 30, remaining: 30, window_seconds: 60 })
const usagePct = computed(() =>
  usage.value.limit > 0 ? Math.min(100, Math.round((usage.value.used / usage.value.limit) * 100)) : 0
)
const usageColor = computed(() => {
  if (usagePct.value < 60) return '#3fb950'
  if (usagePct.value < 85) return '#d29922'
  return '#f85149'
})

async function refreshUsage() {
  try {
    usage.value = await getUsage()
  } catch (e) {
    // ignore
  }
}

onMounted(async () => {
  await Promise.all([refreshStats(), refreshUsage()])
  setInterval(refreshUsage, 10000)
})

const chatRef = ref(null)
function forwardToChat(question, modeName = 'answer') {
  mode.value = MODE_CHAT
  setTimeout(() => {
    if (chatRef.value && chatRef.value.fillQuestion) {
      chatRef.value.fillQuestion(question, modeName)
    }
  }, 50)
}

const subjectRef = ref(null)
function switchToBrowse() {
  mode.value = MODE_BROWSE
  setTimeout(() => {
    if (subjectRef.value && subjectRef.value.load) {
      subjectRef.value.load()
    }
  }, 50)
}
</script>

<template>
  <div class="app-shell">
    <header class="topbar">
      <div class="brand-block">
        <div class="brand-mark">AI</div>
        <div>
          <p class="eyebrow">企业知识库与运营协同平台</p>
          <h1>企业知识库智能助手</h1>
        </div>
      </div>

      <div class="topbar-actions">
        <div class="usage-box" :title="`后端按 IP 限流，60 秒内最多 ${usage.limit} 次`">
          <div class="usage-label">
            <span>接口配额</span>
            <span class="usage-num">
              <b :style="{ color: usageColor }">{{ usage.remaining }}</b>
              <span class="dim">/ {{ usage.limit }}</span>
            </span>
          </div>
          <div class="usage-bar">
            <div class="usage-fill" :style="{ width: usagePct + '%', background: usageColor }"></div>
          </div>
        </div>
        <div class="lib-stat">知识库已索引 <b>{{ libraryCount }}</b> 条</div>
      </div>
    </header>

    <section class="kpis">
      <div v-for="card in overviewCards" :key="card.label" class="kpi-card" :class="card.tone">
        <span>{{ card.label }}</span>
        <strong>{{ card.value }}</strong>
      </div>
    </section>

    <section v-if="analytics.top_subjects.length" class="insights">
      <div class="insight-header">
        <h2>知识主题分布</h2>
        <span>覆盖重点业务领域</span>
      </div>
      <div class="subject-list">
        <div v-for="item in analytics.top_subjects" :key="item.name" class="subject-pill">
          <span>{{ item.name }}</span>
          <strong>{{ item.count }}</strong>
        </div>
      </div>
    </section>

    <main class="layout">
      <aside class="sidebar">
        <UploadPanel @uploaded="onUploaded" />

        <div class="lib-list" v-if="uploads.length">
          <div class="lib-head">
            <h3>已入库文档</h3>
            <button class="clear-btn" @click="handleClearAll" title="清空知识库">🗑 清空</button>
          </div>
          <ul>
            <li v-for="u in uploads" :key="u.source">
              <span class="dot"></span>
              <span class="src" :title="u.source">{{ u.source }}</span>
              <em>{{ u.ingested }} 条</em>
              <button class="del-btn" @click="handleDelete(u.source)" title="删除该文档">✕</button>
            </li>
          </ul>
        </div>

        <div class="mode-switch">
          <h3>工作台</h3>
          <button :class="{ active: mode === MODE_CHAT }" @click="mode = MODE_CHAT">
            💬 智能问答
          </button>
          <button :class="{ active: mode === MODE_BROWSE }" @click="switchToBrowse">
            🗂️ 知识地图
          </button>
          <button :class="{ active: mode === MODE_INTERVIEW }" @click="mode = MODE_INTERVIEW">
            🧭 流程演练
          </button>
        </div>
      </aside>

      <section class="workspace">
        <ChatPanel v-show="mode === MODE_CHAT" ref="chatRef" :has-library="libraryCount > 0" />
        <SubjectBrowser ref="subjectRef" v-show="mode === MODE_BROWSE" :has-library="libraryCount > 0" @ask="forwardToChat" />
        <InterviewMode v-show="mode === MODE_INTERVIEW" :has-library="libraryCount > 0" />
      </section>
    </main>
  </div>
</template>

<style>
* { box-sizing: border-box; }
html, body, #app { height: 100%; margin: 0; }
body {
  margin: 0;
  background: radial-gradient(circle at top, #13243f 0%, #0b1220 30%, #090d16 100%);
  color: #e6edf7;
  font-family: -apple-system, "Segoe UI", Roboto, "PingFang SC", "Microsoft YaHei", sans-serif;
}
button, input, textarea { font: inherit; }
.app-shell {
  min-height: 100vh;
  padding: 20px 22px 24px;
}
.topbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 16px 18px 20px;
  border: 1px solid rgba(148, 163, 184, 0.18);
  border-radius: 18px;
  background: rgba(15, 23, 42, 0.8);
  backdrop-filter: blur(14px);
}
.brand-block {
  display: flex;
  align-items: center;
  gap: 14px;
}
.brand-mark {
  display: grid;
  place-items: center;
  width: 42px;
  height: 42px;
  border-radius: 12px;
  background: linear-gradient(135deg, #60a5fa, #22d3ee);
  color: #03151d;
  font-weight: 800;
}
.eyebrow {
  margin: 0 0 3px;
  color: #78d7ff;
  font-size: 11px;
  letter-spacing: 0.12em;
  text-transform: uppercase;
}
.topbar h1 {
  margin: 0;
  font-size: clamp(1.4rem, 2vw, 2.2rem);
  line-height: 1.2;
}
.topbar-actions {
  display: flex;
  align-items: center;
  gap: 16px;
}
.lib-stat, .usage-box {
  background: rgba(15, 23, 42, 0.74);
  border: 1px solid rgba(148, 163, 184, 0.18);
  border-radius: 12px;
}
.lib-stat {
  padding: 10px 14px;
  color: #cbd5e1;
  font-size: 13px;
}
.usage-box {
  min-width: 220px;
  padding: 9px 12px;
}
.usage-label {
  display: flex;
  justify-content: space-between;
  align-items: center;
  color: #cbd5e1;
  font-size: 12px;
  margin-bottom: 6px;
}
.usage-num { display: flex; align-items: baseline; gap: 4px; }
.usage-num b { font-size: 16px; }
.dim { color: #94a3b8; }
.usage-bar {
  width: 100%;
  height: 8px;
  background: rgba(148, 163, 184, 0.18);
  border-radius: 999px;
  overflow: hidden;
}
.usage-fill {
  height: 100%;
  border-radius: inherit;
}
.kpis {
  display: grid;
  grid-template-columns: repeat(4, minmax(160px, 1fr));
  gap: 14px;
  margin-top: 18px;
}
.kpi-card {
  padding: 18px 18px 16px;
  border-radius: 16px;
  border: 1px solid rgba(148, 163, 184, 0.18);
  background: rgba(15, 23, 42, 0.8);
}
.kpi-card span {
  display: block;
  color: #94a3b8;
  font-size: 12px;
  margin-bottom: 10px;
}
.kpi-card strong {
  font-size: 26px;
  font-weight: 700;
}
.kpi-card.blue { box-shadow: inset 0 0 0 1px rgba(96, 165, 250, 0.2); }
.kpi-card.green { box-shadow: inset 0 0 0 1px rgba(74, 222, 128, 0.2); }
.kpi-card.orange { box-shadow: inset 0 0 0 1px rgba(251, 146, 60, 0.2); }
.kpi-card.purple { box-shadow: inset 0 0 0 1px rgba(168, 85, 247, 0.2); }
.insights {
  margin-top: 18px;
  padding: 14px 16px 16px;
  border-radius: 16px;
  border: 1px solid rgba(148, 163, 184, 0.18);
  background: rgba(15, 23, 42, 0.75);
}
.insight-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 10px;
  margin-bottom: 10px;
}
.insight-header h2 {
  margin: 0;
  font-size: 14px;
  color: #e2e8f0;
}
.insight-header span {
  color: #94a3b8;
  font-size: 11px;
}
.subject-list {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}
.subject-pill {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  border-radius: 999px;
  background: rgba(59, 130, 246, 0.12);
  border: 1px solid rgba(96, 165, 250, 0.2);
  color: #dbeafe;
  font-size: 12px;
}
.subject-pill strong {
  color: #f8fafc;
  font-size: 11px;
}
.layout {
  display: grid;
  grid-template-columns: 330px minmax(0, 1fr);
  gap: 18px;
  margin-top: 18px;
  min-height: 0;
}
.sidebar {
  display: flex;
  flex-direction: column;
  gap: 16px;
}
.workspace {
  min-height: 0;
  background: rgba(15, 23, 42, 0.7);
  border: 1px solid rgba(148, 163, 184, 0.18);
  border-radius: 18px;
  overflow: hidden;
}
.lib-list, .mode-switch {
  background: rgba(15, 23, 42, 0.8);
  border: 1px solid rgba(148, 163, 184, 0.18);
  border-radius: 16px;
  padding: 16px;
}
.lib-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 10px;
}
.lib-head h3, .mode-switch h3 {
  margin: 0;
  font-size: 14px;
  color: #e2e8f0;
}
.clear-btn, .del-btn {
  background: transparent;
  border: none;
  cursor: pointer;
}
.clear-btn {
  color: #fda4af;
  font-size: 12px;
}
.lib-list ul {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.lib-list li {
  display: flex;
  align-items: center;
  gap: 8px;
  background: rgba(15, 23, 42, 0.9);
  padding: 8px 10px;
  border-radius: 10px;
  border: 1px solid rgba(148, 163, 184, 0.12);
}
.dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #60a5fa;
  flex-shrink: 0;
}
.src {
  flex: 1;
  min-width: 0;
  color: #cbd5e1;
  font-size: 12px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.lib-list em {
  color: #94a3b8;
  font-style: normal;
  font-size: 11px;
}
.del-btn {
  color: #94a3b8;
}
.mode-switch { display: flex; flex-direction: column; gap: 10px; }
.mode-switch button {
  width: 100%;
  padding: 11px 12px;
  border: 1px solid rgba(148, 163, 184, 0.18);
  border-radius: 10px;
  background: rgba(15, 23, 42, 0.9);
  color: #dbeafe;
  cursor: pointer;
  text-align: left;
  transition: 0.15s ease;
}
.mode-switch button.active {
  background: linear-gradient(135deg, rgba(59, 130, 246, 0.28), rgba(34, 211, 238, 0.12));
  border-color: rgba(96, 165, 250, 0.7);
}
@media (max-width: 980px) {
  .layout { grid-template-columns: 1fr; }
  .kpis { grid-template-columns: repeat(2, minmax(140px, 1fr)); }
  .topbar { flex-direction: column; align-items: flex-start; }
  .topbar-actions { width: 100%; justify-content: space-between; }
}
</style>
