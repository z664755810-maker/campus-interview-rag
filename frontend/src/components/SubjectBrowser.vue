<script setup>
// 段 B-B2：专题刷题
// 按学科下拉/列表浏览题目，点开看完整内容。点"用 RAG 解析"可针对该题提问。
//
// 段 B-修 #4：补全示例题库后的难度筛选
//   - 顶部增加「全部 / 基础 / 进阶 / 困难」tab，按 metadata.difficulty 过滤
//   - 单题卡片显示难度标签 + 题型标签，便于识别
import { ref, computed } from 'vue'
import { getBySubject } from '../api.js'

const props = defineProps({ hasLibrary: Boolean })
const emit = defineEmits(['ask']) // 把题目内容传到 ChatPanel

const loading = ref(false)
const error = ref('')
const data = ref({ subjects: [], total: 0 })
const activeSubject = ref(null) // 当前选中的学科
const activeDifficulty = ref('全部') // 难度筛选
const openIndex = ref(null) // 当前展开的题号（q_index）
const search = ref('') // 学科内搜索关键字

// 难度 tab 列表（与后端 /api/documents/by-subject?difficulty=* 对应）
const DIFFICULTY_TABS = ['全部', '基础', '进阶', '困难']

async function load(difficulty = activeDifficulty.value) {
  loading.value = true
  error.value = ''
  try {
    data.value = await getBySubject(difficulty === '全部' ? null : difficulty)
    // 默认选中题数最多的学科（仅切到新难度时刷新默认）
    if (data.value.subjects.length && !activeSubject.value) {
      activeSubject.value = data.value.subjects[0].name
    }
  } catch (e) {
    error.value = e.message || '加载学科失败'
  } finally {
    loading.value = false
  }
}

const currentSubject = computed(() =>
  data.value.subjects.find((s) => s.name === activeSubject.value)
)

const filteredQuestions = computed(() => {
  const qs = currentSubject.value?.questions || []
  if (!search.value.trim()) return qs
  const k = search.value.trim().toLowerCase()
  return qs.filter(
    (q) =>
      (q.title || '').toLowerCase().includes(k) ||
      (q.preview || '').toLowerCase().includes(k) ||
      (q.question_only || '').toLowerCase().includes(k)
  )
})

function switchDifficulty(d) {
  activeDifficulty.value = d
  openIndex.value = null
  load(d)
}

function toggle(qIdx) {
  openIndex.value = openIndex.value === qIdx ? null : qIdx
}

function askAbout(q) {
  // 把题目内容作为问题扔回 ChatPanel 去问（让 RAG 生成整理后的答案）
  emit('ask', `请详细讲解：${q.title}`)
}

// 暴露给父组件主动调用（比如父组件切到本面板时刷新）
defineExpose({ load })

// 题型标签
const Q_TYPE_LABEL = {
  qa: '问答',
  multi_choice: '选择',
  judge: '判断',
  code_output: '代码输出',
}
</script>

<template>
  <div class="browser">
    <h2>2 · 专题刷题</h2>

    <div v-if="!hasLibrary" class="warn">
      ⚠️ 题库为空，请先在左侧上传面试题文档。
    </div>

    <div v-else-if="loading" class="info">加载中…</div>

    <div v-else-if="error" class="err">❌ {{ error }}</div>

    <div v-else-if="!data.subjects.length" class="info">题库中没有可分类的题目</div>

    <div v-else class="layout">
      <!-- 顶部：难度筛选 tabs -->
      <nav class="difficulty-bar">
        <button
          v-for="d in DIFFICULTY_TABS"
          :key="d"
          :class="['tab', { active: activeDifficulty === d }]"
          @click="switchDifficulty(d)"
        >{{ d }}</button>
      </nav>

      <!-- 左侧：学科列表 -->
      <aside class="subjects">
        <div class="search-box">
          <input v-model="search" placeholder="🔍 在本学科内搜题…" />
        </div>
        <ul>
          <li
            v-for="s in data.subjects"
            :key="s.name"
            :class="{ active: activeSubject === s.name }"
            @click="activeSubject = s.name; openIndex = null"
          >
            <span class="dot"></span>
            <span class="name">{{ s.name }}</span>
            <span class="count">{{ s.count }}</span>
          </li>
        </ul>
      </aside>

      <!-- 右侧：当前学科的题目 -->
      <section class="questions">
        <header>
          <h3>{{ activeSubject }} <span class="qtotal">{{ filteredQuestions.length }} 道</span></h3>
        </header>
        <ul v-if="filteredQuestions.length" class="qlist">
          <li v-for="q in filteredQuestions" :key="q.q_index + q.title" class="qitem">
            <button class="qhead" @click="toggle(q.q_index)">
              <span class="idx">{{ q.q_index || '?' }}</span>
              <span class="title">{{ q.question_only || q.title || '(无标题)' }}</span>
              <span class="diff" :class="q.difficulty">{{ q.difficulty || '基础' }}</span>
              <span class="qtype-pill">{{ Q_TYPE_LABEL[q.q_type] || '问答' }}</span>
              <span class="caret">{{ openIndex === q.q_index ? '▲' : '▼' }}</span>
            </button>
            <div v-if="openIndex === q.q_index" class="qbody">
              <p class="preview">{{ q.preview }}…</p>
              <button class="ask-btn" @click="askAbout(q)">💬 让 RAG 详细讲解</button>
            </div>
          </li>
        </ul>
        <p v-else class="empty">没有匹配的题目</p>
      </section>
    </div>
  </div>
</template>

<style scoped>
.browser { display: flex; flex-direction: column; height: 100%; padding: 20px 28px; }
.browser > h2 { font-size: 15px; color: #f0f6fc; margin: 0 0 14px; }
.warn {
  background: #2d1d00; border: 1px solid #9e6a03; color: #e3b341;
  padding: 12px 16px; border-radius: 8px; font-size: 13px;
}
.info, .err { color: #8b949e; font-size: 13px; padding: 20px 0; }
.err { color: #f85149; }

.layout { display: flex; gap: 16px; flex: 1; min-height: 0; }

/* 难度筛选 tabs（段 B-修 #4） */
.difficulty-bar {
  display: flex; gap: 8px; margin-bottom: 12px;
}
.difficulty-bar .tab {
  background: #0d1117; border: 1px solid #30363d; color: #c9d1d9;
  padding: 6px 16px; border-radius: 6px; font-size: 12px; cursor: pointer;
  font-family: inherit; transition: all 0.15s;
}
.difficulty-bar .tab:hover { border-color: #58a6ff; }
.difficulty-bar .tab.active {
  background: #1f6feb33; border-color: #58a6ff; color: #58a6ff;
}

/* 单题卡片里的难度 + 题型小标签 */
.qhead .diff {
  padding: 1px 6px; border-radius: 3px; font-size: 10px; font-weight: 600;
  flex-shrink: 0;
}
.qhead .diff.基础 { background: #1f3a5c; color: #79c0ff; }
.qhead .diff.进阶 { background: #5c3a1f; color: #ffa657; }
.qhead .diff.困难 { background: #5c1f1f; color: #ff8181; }
.qhead .diff.通用 { background: #30363d; color: #8b949e; }
.qhead .qtype-pill {
  background: #30363d; color: #c9d1d9; padding: 1px 6px; border-radius: 3px;
  font-size: 10px; flex-shrink: 0;
}

.subjects {
  width: 200px; flex-shrink: 0; display: flex; flex-direction: column;
  background: #0d1117; border: 1px solid #30363d; border-radius: 8px;
  overflow: hidden;
}
.search-box { padding: 10px; border-bottom: 1px solid #30363d; }
.search-box input {
  width: 100%; background: #161b22; border: 1px solid #30363d;
  color: #c9d1d9; padding: 6px 8px; border-radius: 6px; font-size: 12px;
  font-family: inherit; box-sizing: border-box;
}
.search-box input:focus { outline: none; border-color: #58a6ff; }
.subjects ul { list-style: none; padding: 6px; margin: 0; overflow-y: auto; flex: 1; }
.subjects li {
  display: flex; align-items: center; gap: 8px; padding: 8px 10px;
  border-radius: 6px; cursor: pointer; font-size: 13px; color: #c9d1d9;
}
.subjects li:hover { background: #161b22; }
.subjects li.active { background: #1f6feb33; color: #58a6ff; }
.subjects .dot {
  width: 6px; height: 6px; border-radius: 50%;
  background: #58a6ff; flex-shrink: 0;
}
.subjects .name { flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.subjects .count { color: #8b949e; font-size: 11px; }

.questions { flex: 1; min-width: 0; display: flex; flex-direction: column; }
.questions > header { margin-bottom: 10px; }
.questions h3 { margin: 0; color: #f0f6fc; font-size: 14px; }
.questions h3 .qtotal { color: #8b949e; font-size: 12px; margin-left: 8px; font-weight: normal; }
.qlist { list-style: none; padding: 0; margin: 0; overflow-y: auto; flex: 1; }
.qitem { margin-bottom: 8px; }
.qhead {
  width: 100%; display: flex; align-items: center; gap: 10px;
  background: #161b22; border: 1px solid #30363d; border-radius: 8px;
  padding: 10px 14px; color: #c9d1d9; font-size: 13px; text-align: left;
  cursor: pointer; font-family: inherit;
}
.qhead:hover { border-color: #58a6ff; }
.qhead .idx {
  background: #1f6feb; color: #fff; padding: 2px 6px; border-radius: 4px;
  font-size: 11px; font-weight: 600; flex-shrink: 0;
}
.qhead .title { flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.qhead .caret { color: #8b949e; font-size: 11px; }
.qbody { padding: 10px 14px; background: #0d1117; border: 1px solid #30363d; border-top: none; border-radius: 0 0 8px 8px; margin-top: -8px; }
.qbody .preview { color: #8b949e; font-size: 12px; line-height: 1.6; margin: 0 0 8px; }
.ask-btn {
  background: #1f6feb; color: #fff; border: none; border-radius: 6px;
  padding: 6px 12px; font-size: 12px; cursor: pointer; font-family: inherit;
}
.ask-btn:hover { background: #388bfd; }
.empty { color: #6e7681; font-size: 13px; text-align: center; padding: 30px 0; }
</style>
