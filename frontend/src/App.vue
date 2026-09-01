<script setup>
import { ref, onMounted, computed } from 'vue'
import { getApiKey, setApiKey, getStats, getUsage, deleteBySource, clearLibrary } from './api.js'
import UploadPanel from './components/UploadPanel.vue'
import ChatPanel from './components/ChatPanel.vue'
import SubjectBrowser from './components/SubjectBrowser.vue'
import InterviewMode from './components/InterviewMode.vue'

// ── 全局状态 ──────────────────────────────────────────
const MODE_CHAT = 'chat'         // 提问
const MODE_BROWSE = 'browse'     // 专题刷题
const MODE_INTERVIEW = 'interview' // 模拟面试
const mode = ref(MODE_CHAT)

const uploads = ref([])          // 已上传文档列表
const libraryCount = ref(0)      // 总段数

// onUploaded 按 source 去重：后端是 upsert（幂等覆盖），
// 若前端无脑累加，重复载入同一份示例题库会让计数虚高，与实际库内条数对不上。
function onUploaded(payload) {
  const idx = uploads.value.findIndex((u) => u.source === payload.source)
  if (idx !== -1) {
    libraryCount.value -= uploads.value[idx].ingested // 先扣掉旧值
    uploads.value.splice(idx, 1)
  }
  uploads.value.unshift(payload)
  libraryCount.value += payload.ingested
  // 同步后端真实状态，避免本地计数漂移
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
}

// ── 段 A 改 #2：题库管理 ────────────────────────────────
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
  if (!confirm('⚠️ 这会清空整个题库（含示例题库），确定吗？\n此操作不可撤销。')) return
  if (!confirm('再确认一次：真的要清空所有题目吗？')) return
  try {
    await clearLibrary()
    await refreshStats()
  } catch (e) {
    alert('清空失败：' + e.message)
  }
}

// ── 段 A 改 #3：API Key 装饰化 ──────────────────────────
// 思路：保留后端鉴权中间件（防滥用者），但前端不再让用户改一个「所有人都知道」的 key；
// 改为显示「当前接口配额 + 状态」指示器，体现「有鉴权 + 有限流」的中台能力。
const apiKeyReady = ref(!!getApiKey()) // 后端如果配了 key，前端必带；没配就放空
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
    // /api/usage 在没有 API_KEYS 的环境也能走通（已在 RATE_LIMIT_EXEMPT 里）
  }
}

onMounted(async () => {
  await Promise.all([refreshStats(), refreshUsage()])
  // 配额每 10 秒拉一次，让指示器接近实时
  setInterval(refreshUsage, 10000)
})

// ── 段 B：跨面板通信 ──────────────────────────────────
// 专题刷题面板的"让 RAG 详细讲解"按钮会把题目传回这里，自动切到问答面板
const chatRef = ref(null)
function forwardToChat(question) {
  mode.value = MODE_CHAT
  // 等 DOM 更新后调用 ChatPanel 的 fillQuestion（这里用 nextTick 简化处理）
  setTimeout(() => {
    if (chatRef.value && chatRef.value.fillQuestion) {
      chatRef.value.fillQuestion(question)
    }
  }, 50)
}

// 段 B-修：切到「专题刷题」时强制 reload（onMounted 只触发一次，
// 用户先停在 chat 等 stats 加载完再切到 browse，需要再 load 一次才能看见题）
const subjectRef = ref(null)
function switchToBrowse() {
  mode.value = MODE_BROWSE
  // 等 v-show 把组件显示出来再 load（保险起见用 50ms 而非 nextTick）
  setTimeout(() => {
    if (subjectRef.value && subjectRef.value.load) {
      subjectRef.value.load()
    }
  }, 50)
}
</script>

<template>
  <div class="app">
    <header class="topbar">
      <div class="brand">
        <span class="logo">📚</span>
        <div>
          <h1>校招软开面试题库 · RAG 问答</h1>
          <p class="sub">上传题库 → 检索增强生成 → 答案带引用溯源</p>
        </div>
      </div>
      <div class="right">
        <!-- 段 A 改 #3：限流配额指示器（替代原来的 API Key 输入框） -->
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
        <div class="lib-stat">
          题库已索引 <b>{{ libraryCount }}</b> 段
        </div>
      </div>
    </header>

    <main class="layout">
      <aside class="sidebar">
        <UploadPanel @uploaded="onUploaded" />

        <div class="lib-list" v-if="uploads.length">
          <div class="lib-head">
            <h3>已上传文档</h3>
            <button class="clear-btn" @click="handleClearAll" title="清空整个题库">🗑 清空</button>
          </div>
          <ul>
            <li v-for="(u, i) in uploads" :key="u.source">
              <span class="dot"></span>
              <span class="src" :title="u.source">{{ u.source }}</span>
              <em>{{ u.ingested }} 段</em>
              <button class="del-btn" @click="handleDelete(u.source)" title="删除该文档">✕</button>
            </li>
          </ul>
        </div>

        <!-- 模式切换 -->
        <div class="mode-switch">
          <h3>功能面板</h3>
          <button :class="{ active: mode === MODE_CHAT }" @click="mode = MODE_CHAT">
            💬 问答
          </button>
          <button :class="{ active: mode === MODE_BROWSE }" @click="switchToBrowse">
            📖 专题刷题
          </button>
          <button :class="{ active: mode === MODE_INTERVIEW }" @click="mode = MODE_INTERVIEW">
            🎤 模拟面试
          </button>
        </div>
      </aside>

      <section class="chat-area">
        <ChatPanel
          v-show="mode === MODE_CHAT"
          ref="chatRef"
          :has-library="libraryCount > 0"
        />
        <SubjectBrowser
          ref="subjectRef"
          v-show="mode === MODE_BROWSE"
          :has-library="libraryCount > 0"
          @ask="forwardToChat"
        />
        <InterviewMode
          v-show="mode === MODE_INTERVIEW"
          :has-library="libraryCount > 0"
        />
      </section>
    </main>
  </div>
</template>

<style>
* { box-sizing: border-box; }
html, body, #app { height: 100%; margin: 0; }
body {
  background: #0d1117;
  color: #c9d1d9;
  font-family: -apple-system, "Segoe UI", Roboto, "PingFang SC", "Microsoft YaHei", sans-serif;
}
.app { display: flex; flex-direction: column; height: 100vh; }
.topbar {
  display: flex; align-items: center; justify-content: space-between;
  padding: 14px 24px; background: #161b22; border-bottom: 1px solid #30363d;
  gap: 16px;
}
.brand { display: flex; align-items: center; gap: 12px; min-width: 0; }
.brand .logo { font-size: 28px; }
.topbar h1 { font-size: 18px; margin: 0; color: #f0f6fc; }
.topbar .sub { margin: 2px 0 0; font-size: 12px; color: #8b949e; }
.right { display: flex; align-items: center; gap: 20px; flex-shrink: 0; }

/* ── 段 A 改 #3：限流配额指示器 ── */
.usage-box {
  display: flex; flex-direction: column; gap: 4px;
  min-width: 130px; padding: 6px 10px;
  background: #0d1117; border: 1px solid #30363d; border-radius: 6px;
}
.usage-label { display: flex; align-items: baseline; justify-content: space-between; gap: 8px; font-size: 11px; color: #8b949e; }
.usage-num { font-size: 13px; }
.usage-num b { font-size: 15px; }
.usage-num .dim { color: #6e7681; margin-left: 2px; }
.usage-bar { height: 3px; background: #21262d; border-radius: 2px; overflow: hidden; }
.usage-fill { height: 100%; transition: width 0.4s, background 0.4s; }

.lib-stat { font-size: 13px; color: #8b949e; white-space: nowrap; }
.lib-stat b { color: #58a6ff; font-size: 16px; }

.layout { flex: 1; display: flex; min-height: 0; }
.sidebar {
  width: 320px; padding: 20px; border-right: 1px solid #30363d;
  overflow-y: auto; background: #0d1117; display: flex; flex-direction: column; gap: 20px;
}
.chat-area { flex: 1; min-width: 0; display: flex; position: relative; }
.chat-area > * { position: absolute; inset: 0; }

.lib-list { background: transparent; }
.lib-head { display: flex; align-items: center; justify-content: space-between; margin-bottom: 10px; }
.lib-list h3 { font-size: 13px; color: #8b949e; margin: 0; }
.clear-btn {
  background: transparent; border: 1px solid #30363d; color: #8b949e;
  padding: 3px 8px; border-radius: 4px; font-size: 11px; cursor: pointer; font-family: inherit;
}
.clear-btn:hover { color: #f85149; border-color: #f85149; }
.lib-list ul { list-style: none; padding: 0; margin: 0; }
.lib-list li {
  display: flex; align-items: center; gap: 8px; padding: 8px 10px;
  background: #161b22; border: 1px solid #30363d; border-radius: 8px;
  font-size: 13px; margin-bottom: 8px;
}
.lib-list li .dot { width: 8px; height: 8px; border-radius: 50%; background: #3fb950; flex-shrink: 0; }
.lib-list li .src {
  flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
  color: #c9d1d9; font-size: 12px;
}
.lib-list li em { color: #8b949e; font-style: normal; font-size: 11px; flex-shrink: 0; }
.del-btn {
  background: transparent; border: none; color: #6e7681;
  font-size: 14px; cursor: pointer; padding: 0 4px; line-height: 1;
}
.del-btn:hover { color: #f85149; }

.mode-switch { display: flex; flex-direction: column; gap: 6px; padding-top: 4px; border-top: 1px solid #30363d; }
.mode-switch h3 { font-size: 13px; color: #8b949e; margin: 8px 0; }
.mode-switch button {
  background: #0d1117; border: 1px solid #30363d; color: #c9d1d9;
  padding: 9px 12px; border-radius: 8px; font-size: 13px; cursor: pointer;
  text-align: left; font-family: inherit;
}
.mode-switch button:hover { border-color: #58a6ff; }
.mode-switch button.active {
  background: #1f6feb33; border-color: #1f6feb; color: #58a6ff; font-weight: 600;
}
</style>
