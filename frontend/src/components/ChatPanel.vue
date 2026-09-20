<script setup>
import { ref, nextTick } from 'vue'
import { postJson } from '../api.js'

const props = defineProps({ hasLibrary: Boolean })

const question = ref('')
const loading = ref(false)
const error = ref('')
const chats = ref([])
const activeMode = ref('answer')

const MODE_OPTIONS = [
  { id: 'answer', label: '知识问答' },
  { id: 'summary', label: '结论摘要' },
  { id: 'action_items', label: '行动清单' },
  { id: 'risk_check', label: '风险审查' },
]

const presets = {
  answer: [
    '请解释客户退款政策的审批链路。',
    '新员工入职流程需要哪些步骤？',
  ],
  summary: [
    '总结这份 SOP 对团队日常运营的关键影响。',
    '整合这批会议纪要里的关键结论和待办。',
  ],
  action_items: [
    '根据文档提出需要立即执行的动作项。',
    '帮我整理这次变更的执行清单和验收标准。',
  ],
  risk_check: [
    '请检查文档中是否存在合规和交付风险。',
    '识别这份流程可能的异常点与控制建议。',
  ],
}

const MIN_ROWS = 3
const MAX_ROWS = 8
const LINE_PX = 22
const textareaRef = ref(null)

function autoResize() {
  const el = textareaRef.value
  if (!el) return
  el.style.height = 'auto'
  el.style.height = Math.min(el.scrollHeight, MAX_ROWS * LINE_PX) + 'px'
}

async function send() {
  const q = question.value.trim()
  if (!q || loading.value) return
  loading.value = true
  error.value = ''
  try {
    const data = await postJson('/api/ask', { query: q, top_k: 5, mode: activeMode.value })
    chats.value.push({
      question: q,
      answer: data.answer,
      citations: data.citations || [],
      expanded: (data.citations || []).map(() => false),
      mode: data.mode || activeMode.value,
    })
    question.value = ''
    await nextTick()
    autoResize()
  } catch (e) {
    error.value = e.message || '提问出错'
  } finally {
    loading.value = false
  }
}

function toggle(chat, i) {
  chat.expanded[i] = !chat.expanded[i]
}

function onKey(e) {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault()
    send()
  }
}

defineExpose({
  fillQuestion(q, selectedMode = 'answer') {
    question.value = q
    activeMode.value = selectedMode
    nextTick(() => autoResize())
  },
})
</script>

<template>
  <div class="chat-panel">
    <div class="chat-header">
      <div>
        <h2>智能问答</h2>
        <p>面向政策、流程、FAQ 和运营文档的企业知识检索</p>
      </div>
    </div>

    <div v-if="!hasLibrary" class="warn">
      ⚠️ 当前知识库为空，请先在左侧上传政策、SOP、FAQ 或会议纪要等文档。
    </div>

    <div v-else class="mode-row">
      <button
        v-for="modeItem in MODE_OPTIONS"
        :key="modeItem.id"
        :class="{ active: activeMode === modeItem.id }"
        @click="activeMode = modeItem.id"
      >
        {{ modeItem.label }}
      </button>
    </div>

    <div v-if="hasLibrary" class="preset-row">
      <button
        v-for="item in presets[activeMode]"
        :key="item"
        class="preset"
        @click="question = item"
      >
        {{ item }}
      </button>
    </div>

    <div class="messages" v-if="hasLibrary">
      <div v-for="(c, idx) in chats" :key="idx" class="msg">
        <div class="q"><span class="tag">Q</span>{{ c.question }}</div>
        <div class="a">{{ c.answer }}</div>

        <div v-if="c.citations.length" class="cites">
          <div class="cites-head">📚 引用出处（点击展开原文）</div>
          <div v-for="(cit, i) in c.citations" :key="i" class="cite">
            <button class="cite-head" @click="toggle(c, i)">
              <span class="badge">[{{ cit.index }}]</span>
              <span class="cit-subject">{{ cit.subject }}</span>
              <span class="cit-title">{{ cit.title }}</span>
              <span class="cit-src">{{ cit.source }}</span>
              <span class="toggle">{{ c.expanded[i] ? '收起 ▲' : '展开 ▼' }}</span>
            </button>
            <pre v-if="c.expanded[i]" class="cite-body">{{ cit.content }}</pre>
          </div>
        </div>
      </div>
    </div>

    <div class="composer">
      <textarea
        ref="textareaRef"
        v-model="question"
        @input="autoResize"
        @keydown="onKey"
        :placeholder="`例如：请解释售后退款审批链路\n支持多行输入（Enter 发送，Shift+Enter 换行）`"
        :rows="MIN_ROWS"
        :disabled="loading || !hasLibrary"
      ></textarea>
      <button :disabled="loading || !hasLibrary" @click="send">
        {{ loading ? '生成中…' : '提交' }}
      </button>
    </div>
    <p v-if="error" class="err">{{ error }}</p>
  </div>
</template>

<style scoped>
.chat-panel {
  display: flex;
  flex-direction: column;
  height: 100%;
  padding: 20px 24px 18px;
}
.chat-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 14px;
}
.chat-header h2 {
  margin: 0;
  font-size: 15px;
  color: #f0f6fc;
}
.chat-header p {
  margin: 4px 0 0;
  color: #8b949e;
  font-size: 12px;
}
.warn {
  background: rgba(250, 204, 21, 0.08);
  border: 1px solid rgba(250, 204, 21, 0.38);
  color: #facc15;
  padding: 12px 16px;
  border-radius: 10px;
  font-size: 13px;
  margin-bottom: 16px;
}
.mode-row {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 12px;
}
.mode-row button {
  border: 1px solid rgba(148, 163, 184, 0.22);
  background: rgba(15, 23, 42, 0.7);
  color: #dbeafe;
  border-radius: 999px;
  padding: 7px 12px;
  cursor: pointer;
}
.mode-row button.active {
  background: linear-gradient(135deg, rgba(59, 130, 246, 0.25), rgba(34, 211, 238, 0.15));
  border-color: rgba(96, 165, 250, 0.7);
}
.preset-row {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 16px;
}
.preset {
  border: 1px dashed rgba(148, 163, 184, 0.33);
  background: transparent;
  color: #cbd5e1;
  border-radius: 999px;
  padding: 6px 10px;
  cursor: pointer;
  font-size: 12px;
}
.messages {
  flex: 1;
  overflow-y: auto;
  padding-right: 6px;
}
.msg {
  background: rgba(15, 23, 42, 0.76);
  border: 1px solid rgba(148, 163, 184, 0.16);
  border-radius: 12px;
  padding: 14px 16px;
  margin-bottom: 16px;
}
.q {
  font-weight: 600;
  color: #e2e8f0;
  margin-bottom: 8px;
}
.q .tag {
  display: inline-block;
  background: linear-gradient(135deg, #2563eb, #38bdf8);
  color: white;
  font-size: 11px;
  border-radius: 4px;
  padding: 1px 7px;
  margin-right: 8px;
}
.a {
  color: #dbeafe;
  line-height: 1.8;
  white-space: pre-wrap;
  font-size: 14px;
}
.cites { margin-top: 12px; border-top: 1px dashed rgba(148, 163, 184, 0.22); padding-top: 10px; }
.cites-head { font-size: 12px; color: #8b949e; margin-bottom: 8px; }
.cite { margin-bottom: 6px; }
.cite-head {
  width: 100%; display: flex; align-items: center; gap: 8px;
  background: rgba(2, 6, 23, 0.6); border: 1px solid rgba(148, 163, 184, 0.16); border-radius: 8px;
  padding: 8px 10px; cursor: pointer; color: #dbeafe; font-size: 13px; text-align: left;
}
.badge { color: #4ade80; font-weight: 700; }
.cit-subject { color: #7dd3fc; }
.cit-title { color: #e2e8f0; }
.cit-src { color: #94a3b8; font-size: 12px; }
.toggle { margin-left: auto; color: #8b949e; font-size: 12px; }
.cite-body {
  margin: 6px 0 0; padding: 10px 12px; background: rgba(2, 6, 23, 0.7);
  border-left: 3px solid rgba(96, 165, 250, 0.7); border-radius: 0 8px 8px 0;
  color: #cbd5e1; font-size: 13px; line-height: 1.6; white-space: pre-wrap; overflow-x: auto;
}
.composer {
  display: flex; gap: 10px; margin-top: 14px; align-items: flex-end;
}
.composer textarea {
  flex: 1; min-height: 70px; max-height: 200px; resize: none;
  background: rgba(2, 6, 23, 0.7); border: 1px solid rgba(148, 163, 184, 0.22);
  border-radius: 10px; color: #e2e8f0; padding: 12px 14px; font-size: 14px; line-height: 1.5;
  box-sizing: border-box;
}
.composer textarea:focus { outline: none; border-color: rgba(96, 165, 250, 0.9); }
.composer button {
  height: 44px; padding: 0 22px; background: linear-gradient(135deg, #16a34a, #22c55e); color: white;
  border: none; border-radius: 10px; font-weight: 600; cursor: pointer; white-space: nowrap;
}
.composer button:disabled { background: #21262d; color: #6e7681; cursor: not-allowed; }
.err { color: #f87171; font-size: 13px; margin-top: 8px; }
</style>
