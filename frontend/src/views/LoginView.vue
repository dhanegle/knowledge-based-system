<template>
  <div class="flex min-h-screen bg-paper">
    <!-- 品牌侧 -->
    <aside class="relative hidden w-[44%] flex-col justify-between bg-ink-900 p-12 lg:flex">
      <div>
        <div class="flex items-center gap-2.5">
          <span class="font-serif text-[22px] leading-none tracking-tight text-ink-50">知源</span>
          <span class="h-1.5 w-1.5 rounded-full bg-seal-500"></span>
        </div>
        <p class="mt-2 text-[10.5px] uppercase tracking-caps text-ink-500">Knowledge Base</p>
      </div>

      <div>
        <h2 class="font-serif text-[30px] leading-[1.45] text-ink-50">
          把散落的文档，<br />变成可检索的答案。
        </h2>
        <p class="mt-5 max-w-sm text-[13.5px] leading-relaxed text-ink-400">
          上传办公文档与技术资料，提问时基于原文检索作答，回答附带引用来源。
        </p>
      </div>

      <p class="text-[10.5px] uppercase tracking-caps text-ink-600">Self-hosted · RAG</p>
    </aside>

    <!-- 表单侧 -->
    <div class="flex flex-1 items-center justify-center px-6 py-12">
      <div class="w-full max-w-[352px]">
        <!-- 小屏品牌 -->
        <div class="mb-10 lg:hidden">
          <span class="font-serif text-[20px] tracking-tight text-ink-900">知源</span>
          <span class="ml-2 inline-block h-1.5 w-1.5 rounded-full bg-seal-500"></span>
        </div>

        <h1 class="font-serif text-[23px] text-ink-900">登录</h1>
        <p class="mt-1.5 text-[13px] text-ink-500">使用用户名或邮箱继续</p>

        <form class="mt-8 space-y-4" @submit.prevent="handleSubmit">
          <div>
            <label class="mb-1.5 block text-[12.5px] font-medium text-ink-700">用户名 / 邮箱</label>
            <input v-model="form.username" type="text" required class="input" placeholder="输入用户名或邮箱" />
          </div>
          <div>
            <label class="mb-1.5 block text-[12.5px] font-medium text-ink-700">密码</label>
            <input v-model="form.password" type="password" required class="input" placeholder="输入密码" />
          </div>

          <p v-if="error" class="flex items-start gap-1.5 text-[12.5px] text-seal-700">
            <svg class="mt-0.5 h-3.5 w-3.5 flex-shrink-0" fill="none" stroke="currentColor" stroke-width="1.7" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" d="M12 8v5m0 3h.01M10.3 3.9L2.4 17.5A2 2 0 004.1 20.5h15.8a2 2 0 001.7-3L13.7 3.9a2 2 0 00-3.4 0z" />
            </svg>
            {{ error }}
          </p>

          <button type="submit" class="btn btn-md btn-primary w-full !h-10" :disabled="loading">
            {{ loading ? '登录中…' : '登录' }}
          </button>
        </form>

        <p class="mt-7 text-[13px] text-ink-500">
          还没有账号？
          <router-link to="/register" class="font-medium text-seal-700 underline underline-offset-2 hover:text-seal-800">注册</router-link>
        </p>
      </div>
    </div>
  </div>
</template>

<script setup>
import { reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '../stores/auth'

const auth = useAuthStore()
const router = useRouter()

const form = reactive({ username: '', password: '' })
const loading = ref(false)
const error = ref('')

async function handleSubmit() {
  loading.value = true
  error.value = ''
  try {
    await auth.login(form.username, form.password)
    router.push({ name: 'chat' })
  } catch (e) {
    error.value = e.detail || e.error || '登录失败'
  } finally {
    loading.value = false
  }
}
</script>
