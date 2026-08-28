<script setup>
import { ref, onMounted } from 'vue'
import { getApiKey, setApiKey, getStats } from './api.js'
import UploadPanel from './components/UploadPanel.vue'
import ChatPanel from './components/ChatPanel.vue'

// App 作为布局与状态中转：上传成功后累加"已索引段数"，
// 并把 hasLibrary 传给 ChatPanel 控制"题库为空"提示与禁用态。
const uploads = ref([])
const libraryCount = ref(0)

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
}

// 启动时同步一次真实题库状态。
// 原因：PaaS 免费层重启会清空数据盘，后端 seed 会自动灌入 50 道示例题；
// 前端若不主动拉，就会显示「已索引 0 段」而实际有 50 条，误导用户。
onMounted(async () => {
  try {
    const s = await getStats()
    libraryCount.value = s.count || 0
    uploads.value = (s.sources || []).map((x) => ({
      source: x.source,
      ingested: x.chunks,
    }))
  } catch (e) {
    // 统计接口失败就维持 0，不阻断页面使用
    console.warn('题库状态拉取失败：', e.message)
  }
})

// 阶段4：API Key 设置。key 存 localStorage，统一由 api.js 附加到请求头。
// 首次进入用演示 key 预填，保证开箱即用；用户可自行改成自己的 key。
const apiKey = ref(getApiKey() || 'dev-rag-2026')
const keySaved = ref(false)
if (!getApiKey()) setApiKey(apiKey.value) // 首次落默认演示 key
function saveKey() {
  setApiKey(apiKey.value)
  keySaved.value = true
  setTimeout(() => (keySaved.value = false), 2000)
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
        <div class="key-box">
          <label>API Key</label>
          <input v-model="apiKey" placeholder="dev-rag-2026（演示用）" @keyup.enter="saveKey" />
          <button @click="saveKey">保存</button>
          <span v-if="keySaved" class="saved">✓ 已保存</span>
        </div>
        <div class="lib-stat">题库已索引 <b>{{ libraryCount }}</b> 段</div>
      </div>
    </header>

    <main class="layout">
      <aside class="sidebar">
        <UploadPanel @uploaded="onUploaded" />
        <div class="lib-list" v-if="uploads.length">
          <h3>已上传文档</h3>
          <ul>
            <li v-for="(u, i) in uploads" :key="i">
              <span class="dot"></span>{{ u.source }}
              <em>{{ u.ingested }} 段</em>
            </li>
          </ul>
        </div>
      </aside>

      <section class="chat-area">
        <ChatPanel :has-library="libraryCount > 0" />
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
}
.brand { display: flex; align-items: center; gap: 12px; }
.brand .logo { font-size: 28px; }
.topbar h1 { font-size: 18px; margin: 0; color: #f0f6fc; }
.topbar .sub { margin: 2px 0 0; font-size: 12px; color: #8b949e; }
.right { display: flex; align-items: center; gap: 20px; }
.key-box { display: flex; align-items: center; gap: 6px; font-size: 12px; color: #8b949e; }
.key-box label { white-space: nowrap; }
.key-box input {
  width: 150px; background: #0d1117; border: 1px solid #30363d; border-radius: 6px;
  color: #c9d1d9; padding: 5px 8px; font-size: 12px; font-family: inherit;
}
.key-box input:focus { outline: none; border-color: #58a6ff; }
.key-box button {
  background: #21262d; border: 1px solid #30363d; color: #c9d1d9;
  border-radius: 6px; padding: 5px 10px; font-size: 12px; cursor: pointer;
}
.key-box button:hover { border-color: #58a6ff; }
.key-box .saved { color: #3fb950; }
.lib-stat { font-size: 13px; color: #8b949e; white-space: nowrap; }
.lib-stat b { color: #58a6ff; font-size: 16px; }
.layout { flex: 1; display: flex; min-height: 0; }
.sidebar {
  width: 320px; padding: 20px; border-right: 1px solid #30363d;
  overflow-y: auto; background: #0d1117;
}
.chat-area { flex: 1; min-width: 0; display: flex; }
.lib-list { margin-top: 24px; }
.lib-list h3 { font-size: 13px; color: #8b949e; margin: 0 0 10px; }
.lib-list ul { list-style: none; padding: 0; margin: 0; }
.lib-list li {
  display: flex; align-items: center; gap: 8px; padding: 8px 10px;
  background: #161b22; border: 1px solid #30363d; border-radius: 8px;
  font-size: 13px; margin-bottom: 8px;
}
.lib-list li .dot { width: 8px; height: 8px; border-radius: 50%; background: #3fb950; }
.lib-list li em { margin-left: auto; color: #8b949e; font-style: normal; }
</style>
