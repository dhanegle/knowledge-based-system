const API_BASE = '/api'

function getToken() {
  return localStorage.getItem('zhiyuan_token')
}

async function request(path, options = {}) {
  const headers = options.headers || {}
  const token = getToken()
  if (token) {
    headers['Authorization'] = `Bearer ${token}`
  }
  if (options.body && typeof options.body === 'object') {
    headers['Content-Type'] = 'application/json'
    options.body = JSON.stringify(options.body)
  }
  let resp
  try {
    resp = await fetch(`${API_BASE}${path}`, { ...options, headers })
  } catch (e) {
    throw { status: 0, detail: '无法连接到服务器，请检查后端是否运行' }
  }
  const data = await resp.json().catch(() => null)
  if (!resp.ok) {
    throw { status: resp.status, ...(data || { detail: `请求失败 (${resp.status})` }) }
  }
  return data
}

export async function register(username, email, password) {
  return request('/auth/register', {
    method: 'POST',
    body: { username, email, password },
  })
}

export async function login(username, password) {
  return request('/auth/login', {
    method: 'POST',
    body: { username, password },
  })
}

export async function getMe() {
  return request('/auth/me')
}

export async function listDocuments() {
  return request('/documents')
}

export async function getDocument(docId) {
  return request(`/documents/${docId}`)
}

export async function deleteDocument(docId) {
  return request(`/documents/${docId}`, { method: 'DELETE' })
}

export async function uploadDocument(file) {
  const formData = new FormData()
  formData.append('file', file)
  const token = getToken()
  const resp = await fetch(`${API_BASE}/documents/upload`, {
    method: 'POST',
    headers: token ? { Authorization: `Bearer ${token}` } : {},
    body: formData,
  })
  const data = await resp.json().catch(() => null)
  if (!resp.ok) {
    throw { status: resp.status, ...data }
  }
  return data
}

export async function reingestDocument(docId, file) {
  const formData = new FormData()
  formData.append('file', file)
  const token = getToken()
  const resp = await fetch(`${API_BASE}/documents/${docId}/reingest`, {
    method: 'POST',
    headers: token ? { Authorization: `Bearer ${token}` } : {},
    body: formData,
  })
  const data = await resp.json().catch(() => null)
  if (!resp.ok) {
    throw { status: resp.status, ...data }
  }
  return data
}

export { API_BASE, getToken }

// ---- 对话历史 ----

export async function listConversations() {
  return request('/conversations')
}

export async function createConversation(title) {
  return request('/conversations', {
    method: 'POST',
    body: { title },
  })
}

export async function getConversation(id) {
  return request(`/conversations/${id}`)
}

export async function deleteConversation(id) {
  return request(`/conversations/${id}`, { method: 'DELETE' })
}

export async function updateConversation(id, title) {
  return request(`/conversations/${id}`, {
    method: 'PATCH',
    body: { title },
  })
}

// ---- 用户管理（管理员） ----

export async function listUsers() {
  return request('/admin/users')
}

export async function deleteUser(userId) {
  return request(`/admin/users/${userId}`, { method: 'DELETE' })
}

export async function updateUserRole(userId, role) {
  return request(`/admin/users/${userId}/role`, {
    method: 'PATCH',
    body: { role },
  })
}

export async function resetUserPassword(userId, newPassword) {
  return request(`/admin/users/${userId}/reset-password`, {
    method: 'POST',
    body: { new_password: newPassword },
  })
}
