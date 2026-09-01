<script setup>
import { ref, onMounted } from 'vue'
import { uploadFile, getFormats, loadSample } from '../api.js'

// 上传面板：支持多格式文档上传 + 一键载入示例题库 + 示例文件下载。
//
// 三个设计点：
// 1. 格式白名单从后端 /api/documents/formats 拉取，前后端共用一份，
//    不会出现「前端放行了、后端又拒绝」的割裂体验。
// 2. 不支持的老格式（.doc/.xls/.ppt）给出「怎么转」的可执行建议，
//    而不是干巴巴一句「格式不支持」。
// 3. 手边没文件时，一键载入示例题库 —— 降低首次体验门槛的关键。
const emit = defineEmits(['uploaded'])

const uploading = ref(false)
const loadingSample = ref(false)
const sampleCount = ref(0) // 动态显示最近一次载入示例题库的数量
const message = ref('')
const error = ref('')
const dragOver = ref(false)

// 后端下发的格式信息
const formats = ref({ extensions: [], accept: '.md,.txt', labels: {}, unsupported_hints: {}, max_upload_mb: 10 })
const ready = ref(false)

onMounted(async () => {
  try {
    formats.value = await getFormats()
  } catch (e) {
    // 拉不到就用兜底名单，不让一个辅助接口失败卡住整个上传功能
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

// 本地前置校验：体积 + 扩展名，失败时给出可执行的下一步
function validate(file) {
  const maxBytes = (formats.value.max_upload_mb || 10) * 1024 * 1024
  if (file.size > maxBytes) {
    return `文件 ${(file.size / 1024 / 1024).toFixed(1)}MB 超过上限 ${formats.value.max_upload_mb}MB，请拆分或压缩后再传`
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
    message.value = `已入库 ${data.ingested} 段 · 来源 ${data.source}`
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
    message.value = `示例题库已载入 ${data.ingested} 道题，可以直接提问了`
    emit('uploaded', { source: data.source, ingested: data.ingested })
  } catch (e) {
    error.value = e.message || '载入示例题库失败'
  } finally {
    loadingSample.value = false
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
    <h2>1 · 准备面试题库</h2>

    <!-- 主入口：一键载入示例。手边没文件时也能立刻体验 -->
    <button class="sample-btn" :disabled="loadingSample" @click="handleLoadSample">
      <span v-if="!loadingSample">⚡ 一键载入示例题库（<b>{{ sampleCount || 70 }}</b> 道）</span>
      <span v-else>载入中…</span>
    </button>

    <div class="divider"><span>或上传自己的文档</span></div>

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
        <small>Word / PDF / PPT / Excel / TXT / Markdown 等</small>
      </span>
      <span v-else>解析入库中…</span>
    </label>

    <!-- 支持格式标签，一眼看清能传什么 -->
    <div v-if="ready" class="formats">
      <span v-for="ext in formats.extensions" :key="ext" class="tag">{{ ext }}</span>
    </div>

    <p class="hint">
      单文件上限 {{ formats.max_upload_mb }}MB · 相同文件名幂等覆盖 ·
      老版 <code>.doc/.xls/.ppt</code> 请先用 WPS/Office 另存为 <code>.docx/.xlsx/.pptx</code>
    </p>

    <!-- 示例文件下载 -->
    <div class="samples">
      没有现成文件？下载示例：
      <a href="/sample-interview.docx" download>Word 版</a>
      <span class="sep">·</span>
      <a href="/sample-interview.md" download>Markdown 版</a>
    </div>

    <p v-if="message" class="ok">✓ {{ message }}</p>
    <p v-if="error" class="err">✗ {{ error }}</p>
  </div>
</template>

<style scoped>
.upload h2 { font-size: 15px; color: #f0f6fc; margin: 0 0 14px; }

.sample-btn {
  width: 100%; padding: 11px; margin-bottom: 4px;
  background: #238636; color: #fff; border: 1px solid rgba(240, 246, 252, .1);
  border-radius: 8px; font-size: 14px; font-weight: 600; cursor: pointer;
  transition: .15s;
}
.sample-btn:hover:not(:disabled) { background: #2ea043; }
.sample-btn:disabled { opacity: .6; cursor: not-allowed; }

.divider {
  display: flex; align-items: center; gap: 10px;
  margin: 16px 0 12px; color: #6e7681; font-size: 12px;
}
.divider::before, .divider::after {
  content: ''; flex: 1; height: 1px; background: #30363d;
}

.drop {
  display: flex; align-items: center; justify-content: center;
  height: 100px; border: 1.5px dashed #30363d; border-radius: 10px;
  text-align: center; cursor: pointer; color: #8b949e; transition: .15s;
  background: #161b22;
}
.drop:hover { border-color: #58a6ff; color: #c9d1d9; }
.drop.over { border-color: #3fb950; background: #0d2818; color: #fff; }
.drop-text small { color: #6e7681; }

.formats { display: flex; flex-wrap: wrap; gap: 5px; margin-top: 12px; }
.tag {
  font-size: 11px; padding: 2px 7px; border-radius: 20px;
  background: #1f6feb22; color: #58a6ff; border: 1px solid #1f6feb44;
}

.hint { color: #6e7681; font-size: 12px; line-height: 1.6; margin: 10px 0 0; }
.hint code {
  background: #1f2428; padding: 1px 4px; border-radius: 3px;
  color: #8b949e; font-size: 11px;
}

.samples { margin-top: 10px; font-size: 12px; color: #6e7681; }
.samples a { color: #58a6ff; text-decoration: none; }
.samples a:hover { text-decoration: underline; }
.samples .sep { margin: 0 6px; color: #30363d; }

.ok { color: #3fb950; font-size: 13px; margin: 10px 0 0; }
.err { color: #f85149; font-size: 13px; margin: 10px 0 0; line-height: 1.5; }
</style>
