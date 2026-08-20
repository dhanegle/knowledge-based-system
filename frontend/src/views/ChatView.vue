<template>
  <div class="flex flex-col h-full">
    <!-- 顶栏 -->
    <div class="px-6 py-4 border-b border-gray-200 bg-white flex items-center justify-between">
      <div>
        <h2 class="text-lg font-semibold text-gray-800">对话问答</h2>
        <p class="text-sm text-gray-500">基于知识库的 RAG 问答，回答附带引用来源</p>
      </div>
      <button
        @click="handleNewConversation"
        class="px-4 py-2 text-sm bg-zhiyuan-600 text-white rounded-lg hover:bg-zhiyuan-700 transition flex items-center gap-1.5"
      >
        <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 4v16m8-8H4" />
        </svg>
        新对话
      </button>
    </div>

    <!-- 消息列表 -->
    <div ref="messagesEl" class="flex-1 overflow-y-auto px-6 py-6 space-y-6">
      <div v-if="store.messages.length === 0" class="text-center text-gray-400 mt-20">
        <svg class="w-16 h-16 mx-auto mb-4 text-zhiyuan-200" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M20 13V6a2 2 0 00-2-2H6a2 2 0 00-2 2v7m16 0v5a2 2 0 01-2 2H6a2 2 0 01-2-2v-5m16 0h-2.586a1 1 0 00-.707.293l-2.414 2.414a1 1 0 01-.707.293h-3.172a1 1 0 01-.707-.293l-2.414-2.414A1 1 0 006.586 13H4" />
        </svg>
        <p>输入问题开始对话</p>
      </div>

      <div v-for="(msg, i) in store.messages" :key="i" class="space-y-2">
        <!-- 用户消息 -->
        <div v-if="msg.role === 'user'" class="flex justify-end">
          <div class="max-w-2xl px-4 py-3 bg-zhiyuan-600 text-white rounded-2xl rounded-br-sm">
            {{ msg.content }}
          </div>
        </div>

        <!-- AI 消息 -->
        <div v-else class="flex justify-start">
          <div class="max-w-2xl">
            <!-- 回答内容 -->
            <div class="inline-block px-4 py-3 bg-white border border-gray-200 rounded-2xl rounded-bl-sm">
              <!-- 思考动画 -->
              <div v-if="store.streaming && !msg.content && !msg.error" class="flex items-center gap-2 py-1">
                <div class="flex gap-1">
                  <span class="w-2 h-2 bg-zhiyuan-400 rounded-full animate-bounce" style="animation-delay: 0ms"></span>
                  <span class="w-2 h-2 bg-zhiyuan-400 rounded-full animate-bounce" style="animation-delay: 150ms"></span>
                  <span class="w-2 h-2 bg-zhiyuan-400 rounded-full animate-bounce" style="animation-delay: 300ms"></span>
                </div>
                <span class="text-sm text-gray-400">思考中...</span>
              </div>
              <!-- Markdown 渲染的回答 -->
              <div
                v-else-if="msg.content"
                class="prose-chat text-gray-800"
              >
                <span v-html="renderMarkdown(msg.content)"></span><span v-if="store.streaming && i === store.messages.length - 1" class="inline-block w-0.5 h-4 bg-zhiyuan-500 animate-pulse align-middle ml-0.5"></span>
              </div>
              <p v-else-if="msg.error" class="text-red-500 text-sm">{{ msg.error }}</p>
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
          :disabled="store.streaming"
          placeholder="输入你的问题..."
          class="flex-1 px-4 py-3 border border-gray-300 rounded-xl focus:ring-2 focus:ring-zhiyuan-500 focus:border-transparent outline-none transition disabled:bg-gray-100"
        />
        <button
          type="submit"
          :disabled="store.streaming || !question.trim()"
          class="px-6 py-3 bg-zhiyuan-600 text-white rounded-xl hover:bg-zhiyuan-700 disabled:opacity-50 transition font-medium"
        >
          {{ store.streaming ? '回答中...' : '发送' }}
        </button>
      </form>
    </div>
  </div>
</template>

<script setup>
import { ref, nextTick, onMounted, watch } from 'vue'
import { marked } from 'marked'
import { useConversationStore } from '../stores/conversations'

const store = useConversationStore()
const question = ref('')
const messagesEl = ref(null)

// 配置 marked：关闭 mangle，简化输出
marked.setOptions({
  breaks: true,
  gfm: true,
})

function renderMarkdown(text) {
  try {
    return marked.parse(text)
  } catch {
    return text
  }
}

function scrollToBottom() {
  nextTick(() => {
    if (messagesEl.value) {
      messagesEl.value.scrollTop = messagesEl.value.scrollHeight
    }
  })
}

onMounted(async () => {
  // 只在 store 为空时才加载对话列表（首次进入）
  // 切页面回来时不重新加载，避免覆盖正在流式 / 已加载的消息
  if (store.conversations.length === 0) {
    await store.fetchConversations()
  }
  // 仅当没有选中对话且不在流式中时，才选第一个对话
  if (!store.currentId && !store.streaming && store.conversations.length > 0) {
    await store.selectConversation(store.conversations[0].id)
  }
  scrollToBottom()
})

// 流式期间消息增长时自动滚到底部
watch(() => store.messages.length, () => {
  scrollToBottom()
})
watch(
  () => store.messages.at(-1)?.content,
  () => {
    if (store.streaming) scrollToBottom()
  }
)
// 切换对话时滚到底部
watch(
  () => store.currentId,
  () => {
    scrollToBottom()
  }
)

async function handleNewConversation() {
  await store.createNew()
  scrollToBottom()
}

async function handleAsk() {
  const q = question.value.trim()
  if (!q || store.streaming) return
  question.value = ''
  scrollToBottom()
  // 发送后让 store 在后台流式接收，组件不阻塞
  store.ask(q)
}
</script>

<style>
/* Markdown 渲染样式 */
.prose-chat {
  line-height: 1.7;
}
.prose-chat p {
  margin: 0.5em 0;
}
.prose-chat h1, .prose-chat h2, .prose-chat h3, .prose-chat h4 {
  font-weight: 600;
  margin: 0.8em 0 0.4em;
  line-height: 1.3;
}
.prose-chat h1 { font-size: 1.3em; }
.prose-chat h2 { font-size: 1.2em; }
.prose-chat h3 { font-size: 1.1em; }
.prose-chat h4 { font-size: 1em; }
.prose-chat ul, .prose-chat ol {
  margin: 0.4em 0;
  padding-left: 1.5em;
}
.prose-chat li {
  margin: 0.2em 0;
}
.prose-chat ul li {
  list-style: disc;
}
.prose-chat ol li {
  list-style: decimal;
}
.prose-chat strong {
  font-weight: 600;
}
.prose-chat code {
  background: #f3f4f6;
  padding: 0.1em 0.3em;
  border-radius: 3px;
  font-size: 0.9em;
  font-family: monospace;
}
.prose-chat pre {
  background: #1e293b;
  color: #e2e8f0;
  padding: 0.8em;
  border-radius: 6px;
  overflow-x: auto;
  margin: 0.5em 0;
}
.prose-chat pre code {
  background: none;
  padding: 0;
  color: inherit;
}
.prose-chat blockquote {
  border-left: 3px solid #93c5fd;
  padding-left: 0.8em;
  margin: 0.5em 0;
  color: #6b7280;
}
.prose-chat table {
  border-collapse: collapse;
  margin: 0.5em 0;
}
.prose-chat th, .prose-chat td {
  border: 1px solid #e5e7eb;
  padding: 0.4em 0.7em;
  text-align: left;
}
.prose-chat th {
  background: #f9fafb;
  font-weight: 600;
}
</style>
