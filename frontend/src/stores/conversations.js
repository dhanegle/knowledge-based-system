import { defineStore } from 'pinia'
import { ref } from 'vue'
import {
  listConversations,
  getConversation,
  createConversation,
  deleteConversation as apiDeleteConv,
} from '../api'

export const useConversationStore = defineStore('conversations', () => {
  const conversations = ref([])
  const currentId = ref(null)
  const messages = ref([])
  const loading = ref(false)

  async function fetchConversations() {
    loading.value = true
    try {
      conversations.value = await listConversations()
    } finally {
      loading.value = false
    }
  }

  async function selectConversation(id) {
    if (currentId.value === id && messages.value.length) return
    currentId.value = id
    const data = await getConversation(id)
    messages.value = (data.messages || []).map(m => ({
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
    messages.value = []
    return data
  }

  async function removeConversation(id) {
    await apiDeleteConv(id)
    conversations.value = conversations.value.filter(c => c.id !== id)
    if (currentId.value === id) {
      currentId.value = null
      messages.value = []
    }
  }

  function clearCurrent() {
    currentId.value = null
    messages.value = []
  }

  return {
    conversations,
    currentId,
    messages,
    loading,
    fetchConversations,
    selectConversation,
    createNew,
    removeConversation,
    clearCurrent,
  }
})
