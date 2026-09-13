import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import {
  listConversations,
  getConversation,
  createConversation,
  deleteConversation as apiDeleteConv,
  getToken,
} from '../api'

export const useConversationStore = defineStore('conversations', () => {
  const conversations = ref([])
  const currentId = ref(null)
  const loading = ref(false)
  const streaming = ref(false)
  // 每个对话独立的消息缓存，切换对话不互相覆盖
  const messagesMap = ref({})
  // 当前流式请求的取消句柄和身份，避免旧请求结束时覆盖新状态
  let activeRequest = null

  // 当前对话的消息（computed，随 currentId 切换）
  const messages = computed(() => messagesMap.value[currentId.value] || [])

  async function fetchConversations() {
    loading.value = true
    try {
      conversations.value = await listConversations()
    } finally {
      loading.value = false
    }
  }

  async function selectConversation(id) {
    currentId.value = id
    // 已有缓存就不重新拉，避免覆盖流式中/已加载的内容
    if (messagesMap.value[id]) return
    const data = await getConversation(id)
    messagesMap.value[id] = (data.messages || []).map(m => ({
      role: m.role,
      content: m.content,
      sources: m.sources || [],
      error: '',
    }))
  }

  async function createNew() {
    const data = await createConversation()
    conversations.value.unshift(data)
    currentId.value = data.id
    messagesMap.value[data.id] = []
    return data
  }

  async function removeConversation(id) {
    if (id === currentId.value) {
      cancelActiveRequest()
    }
    await apiDeleteConv(id)
    conversations.value = conversations.value.filter(c => c.id !== id)
    delete messagesMap.value[id]
    if (currentId.value === id) {
      currentId.value = null
    }
  }

  function cancelActiveRequest() {
    if (activeRequest) {
      activeRequest.controller.abort()
      activeRequest = null
    }
    streaming.value = false
  }

  function clearCurrent() {
    cancelActiveRequest()
    currentId.value = null
    messagesMap.value = {}
  }

  /**
   * 发起流式问答。读取器存在 store 而非组件，切换页面/对话不中断。
   * 消息写入当前对话的独立缓存，切走再切回不丢失。
   */
  async function ask(question) {
    if (streaming.value) return
    if (!question.trim()) return
    if (!currentId.value) return

    const convId = currentId.value
    const convMessages = messagesMap.value[convId] || []
    messagesMap.value[convId] = convMessages

    convMessages.push({ role: 'user', content: question })
    const aiMsg = { role: 'assistant', content: '', sources: [], error: '' }
    convMessages.push(aiMsg)

    streaming.value = true
    const controller = new AbortController()
    const request = { convId, controller }
    activeRequest = request

    try {
      const token = getToken()
      const convParam = `&conversation_id=${convId}`
      const url = `/api/ask?q=${encodeURIComponent(question)}${convParam}`
      const resp = await fetch(url, {
        headers: token ? { Authorization: `Bearer ${token}` } : {},
        signal: controller.signal,
      })

      if (!resp.ok) {
        let errorMessage = `请求失败（${resp.status}）`
        try {
          const raw = await resp.text()
          if (raw) {
            try {
              const payload = JSON.parse(raw)
              errorMessage = payload.detail || payload.error || errorMessage
            } catch {
              errorMessage = raw.slice(0, 500)
            }
          }
        } catch {
          // 保留状态码作为错误信息
        }
        aiMsg.error = errorMessage
        return
      }

      if (!resp.body) {
        aiMsg.error = '服务器未返回流式响应'
        return
      }

      const reader = resp.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ''

      const consumeEvent = (line) => {
        if (!line.startsWith('data:')) return
        const data = line.slice(5).trim()
        if (!data) return
        try {
          const parsed = JSON.parse(data)
          if (parsed.sources) {
            aiMsg.sources = parsed.sources
          } else if (parsed.text) {
            aiMsg.content += parsed.text
          } else if (parsed.ok === false || parsed.error) {
            aiMsg.error = parsed.error || '请求失败'
          }
        } catch {
          // 非 JSON，跳过
        }
      }

      while (true) {
        const { done, value } = await reader.read()
        if (done) {
          buffer += decoder.decode()
          break
        }
        buffer += decoder.decode(value, { stream: true })

        const lines = buffer.split('\n')
        buffer = lines.pop()

        for (const line of lines) {
          consumeEvent(line)
        }
      }
      if (buffer) consumeEvent(buffer)
      // 流式完成后刷新对话列表（标题/时间可能更新）
      try {
        await fetchConversations()
      } catch {
        // 对话内容已完成，列表刷新失败不覆盖回答
      }
    } catch (error) {
      if (controller.signal.aborted || error?.name === 'AbortError') return
      aiMsg.error = error?.message || '网络错误，请稍后重试'
    } finally {
      if (activeRequest === request) {
        activeRequest = null
        streaming.value = false
      }
    }
  }

  return {
    conversations,
    currentId,
    messages,
    loading,
    streaming,
    fetchConversations,
    selectConversation,
    createNew,
    removeConversation,
    clearCurrent,
    cancelActiveRequest,
    ask,
  }
})
