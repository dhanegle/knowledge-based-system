<template>
  <div class="flex flex-col h-full">
    <!-- 顶栏 -->
    <div class="px-6 py-4 border-b border-gray-200 bg-white">
      <h2 class="text-lg font-semibold text-gray-800">对话问答</h2>
      <p class="text-sm text-gray-500">基于知识库的 RAG 问答，回答附带引用来源</p>
    </div>

    <!-- 消息列表 -->
    <div ref="messagesEl" class="flex-1 overflow-y-auto px-6 py-6 space-y-6">
      <div v-if="messages.length === 0" class="text-center text-gray-400 mt-20">
        <svg class="w-16 h-16 mx-auto mb-4 text-zhiyuan-200" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M20 13V6a2 2 0 00-2-2H6a2 2 0 00-2 2v7m16 0v5a2 2 0 01-2 2H6a2 2 0 01-2-2v-5m16 0h-2.586a1 1 0 00-.707.293l-2.414 2.414a1 1 0 01-.707.293h-3.172a1 1 0 01-.707-.293l-2.414-2.414A1 1 0 006.586 13H4" />
        </svg>
        <p>输入问题开始对话</p>
      </div>

      <div v-for="(msg, i) in messages" :key="i" class="space-y-2">
        <!-- 用户消息 -->
        <div v-if="msg.role === 'user'" class="flex justify-end">
          <div class="max-w-2xl px-4 py-3 bg-zhiyuan-600 text-white rounded-2xl rounded-br-sm">
            {{ msg.content }}
          </div>
        </div>

        <!-- AI 消息 -->
        <div v-else class="flex justify-start">
          <div class="max-w-2xl w-full">
            <!-- 引用来源 -->
            <div v-if="msg.sources && msg.sources.length" class="mb-2 flex flex-wrap gap-2">
              <span
                v-for="(src, si) in msg.sources"
                :key="si"
                class="inline-flex items-center gap-1 px-2.5 py-1 bg-zhiyuan-50 text-zhiyuan-700 text-xs rounded-lg border border-zhiyuan-200"
              >
                <svg class="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12" />
                </svg>
                {{ src.filename }}{{ src.page ? ` · 第${src.page}页` : '' }}
                <span class="text-zhiyuan-400">({{ src.score }})</span>
              </span>
            </div>

            <!-- 回答内容 -->
            <div class="px-4 py-3 bg-white border border-gray-200 rounded-2xl rounded-bl-sm">
              <p class="whitespace-pre-wrap text-gray-800">{{ msg.content || '...' }}</p>
            </div>

            <!-- 错误 -->
            <div v-if="msg.error" class="mt-1 text-sm text-red-500">
              {{ msg.error }}
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- 输入框 -->
    <div class="px-6 py-4 border-t border-gray-200 bg-white">
      <form @submit.prevent="handleAsk" class="flex gap-3">
        <input
          v-model="question"
          type="text"
          :disabled="streaming"
          placeholder="输入你的问题..."
          class="flex-1 px-4 py-3 border border-gray-300 rounded-xl focus:ring-2 focus:ring-zhiyuan-500 focus:border-transparent outline-none transition disabled:bg-gray-100"
        />
        <button
          type="submit"
          :disabled="streaming || !question.trim()"
          class="px-6 py-3 bg-zhiyuan-600 text-white rounded-xl hover:bg-zhiyuan-700 disabled:opacity-50 transition font-medium"
        >
          {{ streaming ? '回答中...' : '发送' }}
        </button>
      </form>
    </div>
  </div>
</template>

<script setup>
import { ref, nextTick, reactive } from 'vue'
import { getToken } from '../api'

const messages = ref([])
const question = ref('')
const streaming = ref(false)
const messagesEl = ref(null)

function scrollToBottom() {
  nextTick(() => {
    if (messagesEl.value) {
      messagesEl.value.scrollTop = messagesEl.value.scrollHeight
    }
  })
}

async function handleAsk() {
  const q = question.value.trim()
  if (!q || streaming.value) return

  messages.value.push({ role: 'user', content: q })
  question.value = ''
  scrollToBottom()

  streaming.value = true
  const aiMsg = reactive({ role: 'assistant', content: '', sources: [], error: '' })
  messages.value.push(aiMsg)
  scrollToBottom()

  try {
    const token = getToken()
    const url = `/api/ask?q=${encodeURIComponent(q)}`
    const resp = await fetch(url, {
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    })

    const reader = resp.body.getReader()
    const decoder = new TextDecoder()
    let buffer = ''

    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true })

      const lines = buffer.split('\n')
      buffer = lines.pop()

      for (const line of lines) {
        if (line.startsWith('data:')) {
          const data = line.slice(5).trim()
          if (!data) continue
          try {
            const parsed = JSON.parse(data)
            // 判断事件类型
            if (parsed.sources) {
              aiMsg.sources = parsed.sources
            } else if (parsed.text) {
              aiMsg.content += parsed.text
              scrollToBottom()
            } else if (parsed.ok === false) {
              aiMsg.error = parsed.error || '请求失败'
            }
          } catch {
            // 非 JSON 数据，跳过
          }
        }
      }
    }
  } catch (e) {
    aiMsg.error = '网络错误，请稍后重试'
  } finally {
    streaming.value = false
  }
}
</script>
