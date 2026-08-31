<script setup>
import { ref, nextTick } from 'vue'
import { postJson } from '../api.js'

// 对话面板：发 /api/ask，展示答案 + 引用出处卡片。
// 引用卡片默认折叠原文，点击展开——对应后端返回的 citations（含 [n] 映射元数据）。
// 段 A 改 #1：提问框占满 chat 区域，JS 动态调高度（最少 3 行，最多 8 行）。
const props = defineProps({ hasLibrary: Boolean })

const question = ref('')
const loading = ref(false)
const error = ref('')
const chats = ref([]) // { question, answer, citations, expanded:[] }

const MIN_ROWS = 3
const MAX_ROWS = 8
const LINE_PX = 22 // 与 CSS line-height 对应；用于按行数算高度
const textareaRef = ref(null)

function autoResize() {
  const el = textareaRef.value
  if (!el) return
  // 先重置到最小再读取 scrollHeight，让"删完字"也能收缩回去
  el.style.height = 'auto'
  el.style.height = Math.min(el.scrollHeight, MAX_ROWS * LINE_PX) + 'px'
}

async function send() {
  const q = question.value.trim()
  if (!q || loading.value) return
  loading.value = true
  error.value = ''
  try {
    const data = await postJson('/api/ask', { query: q, top_k: 5 })
    chats.value.push({
      question: q,
      answer: data.answer,
      citations: data.citations || [],
      expanded: (data.citations || []).map(() => false),
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

// 快捷键：Enter 发送 / Shift+Enter 换行
function onKey(e) {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault()
    send()
  }
}
// 段 B：暴露 fillQuestion 给父组件（专题刷题面板点击"💬 让 RAG 详细讲解"时调用）
defineExpose({
  fillQuestion(q) {
    question.value = q
    nextTick(() => autoResize())
  },
})
</script>

<template>
  <div class="chat">
    <h2>2 · 向题库提问</h2>

    <div v-if="!hasLibrary" class="warn">
      ⚠️ 题库为空，请先在左侧上传面试题文档，再开始提问。
    </div>

    <div class="messages" v-else>
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
        :placeholder="`例如：TCP 三次握手的作用是什么？\n支持多行输入（Enter 发送，Shift+Enter 换行）`"
        :rows="MIN_ROWS"
        :disabled="loading || !hasLibrary"
      ></textarea>
      <button :disabled="loading || !hasLibrary" @click="send">
        {{ loading ? '生成中…' : '提问' }}
      </button>
    </div>
    <p v-if="error" class="err">{{ error }}</p>
  </div>
</template>

<style scoped>
.chat { display: flex; flex-direction: column; height: 100%; padding: 20px 28px; }
.chat > h2 { font-size: 15px; color: #f0f6fc; margin: 0 0 14px; }
.warn {
  background: #2d1d00; border: 1px solid #9e6a03; color: #e3b341;
  padding: 12px 16px; border-radius: 8px; font-size: 13px; margin-bottom: 16px;
}
.messages { flex: 1; overflow-y: auto; padding-right: 6px; }
.msg {
  background: #161b22; border: 1px solid #30363d; border-radius: 10px;
  padding: 14px 16px; margin-bottom: 16px;
}
.q { font-weight: 600; color: #c9d1d9; margin-bottom: 8px; }
.q .tag {
  display: inline-block; background: #1f6feb; color: #fff; font-size: 12px;
  border-radius: 4px; padding: 1px 7px; margin-right: 8px;
}
.a { color: #c9d1d9; line-height: 1.7; white-space: pre-wrap; font-size: 14px; }
.cites { margin-top: 12px; border-top: 1px dashed #30363d; padding-top: 10px; }
.cites-head { font-size: 12px; color: #8b949e; margin-bottom: 8px; }
.cite { margin-bottom: 6px; }
.cite-head {
  width: 100%; display: flex; align-items: center; gap: 8px;
  background: #0d1117; border: 1px solid #30363d; border-radius: 6px;
  padding: 8px 10px; cursor: pointer; color: #c9d1d9; font-size: 13px; text-align: left;
}
.cite-head:hover { border-color: #58a6ff; }
.badge { color: #3fb950; font-weight: 700; }
.cit-subject { color: #58a6ff; }
.cit-title { color: #c9d1d9; }
.cit-src { color: #6e7681; font-size: 12px; }
.toggle { margin-left: auto; color: #8b949e; font-size: 12px; }
.cite-body {
  margin: 6px 0 0; padding: 10px 12px; background: #0d1117;
  border-left: 3px solid #30363d; border-radius: 0 6px 6px 0;
  color: #adbac7; font-size: 13px; line-height: 1.6; white-space: pre-wrap;
  overflow-x: auto;
}

/* 段 A 改 #1：提问框占满 chat 区域，附快捷键提示 */
.composer {
  display: flex; gap: 10px; margin-top: 14px;
  align-items: flex-end; /* 按钮贴底，与动态高度的 textarea 齐平 */
}
.composer textarea {
  flex: 1; min-height: 70px; max-height: 200px;
  resize: none; background: #0d1117; border: 1px solid #30363d;
  border-radius: 8px; color: #c9d1d9; padding: 12px 14px;
  font-size: 14px; font-family: inherit; line-height: 1.5;
  box-sizing: border-box;
  transition: border-color 0.15s;
}
.composer textarea:focus { outline: none; border-color: #58a6ff; }
.composer textarea:disabled { background: #161b22; color: #6e7681; }
.composer button {
  height: 44px; padding: 0 24px; background: #238636; color: #fff;
  border: none; border-radius: 8px; font-size: 14px; cursor: pointer; font-weight: 600;
  white-space: nowrap;
}
.composer button:disabled { background: #21262d; color: #6e7681; cursor: not-allowed; }
.composer button:hover:not(:disabled) { background: #2ea043; }
.err { color: #f85149; font-size: 13px; margin-top: 8px; }
</style>
