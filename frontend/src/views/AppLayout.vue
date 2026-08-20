<template>
  <div class="flex h-screen bg-gray-50">
    <!-- 侧边栏 -->
    <aside class="w-64 bg-zhiyuan-800 text-white flex flex-col">
      <!-- Logo -->
      <div class="px-6 py-5 border-b border-zhiyuan-700">
        <h1 class="text-xl font-bold tracking-wide">知源</h1>
        <p class="text-xs text-zhiyuan-300 mt-1">知识库问答系统</p>
      </div>

      <!-- 导航 -->
      <nav class="py-4 px-3 space-y-1">
        <router-link
          to="/"
          class="flex items-center gap-3 px-3 py-2.5 rounded-lg transition-colors"
          :class="$route.name === 'chat' ? 'bg-zhiyuan-600 text-white' : 'text-zhiyuan-200 hover:bg-zhiyuan-700'"
        >
          <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 12h8M8 16h5m-6-8h7a2 2 0 012 2v8a2 2 0 01-2 2H6a2 2 0 01-2-2V8a2 2 0 012-2z" />
          </svg>
          对话问答
        </router-link>
        <router-link
          to="/documents"
          class="flex items-center gap-3 px-3 py-2.5 rounded-lg transition-colors"
          :class="$route.name === 'documents' ? 'bg-zhiyuan-600 text-white' : 'text-zhiyuan-200 hover:bg-zhiyuan-700'"
        >
          <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
          </svg>
          文档管理
        </router-link>
      </nav>

      <!-- 对话列表 -->
      <div class="flex-1 overflow-y-auto px-3" v-if="convStore.conversations.length">
        <div class="text-xs text-zhiyuan-400 px-3 py-2 uppercase tracking-wider">对话历史</div>
        <div class="space-y-0.5">
          <div
            v-for="conv in convStore.conversations"
            :key="conv.id"
            class="group flex items-center gap-2 px-3 py-2 rounded-lg cursor-pointer transition-colors"
            :class="convStore.currentId === conv.id ? 'bg-zhiyuan-600 text-white' : 'text-zhiyuan-200 hover:bg-zhiyuan-700'"
            @click="selectConv(conv.id)"
          >
            <svg class="w-4 h-4 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 12h8M8 16h5m-6-8h7a2 2 0 012 2v8a2 2 0 01-2 2H6a2 2 0 01-2-2V8a2 2 0 012-2z" />
            </svg>
            <span class="flex-1 text-sm truncate">{{ conv.title }}</span>
            <button
              @click.stop="deleteConv(conv.id)"
              class="opacity-0 group-hover:opacity-100 text-zhiyuan-300 hover:text-red-400 transition-opacity"
            >
              <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
              </svg>
            </button>
          </div>
        </div>
      </div>

      <!-- 用户信息 -->
      <div class="p-4 border-t border-zhiyuan-700">
        <div class="flex items-center gap-3 mb-3">
          <div class="w-8 h-8 rounded-full bg-zhiyuan-500 flex items-center justify-center text-sm font-bold">
            {{ auth.user?.username?.charAt(0).toUpperCase() || '?' }}
          </div>
          <span class="text-sm text-zhiyuan-200">{{ auth.user?.username || '未登录' }}</span>
        </div>
        <button
          @click="handleLogout"
          class="w-full px-3 py-2 text-sm text-zhiyuan-200 hover:bg-zhiyuan-700 rounded-lg transition-colors"
        >
          退出登录
        </button>
      </div>
    </aside>

    <!-- 主内容区 -->
    <main class="flex-1 overflow-hidden">
      <router-view />
    </main>
  </div>
</template>

<script setup>
import { onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '../stores/auth'
import { useConversationStore } from '../stores/conversations'

const auth = useAuthStore()
const convStore = useConversationStore()
const router = useRouter()

onMounted(async () => {
  await auth.fetchMe()
  await convStore.fetchConversations()
})

function selectConv(id) {
  convStore.selectConversation(id)
  if (router.currentRoute.value.name !== 'chat') {
    router.push({ name: 'chat' })
  }
}

async function deleteConv(id) {
  if (!confirm('确认删除此对话？')) return
  await convStore.removeConversation(id)
}

function handleLogout() {
  auth.logout()
  router.push({ name: 'login' })
}
</script>
