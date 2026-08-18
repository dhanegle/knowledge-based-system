import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { login as apiLogin, register as apiRegister, getMe } from '../api'

export const useAuthStore = defineStore('auth', () => {
  const token = ref(localStorage.getItem('zhiyuan_token') || '')
  const user = ref(null)

  const isLoggedIn = computed(() => !!token.value)

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
    user.value = { username: data.username }
    return data
  }

  async function register(username, email, password) {
    const data = await apiRegister(username, email, password)
    setToken(data.access_token)
    user.value = { username: data.username }
    return data
  }

  async function fetchMe() {
    if (!token.value) return null
    try {
      const data = await getMe()
      user.value = data
      return data
    } catch {
      clearToken()
      return null
    }
  }

  function logout() {
    clearToken()
  }

  return { token, user, isLoggedIn, login, register, fetchMe, logout, setToken, clearToken }
})
