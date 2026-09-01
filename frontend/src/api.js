// 统一请求层：自动附加 X-API-Key，并集中翻译鉴权/限流的友好错误提示。
//
// 部署改造：基础地址由 VITE_API_BASE 决定。
// - 开发环境：留空，默认 /api（Vite 代理到 127.0.0.1:8000）
// - 生产环境：填线上后端完整地址，如 https://campus-interview-rag.up.railway.app

const KEY_STORAGE = 'rag_api_key'

// Vite 注入的环境变量；未设置时为空串，请求走相对路径（开发走代理）
const BASE = import.meta.env.VITE_API_BASE || ''

export function getApiKey() {
  return localStorage.getItem(KEY_STORAGE) || ''
}

export function setApiKey(key) {
  const k = (key || '').trim()
  if (k) localStorage.setItem(KEY_STORAGE, k)
  else localStorage.removeItem(KEY_STORAGE)
}

async function request(path, options = {}) {
  const headers = { ...(options.headers || {}) }
  const key = getApiKey()
  if (key) headers['X-API-Key'] = key

  // 绝对路径直接用；相对路径拼 BASE
  const url = /^https?:\/\//.test(path) ? path : `${BASE}${path}`

  const res = await fetch(url, { ...options, headers })

  if (!res.ok) {
    // 集中处理业务加固相关的状态码，给出人话提示
    let detail = `请求失败 (${res.status})`
    if (res.status === 401) detail = '未授权：API Key 无效（请检查配置）'
    else if (res.status === 429) detail = '请求过于频繁，请稍后再试（已触发限流）'
    else if (res.status === 413) detail = '文件过大，请拆分后再上传'
    else if (res.status === 415) detail = '不支持的文件格式'
    else {
      const e = await res.json().catch(() => ({}))
      if (e.detail) detail = e.detail
    }
    throw new Error(detail)
  }
  return res.json()
}

export function postJson(path, body) {
  return request(path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
}

export function deleteReq(path) {
  return request(path, { method: 'DELETE' })
}

export async function uploadFile(path, file) {
  const form = new FormData()
  form.append('file', file)
  return request(path, { method: 'POST', body: form })
}

// 拉取后端「支持哪些格式」的白名单，前后端共用一份，避免两处维护不一致
export function getFormats() {
  return request('/api/documents/formats')
}

// 拉取当前题库真实状态（总片段数 + 来源分布）。
export function getStats() {
  return request('/api/documents/stats')
}

// 一键载入内置示例题库：手边没有现成文件时，点一下就能立刻体验完整链路
export function loadSample() {
  return request('/api/documents/load-sample', { method: 'POST' })
}

// 当前客户端的限流配额状态（段 A 改 #3：API Key 装饰化后，前端只看配额）
export function getUsage() {
  return request('/api/usage')
}

// 按 source 删除某个文档（段 A 改 #2：题库管理）
export function deleteBySource(source) {
  // source 可能含中文/点号/空格，必须 encodeURIComponent
  return deleteReq(`/api/documents/by-source/${encodeURIComponent(source)}`)
}

// 清空整个题库（需要传 confirm=true）
export function clearLibrary() {
  return postJson('/api/documents/clear', { confirm: true })
}

// 按学科分组列出所有题目（段 B-B2：专题刷题）
// difficulty 可为 null（全部）或 '基础' / '进阶' / '困难'，与后端 /by-subject?difficulty=* 对应
export function getBySubject(difficulty = null) {
  const q = difficulty ? `?difficulty=${encodeURIComponent(difficulty)}` : ''
  return request(`/api/documents/by-subject${q}`)
}

// 随机抽 N 道题（段 B-B3：模拟面试）
export function getRandom(n = 5, subject = null) {
  const q = subject ? `?n=${n}&subject=${encodeURIComponent(subject)}` : `?n=${n}`
  return request(`/api/documents/random${q}`)
}
