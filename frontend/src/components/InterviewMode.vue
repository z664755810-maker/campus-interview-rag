<script setup>
// 段 B-B3：模拟面试
// 随机抽 N 道题 → 限时（默认 90 秒/题）→ 自评（对/错/不确定）→ 评分 + 错题列表
//
// 段 B-修 #1：题干/答案拆开建模
//   - current.questionOnly 仅显示题干，不泄露答案
//   - 自评点击后才揭晓完整 current.content（题面 + 答案）
//   - 解锁后切换到下一题（状态由 revealed 决定）
//
// 段 B-修 #2：随时可退出
//   - 顶部「退出面试」按钮 → confirm 二次确认 → 回 setup 阶段
import { ref, computed, onUnmounted } from 'vue'
import { getRandom, postJson } from '../api.js'

const props = defineProps({ hasLibrary: Boolean })

const STEP = { SETUP: 'setup', INTERVIEW: 'interview', RESULT: 'result' }
const step = ref(STEP.SETUP)

const N_DEFAULT = 5
const TIME_PER_Q = 90 // 每题 90 秒
const subject = ref('') // 留空 = 全题库

// 状态
const questions = ref([]) // 抽到的题目
const currentIdx = ref(0)
const answers = ref([]) // { q, userSelf: 'right'|'wrong'|'unsure', userAnswer: '' }
const userInput = ref('') // 当前题的"我的作答"
const revealed = ref(false) // 当前题答案是否已揭晓
const timeLeft = ref(TIME_PER_Q)
let timerHandle = null

const current = computed(() => questions.value[currentIdx.value])
const correctCount = computed(() => answers.value.filter((a) => a.userSelf === 'right').length)
const scorePct = computed(() => {
  if (!answers.value.length) return 0
  return Math.round((correctCount.value / answers.value.length) * 100)
})

async function start() {
  try {
    const data = await getRandom(N_DEFAULT, subject.value || null)
    if (!data.questions.length) {
      alert('题库里抽不到题，请先上传题库或换个学科')
      return
    }
    questions.value = data.questions
    currentIdx.value = 0
    answers.value = []
    userInput.value = ''
    revealed.value = false
    startTimer()
    step.value = STEP.INTERVIEW
  } catch (e) {
    alert('抽题失败：' + e.message)
  }
}

function startTimer() {
  timeLeft.value = TIME_PER_Q
  if (timerHandle) clearInterval(timerHandle)
  timerHandle = setInterval(() => {
    timeLeft.value -= 1
    if (timeLeft.value <= 0) {
      // 时间到视为「揭晓并跳下一题」，同时标记为 unsure
      markAndNext('unsure')
    }
  }, 1000)
}

function stopTimer() {
  if (timerHandle) {
    clearInterval(timerHandle)
    timerHandle = null
  }
}

function markAndNext(self) {
  // 首次自评：揭晓答案；如果点的是 wrong/unsure，停留展示答案几秒再切下一题；
  // 如果点的是 right，直接切下一题（已经掌握，没必要多看）
  const alreadyRevealed = revealed.value
  // 1. 首次按下时把"是否揭晓"标记为 true（这样切换下一题前答案能停留可见）
  if (!alreadyRevealed) {
    revealed.value = true
    // right 类型直接跳过停留；wrong/unsure 停 4 秒让用户比对答案
    if (self === 'right') {
      proceedToNext(self)
      return
    }
    timerHandle = setTimeout(() => proceedToNext(self), 4000)
    // 清掉旧的秒级计时器，否则它会再触发 markAndNext
    stopTimer()
    return
  }
  // 2. 已经揭晓、用户二次点击"继续下一题"：直接走
  proceedToNext(self)
}

function proceedToNext(self) {
  answers.value.push({
    q: current.value,
    userAnswer: userInput.value,
    userSelf: self,
  })

  if (currentIdx.value + 1 >= questions.value.length) {
    stopTimer()
    step.value = STEP.RESULT
    return
  }
  currentIdx.value += 1
  userInput.value = ''
  revealed.value = false
  startTimer()
}

function quitInterview() {
  // 段 B-修 #2：随时可退出（二次确认）
  if (!window.confirm('确定要退出当前模拟面试吗？未做完的题目将不会计分。')) {
    return
  }
  stopTimer()
  step.value = STEP.SETUP
  questions.value = []
  currentIdx.value = 0
  answers.value = []
  userInput.value = ''
  revealed.value = false
  timeLeft.value = TIME_PER_Q
}

function restart() {
  stopTimer()
  step.value = STEP.SETUP
  questions.value = []
  answers.value = []
  userInput.value = ''
  revealed.value = false
  timeLeft.value = TIME_PER_Q
}

onUnmounted(stopTimer)

// 进度条
const progressPct = computed(() => {
  if (!questions.value.length) return 0
  return Math.round((currentIdx.value / questions.value.length) * 100)
})

const timerColor = computed(() => {
  if (timeLeft.value > 30) return '#3fb950'
  if (timeLeft.value > 10) return '#d29922'
  return '#f85149'
})

const mm = computed(() => String(Math.floor(timeLeft.value / 60)).padStart(1, '0'))
const ss = computed(() => String(timeLeft.value % 60).padStart(2, '0'))

// 揭示答案后，把已知类型映射成可读标签
const Q_TYPE_LABEL = {
  qa: '问答',
  multi_choice: '选择题',
  judge: '判断题',
  code_output: '代码输出',
}
</script>

<template>
  <div class="iv">
    <!-- ── 阶段 1：配置 ── -->
    <template v-if="step === 'setup'">
      <h2>2 · 模拟面试</h2>
      <div v-if="!hasLibrary" class="warn">
        ⚠️ 题库为空，请先在左侧上传面试题文档。
      </div>
      <div v-else class="setup">
        <p class="intro">
          随机从题库抽 {{ N_DEFAULT }} 道题，限时 {{ TIME_PER_Q }} 秒/题。<br />
          模拟真实面试节奏，时间到自动跳到下一题。
        </p>
        <label class="opt">
          <span>学科筛选（留空 = 全题库）</span>
          <input v-model="subject" placeholder="例如：Java / MySQL / 计算机网络" />
        </label>
        <button class="start" @click="start">🎤 开始模拟面试</button>
      </div>
    </template>

    <!-- ── 阶段 2：面试进行中 ── -->
    <template v-else-if="step === 'interview'">
      <header class="bar">
        <div class="progress">
          <span>第 <b>{{ currentIdx + 1 }}</b> / {{ questions.length }} 题</span>
          <div class="bar-bg"><div class="bar-fill" :style="{ width: progressPct + '%' }"></div></div>
        </div>
        <div class="timer" :style="{ color: timerColor }">⏱ {{ mm }}:{{ ss }}</div>
        <button class="quit" @click="quitInterview" title="随时退出当前面试">🚪 退出</button>
      </header>

      <div class="card">
        <div class="meta">
          <span class="tag">{{ current.subject }}</span>
          <span class="idx">{{ current.q_index }}</span>
          <span class="diff" :class="current.difficulty">{{ current.difficulty || '基础' }}</span>
          <span class="qtype">{{ Q_TYPE_LABEL[current.q_type] || '问答' }}</span>
        </div>
        <h3 class="qtitle">{{ current.question_only || current.title }}</h3>
        <!-- 题面与答案拆开建模：默认只显示题干，点击自评后才揭晓参考答案 -->
        <textarea
          v-model="userInput"
          class="myanswer"
          placeholder="📝 在这里写你的作答思路（不会传给后端，仅本地自评用）"
        ></textarea>

        <!-- 揭晓区：reaveled=true 时展开参考答案 -->
        <transition name="reveal">
          <div v-if="revealed" class="answer-reveal">
            <div class="answer-label">📖 参考答案</div>
            <pre class="qcontent">{{ current.content }}</pre>
            <p v-if="!userInput.trim()" class="hint">
              💡 看看参考答案与你的思路有啥差距 → 继续下一题
            </p>
          </div>
        </transition>

        <div class="actions">
          <button
            v-if="!revealed"
            class="btn wrong"
            @click="markAndNext('wrong')"
          >❌ 我答错了</button>
          <button
            v-if="!revealed"
            class="btn unsure"
            @click="markAndNext('unsure')"
          >🤔 不确定</button>
          <button
            v-if="!revealed"
            class="btn right"
            @click="markAndNext('right')"
          >✅ 我答对了</button>
          <!-- 揭晓后允许手动「继续下一题」 -->
          <button
            v-else
            class="btn continue"
            @click="markAndNext(current.userSelf || 'unsure')"
          >➡ 下一题</button>
        </div>
      </div>
    </template>

    <!-- ── 阶段 3：结果 ── -->
    <template v-else>
      <h2>2 · 模拟面试结果</h2>
      <div class="result">
        <div class="score-card" :class="scorePct >= 60 ? 'pass' : 'fail'">
          <div class="score-num">{{ scorePct }}<small>分</small></div>
          <div class="score-detail">
            答对 {{ correctCount }} / {{ answers.length }} 题
          </div>
        </div>

        <h3>📋 答题回顾</h3>
        <ul class="review">
          <li v-for="(a, i) in answers" :key="i" :class="a.userSelf">
            <div class="rev-head">
              <span class="badge" :class="a.userSelf">
                {{ a.userSelf === 'right' ? '✓' : a.userSelf === 'wrong' ? '✗' : '?' }}
              </span>
              <span class="rev-subject">{{ a.q.subject }}</span>
              <span class="rev-title">{{ a.q.title }}</span>
            </div>
            <details v-if="a.userAnswer">
              <summary>我的作答</summary>
              <pre>{{ a.userAnswer }}</pre>
            </details>
            <details>
              <summary>参考答案</summary>
              <pre>{{ a.q.content }}</pre>
            </details>
          </li>
        </ul>

        <div class="end-actions">
          <button class="restart" @click="restart">🔁 再来一轮</button>
        </div>
      </div>
    </template>
  </div>
</template>

<style scoped>
.iv { display: flex; flex-direction: column; height: 100%; padding: 20px 28px; }
.iv > h2 { font-size: 15px; color: #f0f6fc; margin: 0 0 14px; }
.warn {
  background: #2d1d00; border: 1px solid #9e6a03; color: #e3b341;
  padding: 12px 16px; border-radius: 8px; font-size: 13px;
}

.setup { max-width: 500px; }
.intro { color: #8b949e; line-height: 1.7; font-size: 13px; margin-bottom: 20px; }
.opt { display: flex; flex-direction: column; gap: 6px; margin-bottom: 20px; }
.opt span { color: #c9d1d9; font-size: 13px; }
.opt input {
  background: #0d1117; border: 1px solid #30363d; color: #c9d1d9;
  padding: 8px 12px; border-radius: 6px; font-size: 14px; font-family: inherit;
}
.opt input:focus { outline: none; border-color: #58a6ff; }
.start {
  background: #238636; color: #fff; border: none; border-radius: 8px;
  padding: 12px 28px; font-size: 15px; cursor: pointer; font-weight: 600;
  font-family: inherit;
}
.start:hover { background: #2ea043; }

.bar {
  display: flex; justify-content: space-between; align-items: center;
  margin-bottom: 16px; padding: 10px 14px; background: #161b22;
  border: 1px solid #30363d; border-radius: 8px;
}
.progress { flex: 1; margin-right: 16px; }
.progress span { font-size: 13px; color: #c9d1d9; }
.progress b { color: #58a6ff; font-size: 16px; }
.bar-bg { height: 4px; background: #0d1117; border-radius: 2px; margin-top: 6px; overflow: hidden; }
.bar-fill { height: 100%; background: linear-gradient(90deg, #58a6ff, #1f6feb); transition: width 0.3s; }
.timer { font-size: 22px; font-weight: 600; font-family: 'Courier New', monospace; }

.card {
  flex: 1; background: #161b22; border: 1px solid #30363d; border-radius: 10px;
  padding: 18px 22px; display: flex; flex-direction: column; min-height: 0;
}
.meta { display: flex; gap: 8px; margin-bottom: 10px; }
.meta .tag {
  background: #1f6feb33; color: #58a6ff; padding: 2px 8px; border-radius: 4px;
  font-size: 11px; font-weight: 600;
}
.meta .idx {
  background: #30363d; color: #c9d1d9; padding: 2px 8px; border-radius: 4px; font-size: 11px;
}
.qtitle { color: #f0f6fc; margin: 0 0 12px; font-size: 16px; }
.qcontent {
  color: #c9d1d9; font-size: 13px; line-height: 1.7; white-space: pre-wrap;
  background: #0d1117; padding: 12px; border-radius: 6px;
  max-height: 220px; overflow-y: auto; margin: 0 0 12px;
}
.myanswer {
  width: 100%; min-height: 80px; resize: vertical;
  background: #0d1117; border: 1px solid #30363d; border-radius: 6px;
  color: #c9d1d9; padding: 10px 12px; font-size: 13px; font-family: inherit;
  line-height: 1.5; box-sizing: border-box;
}
.myanswer:focus { outline: none; border-color: #58a6ff; }
.actions { display: flex; gap: 10px; margin-top: 12px; }
.btn {
  flex: 1; padding: 10px 12px; border: none; border-radius: 8px;
  font-size: 13px; cursor: pointer; font-weight: 600; font-family: inherit;
}
.btn.right { background: #238636; color: #fff; }
.btn.right:hover { background: #2ea043; }
.btn.unsure { background: #9e6a03; color: #fff; }
.btn.unsure:hover { background: #bb8009; }
.btn.wrong { background: #da3633; color: #fff; }
.btn.wrong:hover { background: #f85149; }
.btn.continue {
  background: #1f6feb; color: #fff; flex: 0 0 auto; min-width: 160px;
}
.btn.continue:hover { background: #388bfd; }

/* 退出按钮 */
.quit {
  background: transparent; color: #8b949e; border: 1px solid #30363d;
  padding: 4px 10px; border-radius: 6px; font-size: 12px; cursor: pointer;
  font-family: inherit; margin-left: 10px;
}
.quit:hover { color: #f85149; border-color: #f85149; }

/* 元数据标签：难度 + 题型 */
.diff {
  padding: 2px 8px; border-radius: 4px; font-size: 11px; font-weight: 600;
}
.diff.基础 { background: #1f3a5c; color: #79c0ff; }
.diff.进阶 { background: #5c3a1f; color: #ffa657; }
.diff.困难 { background: #5c1f1f; color: #ff8181; }
.diff.通用 { background: #30363d; color: #8b949e; }
.qtype {
  background: #30363d; color: #c9d1d9; padding: 2px 8px;
  border-radius: 4px; font-size: 11px;
}

/* 答案揭晓区 */
.answer-reveal {
  margin-top: 14px; padding: 14px 16px;
  background: #0d1117; border: 1px solid #1f6feb; border-radius: 8px;
}
.answer-label {
  font-size: 12px; color: #58a6ff; font-weight: 600;
  margin-bottom: 8px; letter-spacing: 0.5px;
}
.answer-reveal .hint {
  color: #8b949e; font-size: 12px; margin: 8px 0 0;
}

.reveal-enter-active, .reveal-leave-active { transition: opacity 0.3s, transform 0.3s; }
.reveal-enter-from, .reveal-leave-to { opacity: 0; transform: translateY(-6px); }

.result { flex: 1; overflow-y: auto; }
.score-card {
  text-align: center; padding: 24px; border-radius: 12px;
  background: #161b22; border: 2px solid; margin-bottom: 20px;
}
.score-card.pass { border-color: #3fb950; }
.score-card.fail { border-color: #f85149; }
.score-num { font-size: 48px; font-weight: 700; color: #f0f6fc; }
.score-num small { font-size: 18px; color: #8b949e; margin-left: 4px; }
.score-detail { color: #8b949e; font-size: 14px; margin-top: 4px; }

.review { list-style: none; padding: 0; margin: 0; }
.review li { background: #161b22; border: 1px solid #30363d; border-radius: 8px; padding: 10px 14px; margin-bottom: 8px; }
.review li.right { border-left: 3px solid #3fb950; }
.review li.wrong { border-left: 3px solid #f85149; }
.review li.unsure { border-left: 3px solid #d29922; }
.rev-head { display: flex; align-items: center; gap: 8px; }
.rev-head .badge {
  width: 20px; height: 20px; border-radius: 50%; display: inline-flex;
  align-items: center; justify-content: center; font-size: 12px; font-weight: 700; flex-shrink: 0;
}
.rev-head .badge.right { background: #238636; color: #fff; }
.rev-head .badge.wrong { background: #da3633; color: #fff; }
.rev-head .badge.unsure { background: #9e6a03; color: #fff; }
.rev-subject { color: #58a6ff; font-size: 12px; }
.rev-title { color: #c9d1d9; font-size: 13px; }
.review details { margin-top: 8px; font-size: 12px; color: #8b949e; }
.review details summary { cursor: pointer; padding: 2px 0; }
.review details pre { background: #0d1117; padding: 8px; border-radius: 4px; white-space: pre-wrap; font-size: 12px; line-height: 1.6; }

.end-actions { text-align: center; margin-top: 20px; }
.restart {
  background: #1f6feb; color: #fff; border: none; border-radius: 8px;
  padding: 10px 24px; font-size: 14px; cursor: pointer; font-family: inherit;
}
.restart:hover { background: #388bfd; }
</style>
