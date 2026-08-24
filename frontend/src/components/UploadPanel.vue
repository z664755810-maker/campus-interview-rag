<script setup>
import { ref } from 'vue'
import { uploadFile } from '../api.js'

// 上传面板：选择/拖拽 .md/.txt 面试题文档，调后端 /api/documents/upload。
// 成功后 emit('uploaded') 把"来源+入库条数"抛给父组件 App，用于刷新库状态。
// 所有带 Key 的请求统一走 api.js（含 401/429 友好提示）。
const emit = defineEmits(['uploaded'])
const uploading = ref(false)
const message = ref('')
const error = ref('')
const dragOver = ref(false)

async function handleFile(file) {
  if (!file) return
  if (!file.name.endsWith('.md') && !file.name.endsWith('.txt')) {
    error.value = '仅支持 .md / .txt 文件'
    return
  }
  uploading.value = true
  error.value = ''
  message.value = ''
  try {
    const data = await uploadFile('/api/documents/upload', file)
    message.value = `已入库 ${data.ingested} 段 · 来源 ${data.source}`
    emit('uploaded', { source: data.source, ingested: data.ingested })
  } catch (e) {
    error.value = e.message || '上传出错'
  } finally {
    uploading.value = false
  }
}

function onInput(e) {
  handleFile(e.target.files[0])
  e.target.value = '' // 允许重复选同一文件触发上传
}
function onDrop(e) {
  dragOver.value = false
  handleFile(e.dataTransfer.files[0])
}
</script>

<template>
  <div class="upload">
    <h2>1 · 上传面试题库</h2>
    <label
      class="drop"
      :class="{ over: dragOver }"
      @dragover.prevent="dragOver = true"
      @dragleave.prevent="dragOver = false"
      @drop.prevent="onDrop"
    >
      <input type="file" accept=".md,.txt" hidden @change="onInput" />
      <span v-if="!uploading" class="drop-text">
        📄 点击选择 或 拖拽<br /><small>.md / .txt 面试题文档</small>
      </span>
      <span v-else>入库中…</span>
    </label>
    <p v-if="message" class="ok">✓ {{ message }}</p>
    <p v-if="error" class="err">✗ {{ error }}</p>
    <p class="hint">相同文件名会幂等覆盖更新，可反复校正题库。</p>
  </div>
</template>

<style scoped>
.upload h2 { font-size: 15px; color: #f0f6fc; margin: 0 0 14px; }
.drop {
  display: flex; align-items: center; justify-content: center;
  height: 110px; border: 1.5px dashed #30363d; border-radius: 10px;
  text-align: center; cursor: pointer; color: #8b949e; transition: .15s;
  background: #161b22;
}
.drop:hover { border-color: #58a6ff; color: #c9d1d9; }
.drop.over { border-color: #3fb950; background: #0d2818; color: #fff; }
.drop-text small { color: #6e7681; }
.ok { color: #3fb950; font-size: 13px; }
.err { color: #f85149; font-size: 13px; }
.hint { color: #6e7681; font-size: 12px; line-height: 1.5; }
</style>
