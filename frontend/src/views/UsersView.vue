<template>
  <div class="flex flex-col h-full">
    <!-- 顶栏 -->
    <div class="px-6 py-4 border-b border-gray-200 bg-white">
      <h2 class="text-lg font-semibold text-gray-800">用户管理</h2>
      <p class="text-sm text-gray-500">
        {{ auth.isOwner ? '管理所有用户：查看、删除、重置密码、修改角色' : '管理普通用户：查看、删除、重置密码' }}
      </p>
    </div>

    <!-- 用户列表 -->
    <div class="flex-1 overflow-y-auto p-6">
      <div v-if="loading" class="text-center text-gray-400 py-12">加载中...</div>
      <div v-else-if="users.length === 0" class="text-center text-gray-400 py-12">暂无用户</div>

      <div v-else class="overflow-x-auto">
        <table class="w-full">
          <thead>
            <tr class="border-b border-gray-200 text-left text-xs text-gray-500 uppercase tracking-wider">
              <th class="py-3 px-4">用户名</th>
              <th class="py-3 px-4">邮箱</th>
              <th class="py-3 px-4">角色</th>
              <th class="py-3 px-4">注册时间</th>
              <th class="py-3 px-4 text-right">操作</th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="u in users"
              :key="u.id"
              class="border-b border-gray-100 hover:bg-gray-50 transition"
            >
              <td class="py-3 px-4">
                <div class="flex items-center gap-2">
                  <div class="w-8 h-8 rounded-full bg-zhiyuan-100 text-zhiyuan-600 flex items-center justify-center text-xs font-bold">
                    {{ u.username.charAt(0).toUpperCase() }}
                  </div>
                  <span class="font-medium text-gray-800">{{ u.username }}</span>
                  <span v-if="u.id === auth.user.id" class="text-xs text-zhiyuan-500">(你)</span>
                </div>
              </td>
              <td class="py-3 px-4 text-sm text-gray-600">{{ u.email }}</td>
              <td class="py-3 px-4">
                <span class="inline-flex items-center px-2 py-0.5 text-xs rounded-full"
                  :class="roleClass(u.role)">
                  {{ roleLabel(u.role) }}
                </span>
              </td>
              <td class="py-3 px-4 text-sm text-gray-500">{{ formatDate(u.created_at) }}</td>
              <td class="py-3 px-4">
                <div class="flex items-center justify-end gap-1">
                  <!-- 重置密码 -->
                  <button
                    v-if="canResetPassword(u)"
                    @click="handleResetPassword(u)"
                    class="p-2 text-gray-400 hover:text-zhiyuan-600 hover:bg-zhiyuan-50 rounded-lg transition"
                    title="重置密码"
                  >
                    <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 7a2 2 0 012 2m4 0a6 6 0 01-7.743 5.743L11 17H9v2H7v2H4a1 1 0 01-1-1v-2.586a1 1 0 01.293-.707l5.964-5.964A6 6 0 1121 9z" />
                    </svg>
                  </button>
                  <!-- 切换角色（仅站长） -->
                  <button
                    v-if="auth.isOwner && u.role === 'user' && u.id !== auth.user.id"
                    @click="handleToggleRole(u)"
                    class="p-2 text-gray-400 hover:text-amber-600 hover:bg-amber-50 rounded-lg transition"
                    title="提升为管理员"
                  >
                    <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 10l7-7m0 0l7 7m-7-7v18" />
                    </svg>
                  </button>
                  <button
                    v-if="auth.isOwner && u.role === 'admin' && u.id !== auth.user.id"
                    @click="handleToggleRole(u)"
                    class="p-2 text-gray-400 hover:text-gray-600 hover:bg-gray-100 rounded-lg transition"
                    title="降级为普通用户"
                  >
                    <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 14l-7 7m0 0l-7-7m7 7V3" />
                    </svg>
                  </button>
                  <!-- 删除 -->
                  <button
                    v-if="canDelete(u)"
                    @click="handleDelete(u)"
                    class="p-2 text-gray-400 hover:text-red-500 hover:bg-red-50 rounded-lg transition"
                    title="删除用户"
                  >
                    <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                    </svg>
                  </button>
                </div>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <!-- 重置密码弹窗 -->
    <div v-if="resetTarget" class="fixed inset-0 bg-black/40 flex items-center justify-center z-50" @click.self="resetTarget = null">
      <div class="bg-white rounded-2xl shadow-xl p-6 w-96">
        <h3 class="text-lg font-semibold text-gray-800 mb-1">重置密码</h3>
        <p class="text-sm text-gray-500 mb-4">为用户「{{ resetTarget.username }}」设置新密码</p>
        <input
          v-model="newPassword"
          type="password"
          minlength="6"
          placeholder="输入新密码（至少 6 位）"
          class="w-full px-4 py-2.5 border border-gray-300 rounded-lg focus:ring-2 focus:ring-zhiyuan-500 focus:border-transparent outline-none transition mb-4"
        />
        <div class="flex gap-3 justify-end">
          <button @click="resetTarget = null" class="px-4 py-2 text-sm text-gray-600 hover:bg-gray-100 rounded-lg transition">取消</button>
          <button
            @click="confirmResetPassword"
            :disabled="!newPassword || newPassword.length < 6"
            class="px-4 py-2 text-sm bg-zhiyuan-600 text-white rounded-lg hover:bg-zhiyuan-700 disabled:opacity-50 transition"
          >确认重置</button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useAuthStore } from '../stores/auth'
import { listUsers, deleteUser, updateUserRole, resetUserPassword } from '../api'

const auth = useAuthStore()
const users = ref([])
const loading = ref(false)
const resetTarget = ref(null)
const newPassword = ref('')

onMounted(async () => {
  await fetchUsers()
})

async function fetchUsers() {
  loading.value = true
  try {
    users.value = await listUsers()
  } catch (e) {
    alert(e.detail || e.error || '加载失败')
  } finally {
    loading.value = false
  }
}

function canResetPassword(u) {
  if (u.id === auth.user.id) return false
  // 管理员只能重置普通用户；站长可重置所有人（除自己）
  if (auth.isOwner) return true
  return u.role === 'user'
}

function canDelete(u) {
  if (u.id === auth.user.id) return false
  if (auth.isOwner) return u.role !== 'owner'
  return u.role === 'user'
}

async function handleResetPassword(u) {
  resetTarget.value = u
  newPassword.value = ''
}

async function confirmResetPassword() {
  if (!resetTarget.value || !newPassword.value) return
  try {
    await resetUserPassword(resetTarget.value.id, newPassword.value)
    alert(`已重置「${resetTarget.value.username}」的密码`)
    resetTarget.value = null
    newPassword.value = ''
  } catch (e) {
    alert(e.detail || e.error || '重置失败')
  }
}

async function handleToggleRole(u) {
  const newRole = u.role === 'user' ? 'admin' : 'user'
  if (!confirm(`确认将「${u.username}」${newRole === 'admin' ? '提升为管理员' : '降级为普通用户'}？`)) return
  try {
    await updateUserRole(u.id, newRole)
    await fetchUsers()
  } catch (e) {
    alert(e.detail || e.error || '修改角色失败')
  }
}

async function handleDelete(u) {
  if (!confirm(`确认删除用户「${u.username}」？该用户的所有对话也将被删除。`)) return
  try {
    await deleteUser(u.id)
    await fetchUsers()
  } catch (e) {
    alert(e.detail || e.error || '删除失败')
  }
}

function formatDate(iso) {
  if (!iso) return '-'
  const d = new Date(iso)
  return `${d.getFullYear()}/${d.getMonth() + 1}/${d.getDate()}`
}

function roleClass(role) {
  return {
    owner: 'bg-amber-100 text-amber-700',
    admin: 'bg-zhiyuan-100 text-zhiyuan-700',
    user: 'bg-gray-100 text-gray-600',
  }[role] || 'bg-gray-100 text-gray-600'
}

function roleLabel(role) {
  return { owner: '站长', admin: '管理员', user: '普通用户' }[role] || role
}
</script>
