<script setup>
import { ref, onMounted } from 'vue'
import { uploadFile, getFormats, loadSample } from '../api.js'

const emit = defineEmits(['uploaded'])

const uploading = ref(false)
const loadingSample = ref(false)
const sampleCount = ref(0)
const message = ref('')
const error = ref('')
const dragOver = ref(false)

const formats = ref({ extensions: [], accept: '.md,.txt', labels: {}, unsupported_hints: {}, max_upload_mb: 10 })
const ready = ref(false)

onMounted(async () => {
  try {
    formats.value = await getFormats()
  } catch (e) {
    formats.value = {
      extensions: ['.md', '.txt', '.docx', '.pdf', '.pptx', '.xlsx', '.csv', '.json', '.html'],
      accept: '.md,.txt,.docx,.pdf,.pptx,.xlsx,.csv,.json,.html',
      labels: {},
      unsupported_hints: {},
      max_upload_mb: 10,
    }
  } finally {
    ready.value = true
  }
})

function extOf(name) {
  const i = (name || '').lastIndexOf('.')
  return i === -1 ? '' : name.slice(i).toLowerCase()
}

function validate(file) {
  const maxBytes = (formats.value.max_upload_mb || 10) * 1024 * 1024
  if (file.size > maxBytes) {
    return `文件 ${(file.size / 1024 / 1024).toFixed(1)}MB 超过上限 ${formats.value.max_upload_mb}MB，请拆分或压缩后再上传`
  }
  const ext = extOf(file.name)
  if (!ext) return '文件没有扩展名，无法判断类型，请补充后缀（如 .docx）'
  if (formats.value.extensions.includes(ext)) return ''
  const hint = formats.value.unsupported_hints?.[ext]
  if (hint) return hint
  return `暂不支持 ${ext} 格式，当前支持：${formats.value.extensions.join(' ')}`
}

async function handleFile(file) {
  if (!file) return
  error.value = ''
  message.value = ''

  const err = validate(file)
  if (err) {
    error.value = err
    return
  }

  uploading.value = true
  try {
    const data = await uploadFile('/api/documents/upload', file)
    message.value = `已入库 ${data.ingested} 条 · 来源 ${data.source}`
    emit('uploaded', { source: data.source, ingested: data.ingested })
  } catch (e) {
    error.value = e.message || '上传出错'
  } finally {
    uploading.value = false
  }
}

async function handleLoadSample() {
  error.value = ''
  message.value = ''
  loadingSample.value = true
  try {
    const data = await loadSample()
    sampleCount.value = data.ingested
  message.value = `企业知识库样例已载入 ${data.ingested} 条，可直接开始问答。`
    emit('uploaded', { source: data.source, ingested: data.ingested })
  } catch (e) {
    error.value = e.message || '载入示例库失败'
  } finally {
    loadingSample.value = false
  }
}

function onInput(e) {
  handleFile(e.target.files[0])
  e.target.value = ''
}

function onDrop(e) {
  dragOver.value = false
  handleFile(e.dataTransfer.files[0])
}
</script>

<template>
  <div class="upload-panel">
    <h2>1 · 准备知识库</h2>

    <button class="sample-btn" :disabled="loadingSample" @click="handleLoadSample">
      <span v-if="!loadingSample">⚡ 一键载入企业知识样例（<b>{{ sampleCount || 14 }}</b> 条）</span>
      <span v-else>载入中…</span>
    </button>

    <div class="divider"><span>或上传企业文档</span></div>

    <label
      class="drop"
      :class="{ over: dragOver }"
      @dragover.prevent="dragOver = true"
      @dragleave.prevent="dragOver = false"
      @drop.prevent="onDrop"
    >
      <input type="file" :accept="formats.accept" hidden @change="onInput" />
      <span v-if="!uploading" class="drop-text">
        📄 点击选择 或 拖拽文件到这里<br />
        <small>政策文档 / SOP / FAQ / 会议纪要 / Excel 等</small>
      </span>
      <span v-else>解析入库中…</span>
    </label>

    <div v-if="ready" class="formats">
      <span v-for="ext in formats.extensions" :key="ext" class="tag">{{ ext }}</span>
    </div>

    <p class="hint">
      单文件上限 {{ formats.max_upload_mb }}MB · 同名文件会幂等覆盖 ·
      老版 <code>.doc/.xls/.ppt</code> 请先用 WPS / Office 转为 <code>.docx/.xlsx/.pptx</code>
    </p>

    <div class="samples">
      需要示例语料？下载：
      <a href="/sample-enterprise.md" download>企业知识库样例</a>
    </div>

    <p v-if="message" class="ok">✓ {{ message }}</p>
    <p v-if="error" class="err">✗ {{ error }}</p>
  </div>
</template>

<style scoped>
.upload-panel { background: rgba(15, 23, 42, 0.8); border: 1px solid rgba(148,163,184,0.18); border-radius: 16px; padding: 16px; }
.upload-panel h2 { font-size: 15px; color: #f0f6fc; margin: 0 0 14px; }
.sample-btn {
  width: 100%; padding: 11px; border: 1px solid rgba(96,165,250,0.4); border-radius: 10px; background: linear-gradient(135deg, rgba(37,99,235,0.55), rgba(14,165,233,0.35)); color: white; cursor: pointer; font-weight: 600;
}
.sample-btn:disabled { opacity: 0.6; cursor: not-allowed; }
.divider { display: flex; align-items: center; gap: 10px; margin: 16px 0 12px; color: #6e7681; font-size: 12px; }
.divider::before, .divider::after { content: ''; flex: 1; height: 1px; background: rgba(148,163,184,0.18); }
.drop {
  display: flex; align-items: center; justify-content: center; height: 104px; border: 1.5px dashed rgba(148,163,184,0.32); border-radius: 12px; text-align: center; cursor: pointer; color: #8b949e; transition: .15s; background: rgba(15,23,42,0.7);
}
.drop:hover { border-color: #7dd3fc; color: #c9d1d9; }
.drop.over { border-color: #60a5fa; background: rgba(59,130,246,0.12); color: #fff; }
.drop-text small { color: #6e7681; }
.formats { display: flex; flex-wrap: wrap; gap: 5px; margin-top: 12px; }
.tag { font-size: 11px; padding: 2px 7px; border-radius: 20px; background: rgba(37,99,235,0.12); color: #7dd3fc; border: 1px solid rgba(96,165,250,0.28); }
.hint { color: #6e7681; font-size: 12px; line-height: 1.6; margin: 10px 0 0; }
.hint code { background: rgba(15,23,42,0.9); padding: 1px 4px; border-radius: 3px; color: #cbd5e1; font-size: 11px; }
.samples { margin-top: 10px; font-size: 12px; color: #6e7681; }
.samples a { color: #7dd3fc; text-decoration: none; }
.samples a:hover { text-decoration: underline; }
.samples .sep { margin: 0 6px; color: #30363d; }
.ok { color: #4ade80; font-size: 13px; margin: 10px 0 0; }
.err { color: #f87171; font-size: 13px; margin: 10px 0 0; line-height: 1.5; }
</style>
