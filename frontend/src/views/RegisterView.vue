<template>
  <div class="min-h-screen flex items-center justify-center bg-gradient-to-br from-zhiyuan-50 to-zhiyuan-100">
    <div class="w-full max-w-md p-8 bg-white rounded-2xl shadow-lg">
      <div class="text-center mb-8">
        <h1 class="text-3xl font-bold text-zhiyuan-700">注册</h1>
        <p class="text-gray-500 mt-2">创建知源账号</p>
      </div>

      <form @submit.prevent="handleSubmit" class="space-y-4">
        <div>
          <label class="block text-sm font-medium text-gray-700 mb-1">用户名</label>
          <input
            v-model="form.username"
            type="text"
            required
            minlength="2"
            class="w-full px-4 py-2.5 border border-gray-300 rounded-lg focus:ring-2 focus:ring-zhiyuan-500 focus:border-transparent outline-none transition"
            placeholder="至少 2 个字符"
          />
        </div>
        <div>
          <label class="block text-sm font-medium text-gray-700 mb-1">邮箱</label>
          <input
            v-model="form.email"
            type="email"
            required
            class="w-full px-4 py-2.5 border border-gray-300 rounded-lg focus:ring-2 focus:ring-zhiyuan-500 focus:border-transparent outline-none transition"
            placeholder="your@example.com"
          />
        </div>
        <div>
          <label class="block text-sm font-medium text-gray-700 mb-1">密码</label>
          <input
            v-model="form.password"
            type="password"
            required
            minlength="6"
            class="w-full px-4 py-2.5 border border-gray-300 rounded-lg focus:ring-2 focus:ring-zhiyuan-500 focus:border-transparent outline-none transition"
            placeholder="至少 6 个字符"
          />
        </div>

        <p v-if="error" class="text-sm text-red-500">{{ error }}</p>

        <button
          type="submit"
          :disabled="loading"
          class="w-full py-2.5 bg-zhiyuan-600 text-white rounded-lg hover:bg-zhiyuan-700 disabled:opacity-50 transition font-medium"
        >
          {{ loading ? '注册中...' : '注册' }}
        </button>
      </form>

      <p class="text-center text-sm text-gray-500 mt-6">
        已有账号？
        <router-link to="/login" class="text-zhiyuan-600 hover:underline font-medium">登录</router-link>
      </p>
    </div>
  </div>
</template>

<script setup>
import { reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '../stores/auth'

const auth = useAuthStore()
const router = useRouter()

const form = reactive({ username: '', email: '', password: '' })
const loading = ref(false)
const error = ref('')

async function handleSubmit() {
  loading.value = true
  error.value = ''
  try {
    await auth.register(form.username, form.email, form.password)
    router.push({ name: 'chat' })
  } catch (e) {
    error.value = e.detail || e.error || '注册失败'
  } finally {
    loading.value = false
  }
}
</script>
