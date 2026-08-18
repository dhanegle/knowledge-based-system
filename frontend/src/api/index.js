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
  const resp = await fetch(`${API_BASE}${path}`, { ...options, headers })
  const data = await resp.json().catch(() => null)
  if (!resp.ok) {
    throw { status: resp.status, ...data }
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
