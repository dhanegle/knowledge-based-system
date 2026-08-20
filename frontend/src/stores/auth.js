import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { login as apiLogin, register as apiRegister, getMe } from '../api'

export const useAuthStore = defineStore('auth', () => {
  const token = ref(localStorage.getItem('zhiyuan_token') || '')
  const user = ref(null)

  const isLoggedIn = computed(() => !!token.value)
  const isAdmin = computed(() => user.value?.role === 'admin' || user.value?.role === 'owner')
  const isOwner = computed(() => user.value?.role === 'owner')

  function setToken(t) {
    token.value = t
    localStorage.setItem('zhiyuan_token', t)
  }

  function clearToken() {
    token.value = ''
    user.value = null
    localStorage.removeItem('zhiyuan_token')
  }

  async function login(username, password) {
    const data = await apiLogin(username, password)
    setToken(data.access_token)
    user.value = { username: data.username, role: data.role }
    return data
  }

  async function register(username, email, password) {
    const data = await apiRegister(username, email, password)
    setToken(data.access_token)
    user.value = { username: data.username, role: data.role }
    return data
  }

  async function fetchMe() {
    if (!token.value) return null
    try {
      const data = await getMe()
      // 如果用户变了（不同账号登录同一浏览器），清除旧对话
      if (user.value && user.value.username && user.value.username !== data.username) {
        const { useConversationStore } = await import('../stores/conversations')
        useConversationStore().clearCurrent()
      }
      user.value = data
      return data
    } catch {
      clearToken()
      return null
    }
  }

  function logout() {
    clearToken()
    // 清除对话状态
    import('../stores/conversations').then(({ useConversationStore }) => {
      useConversationStore().clearCurrent()
    })
  }

  return { token, user, isLoggedIn, isAdmin, isOwner, login, register, fetchMe, logout, setToken, clearToken }
})
