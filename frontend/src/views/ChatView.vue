<template>
  <div class="flex h-full flex-col">
    <!-- 页头 -->
    <header class="page-head">
      <div>
        <h2 class="page-title">对话问答</h2>
        <p class="page-sub">基于知识库检索作答，回答附带引用来源</p>
      </div>
      <button class="btn btn-md btn-outline" @click="handleNewConversation">
        <svg class="h-3.5 w-3.5" fill="none" stroke="currentColor" stroke-width="1.8" viewBox="0 0 24 24">
          <path stroke-linecap="round" d="M12 5v14M5 12h14" />
        </svg>
        新对话
      </button>
    </header>

    <!-- 消息区 -->
    <div ref="messagesEl" class="min-h-0 flex-1 overflow-y-auto">
      <div class="mx-auto max-w-3xl px-8 py-8">
        <!-- 空态 -->
        <div v-if="store.messages.length === 0" class="flex flex-col items-center pb-16 pt-24 text-center">
          <div class="flex h-12 w-12 items-center justify-center rounded-lg border border-ink-200 bg-white">
            <svg class="h-5 w-5 text-ink-300" fill="none" stroke="currentColor" stroke-width="1.4" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" d="M8 10h8M8 14h5M5 19h14a1 1 0 001-1V7a2 2 0 00-2-2H6a2 2 0 00-2 2v10l1 2z" />
            </svg>
          </div>
          <p class="mt-4 font-serif text-[16px] text-ink-800">开始一次提问</p>
          <p class="mt-1.5 max-w-xs text-[13px] leading-relaxed text-ink-500">
            回答仅依据已上传的文档生成，若知识库中没有相关内容会如实告知。
          </p>
        </div>

        <!-- 消息列表 -->
        <div v-else class="space-y-7">
          <template v-for="(msg, i) in store.messages" :key="i">
            <!-- 用户 -->
            <div v-if="msg.role === 'user'" class="flex justify-end">
              <div class="max-w-[85%] whitespace-pre-wrap rounded-lg rounded-br-sm bg-ink-100 px-4 py-2.5 text-[15px] leading-relaxed text-ink-900">
                {{ msg.content }}
              </div>
            </div>

            <!-- 助手 -->
            <div v-else class="flex gap-3.5">
              <div class="mt-0.5 flex h-6 w-6 flex-shrink-0 select-none items-center justify-center rounded border border-ink-200 bg-white font-serif text-[11px] text-ink-500">
                知
              </div>

              <div class="min-w-0 flex-1">
                <!-- 检索中 -->
                <div v-if="store.streaming && !msg.content && !msg.error" class="flex items-center gap-2 pt-0.5">
                  <span class="flex gap-1">
                    <span class="h-1.5 w-1.5 animate-breathe rounded-full bg-ink-400"></span>
                    <span class="h-1.5 w-1.5 animate-breathe rounded-full bg-ink-400" style="animation-delay: 200ms"></span>
                    <span class="h-1.5 w-1.5 animate-breathe rounded-full bg-ink-400" style="animation-delay: 400ms"></span>
                  </span>
                  <span class="text-[13px] text-ink-400">检索并组织回答…</span>
                </div>

                <!-- 正文 -->
                <div v-else-if="msg.content" class="prose-chat">
                  <span v-html="renderMarkdown(msg.content)"></span><span
                    v-if="store.streaming && i === store.messages.length - 1"
                    class="ml-0.5 inline-block h-[15px] w-[2px] translate-y-[3px] animate-pulse bg-seal-500"
                  ></span>
                </div>

                <!-- 错误 -->
                <p v-if="msg.error" class="mt-1 flex items-start gap-1.5 text-[13px] text-seal-700">
                  <svg class="mt-0.5 h-3.5 w-3.5 flex-shrink-0" fill="none" stroke="currentColor" stroke-width="1.7" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" d="M12 8v5m0 3h.01M10.3 3.9L2.4 17.5A2 2 0 004.1 20.5h15.8a2 2 0 001.7-3L13.7 3.9a2 2 0 00-3.4 0z" />
                  </svg>
                  {{ msg.error }}
                </p>

                <!-- 引用来源 -->
                <div v-if="msg.sources?.length" class="mt-4 border-t border-ink-200/80 pt-3">
                  <p class="caps mb-2">引用来源 · {{ msg.sources.length }}</p>
                  <div class="grid gap-1.5 sm:grid-cols-2">
                    <div
                      v-for="(s, si) in msg.sources"
                      :key="si"
                      class="rounded-md border border-ink-200/80 bg-white px-3 py-2 transition-colors hover:border-ink-300"
                      :title="s.text_preview"
                    >
                      <div class="flex items-baseline gap-2">
                        <span class="font-mono text-[10px] tabular-nums text-ink-400">{{ si + 1 }}</span>
                        <span class="truncate text-[12.5px] font-medium text-ink-800">{{ s.filename }}</span>
                      </div>
                      <div class="mt-1 flex items-center gap-2 text-[11px] text-ink-400">
                        <span>第 {{ s.page }} 页</span>
                        <span class="h-3 w-px bg-ink-200"></span>
                        <span class="tabular-nums">匹配 {{ s.score.toFixed(2) }}</span>
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </template>
        </div>
      </div>
    </div>

    <!-- 输入区 -->
    <div class="border-t border-ink-200/80 bg-paper px-8 py-4">
      <form class="mx-auto max-w-3xl" @submit.prevent="handleAsk">
        <div class="flex items-end gap-2 rounded-lg border border-ink-200 bg-white p-1.5 shadow-hairline transition-colors focus-within:border-ink-400 focus-within:ring-2 focus-within:ring-ink-900/[0.06]">
          <textarea
            ref="questionEl"
            v-model="question"
            rows="1"
            :disabled="store.streaming"
            placeholder="输入你的问题…"
            class="max-h-40 flex-1 resize-none border-0 bg-transparent px-2.5 py-2 text-[15px] leading-relaxed text-ink-900 outline-none placeholder:text-ink-400 focus-visible:ring-0 disabled:opacity-60"
            @keydown="onKeydown"
            @input="autoGrow"
          ></textarea>

          <button
            v-if="store.streaming"
            type="button"
            class="btn btn-sm btn-outline flex-shrink-0"
            @click="store.cancelActiveRequest()"
          >
            <span class="h-2 w-2 rounded-[1px] bg-ink-500"></span>
            停止
          </button>
          <button
            v-else
            type="submit"
            class="btn btn-sm btn-primary h-9 flex-shrink-0 px-3.5"
            :disabled="!question.trim()"
          >
            发送
            <svg class="h-3.5 w-3.5" fill="none" stroke="currentColor" stroke-width="1.8" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" d="M5 12h13m0 0l-5-5m5 5l-5 5" />
            </svg>
          </button>
        </div>
        <p class="mt-2 text-center text-[11.5px] text-ink-400">
          Enter 发送 · Shift + Enter 换行
        </p>
      </form>
    </div>
  </div>
</template>

<script setup>
import { ref, nextTick, onMounted, watch } from 'vue'
import { marked } from 'marked'
import DOMPurify from 'dompurify'
import { useConversationStore } from '../stores/conversations'

const store = useConversationStore()
const question = ref('')
const questionEl = ref(null)
const messagesEl = ref(null)

marked.setOptions({ breaks: true, gfm: true })

function renderMarkdown(text) {
  try {
    return DOMPurify.sanitize(marked.parse(text), { USE_PROFILES: { html: true } })
  } catch {
    return DOMPurify.sanitize(text, { USE_PROFILES: { html: true } })
  }
}

function scrollToBottom() {
  nextTick(() => {
    if (messagesEl.value) {
      messagesEl.value.scrollTop = messagesEl.value.scrollHeight
    }
  })
}

// 输入框随内容增高，上限由 max-h 控制
function autoGrow() {
  const el = questionEl.value
  if (!el) return
  el.style.height = 'auto'
  el.style.height = `${Math.min(el.scrollHeight, 160)}px`
}

function onKeydown(e) {
  // isComposing：中文输入法选词时的回车不应触发发送
  if (e.key === 'Enter' && !e.shiftKey && !e.isComposing) {
    e.preventDefault()
    handleAsk()
  }
}

function resetComposer() {
  question.value = ''
  nextTick(() => {
    if (questionEl.value) questionEl.value.style.height = 'auto'
  })
}

onMounted(async () => {
  if (store.conversations.length === 0) {
    await store.fetchConversations()
  }
  if (!store.currentId && !store.streaming && store.conversations.length > 0) {
    await store.selectConversation(store.conversations[0].id)
  }
  scrollToBottom()
})

watch(() => store.messages.length, scrollToBottom)
watch(
  () => store.messages.at(-1)?.content,
  () => { if (store.streaming) scrollToBottom() }
)
watch(() => store.currentId, scrollToBottom)

async function handleNewConversation() {
  await store.createNew()
  scrollToBottom()
}

async function handleAsk() {
  const q = question.value.trim()
  if (!q || store.streaming) return
  resetComposer()
  scrollToBottom()
  store.ask(q)
}
</script>
