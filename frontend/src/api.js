// 统一请求层：自动附加 X-API-Key，并集中翻译鉴权/限流的友好错误提示。
//
// 为什么单独抽这一层？
// 阶段4 起，所有业务接口都需要带 API Key 才能访问。如果让每个组件各自拼
// 请求头、各自判断 401/429，会出现大量重复代码，改密钥头名也得改多处。
// 把"带 key 的 HTTP 调用"收口到这一个文件，组件只关心业务数据，符合
// 工程上的「单一职责 + 关注点分离」。
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
    if (res.status === 401) detail = '未授权：请在右上角填写有效的 API Key'
    else if (res.status === 429) detail = '请求过于频繁，请稍后再试（已触发限流）'
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

export async function uploadFile(path, file) {
  const form = new FormData()
  form.append('file', file)
  return request(path, { method: 'POST', body: form })
}
