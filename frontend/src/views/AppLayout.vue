<template>
  <div class="flex h-screen bg-paper">
    <!-- 侧边栏 -->
    <aside class="flex w-[262px] flex-shrink-0 flex-col bg-ink-900">
      <!-- 品牌 -->
      <div class="px-5 pb-4 pt-5">
        <div class="flex items-center gap-2.5">
          <h1 class="font-serif text-[22px] leading-none tracking-tight text-ink-50">知源</h1>
          <span class="h-1.5 w-1.5 rounded-full bg-seal-500"></span>
        </div>
        <p class="mt-2 text-[10.5px] uppercase tracking-caps text-ink-500">Knowledge Base</p>
      </div>

      <div class="mx-5 h-px bg-ink-800/70"></div>

      <!-- 主导航 -->
      <nav class="space-y-0.5 px-3 py-3">
        <router-link
          v-for="item in navItems"
          :key="item.name"
          :to="item.to"
          class="group flex items-center gap-2.5 rounded-md px-3 py-2 text-[13px] transition-colors duration-150"
          :class="isActive(item.name)
            ? 'bg-ink-800 text-ink-50'
            : 'text-ink-400 hover:bg-ink-800/50 hover:text-ink-200'"
        >
          <svg
            class="h-[17px] w-[17px] flex-shrink-0 transition-colors"
            :class="isActive(item.name) ? 'text-seal-400' : 'text-ink-500 group-hover:text-ink-400'"
            fill="none" stroke="currentColor" stroke-width="1.6" viewBox="0 0 24 24"
          >
            <path stroke-linecap="round" stroke-linejoin="round" :d="item.icon" />
          </svg>
          <span>{{ item.label }}</span>
        </router-link>
      </nav>

      <!-- 对话历史 -->
      <div class="mt-1 flex min-h-0 flex-1 flex-col">
        <div class="flex items-center justify-between px-5 pb-2">
          <span class="caps !text-ink-600">对话历史</span>
          <span v-if="convStore.conversations.length" class="text-[11px] tabular-nums text-ink-600">
            {{ convStore.conversations.length }}
          </span>
        </div>

        <div class="min-h-0 flex-1 overflow-y-auto px-3 pb-3">
          <p v-if="!convStore.conversations.length" class="px-3 py-2 text-[12.5px] text-ink-600">
            暂无对话记录
          </p>

          <div
            v-for="conv in convStore.conversations"
            :key="conv.id"
            class="group flex cursor-pointer items-center gap-2 rounded-md px-3 py-[7px] transition-colors duration-150"
            :class="convStore.currentId === conv.id
              ? 'bg-ink-800/80 text-ink-100'
              : 'text-ink-400 hover:bg-ink-800/40 hover:text-ink-200'"
            @click="selectConv(conv.id)"
          >
            <span
              class="h-1 w-1 flex-shrink-0 rounded-full transition-colors"
              :class="convStore.currentId === conv.id ? 'bg-seal-500' : 'bg-ink-700 group-hover:bg-ink-600'"
            ></span>
            <span class="min-w-0 flex-1 truncate text-[12.5px]">{{ conv.title }}</span>
            <button
              class="flex-shrink-0 text-ink-600 opacity-0 transition-all hover:text-seal-400 group-hover:opacity-100"
              title="删除对话"
              @click.stop="deleteConv(conv.id)"
            >
              <svg class="h-3.5 w-3.5" fill="none" stroke="currentColor" stroke-width="1.6" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          </div>
        </div>
      </div>

      <!-- 用户信息 -->
      <div class="border-t border-ink-800/70 p-3">
        <div class="flex items-center gap-2.5 rounded-md px-2 py-1.5">
          <div class="flex h-7 w-7 flex-shrink-0 items-center justify-center rounded border border-ink-700 font-serif text-[12px] text-ink-300">
            {{ auth.user?.username?.charAt(0)?.toUpperCase() || '?' }}
          </div>
          <div class="min-w-0 flex-1">
            <p class="truncate text-[13px] text-ink-200">{{ auth.user?.username || '未登录' }}</p>
            <p class="text-[11px] text-ink-500">{{ roleLabel }}</p>
          </div>
          <button
            class="flex-shrink-0 rounded p-1.5 text-ink-600 transition-colors hover:bg-ink-800 hover:text-ink-300"
            title="退出登录"
            @click="handleLogout"
          >
            <svg class="h-4 w-4" fill="none" stroke="currentColor" stroke-width="1.6" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" d="M15 12H4m0 0l3.5-3.5M4 12l3.5 3.5M11 5h6a2 2 0 012 2v10a2 2 0 01-2 2h-6" />
            </svg>
          </button>
        </div>
      </div>
    </aside>

    <!-- 主内容区 -->
    <main class="min-w-0 flex-1 overflow-hidden">
      <router-view />
    </main>
  </div>
</template>

<script setup>
import { computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '../stores/auth'
import { useConversationStore } from '../stores/conversations'

const auth = useAuthStore()
const convStore = useConversationStore()
const router = useRouter()

// 图标路径集中管理，模板只负责布局
const ICONS = {
  chat: 'M8 10h8M8 14h5M5 19h14a1 1 0 001-1V7a2 2 0 00-2-2H6a2 2 0 00-2 2v10l1 2z',
  docs: 'M9 3h6l4 4v12a2 2 0 01-2 2H7a2 2 0 01-2-2V5a2 2 0 012-2h2zm5 1.5V8h3.5M9 13h6M9 17h4',
  users: 'M16 19v-1.5a4 4 0 00-4-4H7a4 4 0 00-4 4V19M9.5 9.5a3 3 0 100-6 3 3 0 000 6zM21 19v-1.5a4 4 0 00-3-3.87M16.5 3.62a4 4 0 010 7.75',
}

const navItems = computed(() => {
  const items = [{ name: 'chat', to: '/', label: '对话问答', icon: ICONS.chat }]
  if (auth.isAdmin) {
    items.push({ name: 'documents', to: '/documents', label: '文档管理', icon: ICONS.docs })
    items.push({ name: 'users', to: '/users', label: '用户管理', icon: ICONS.users })
  }
  return items
})

const roleLabel = computed(() => {
  if (auth.isOwner) return '站长'
  if (auth.isAdmin) return '管理员'
  return '普通用户'
})

function isActive(name) {
  return router.currentRoute.value.name === name
}

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
