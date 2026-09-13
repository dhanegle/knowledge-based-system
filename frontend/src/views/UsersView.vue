<template>
  <div class="flex h-full flex-col">
    <!-- 页头 -->
    <header class="page-head">
      <div>
        <h2 class="page-title">用户管理</h2>
        <p class="page-sub">
          {{ auth.isOwner ? '管理所有用户：查看、删除、重置密码、修改角色' : '管理普通用户：查看、删除、重置密码' }}
        </p>
      </div>
      <span v-if="users.length" class="caps">{{ users.length }} 位成员</span>
    </header>

    <div class="min-h-0 flex-1 overflow-y-auto">
      <div class="mx-auto max-w-4xl px-8 py-6">
        <div v-if="loading" class="py-16 text-center text-[13.5px] text-ink-400">加载中…</div>
        <div v-else-if="users.length === 0" class="py-16 text-center text-[13.5px] text-ink-400">暂无用户</div>

        <div v-else class="card overflow-hidden">
          <table class="w-full">
            <thead>
              <tr class="border-b border-ink-200/80">
                <th class="caps px-4 py-2.5 text-left font-medium">用户名</th>
                <th class="caps px-4 py-2.5 text-left font-medium">邮箱</th>
                <th class="caps px-4 py-2.5 text-left font-medium">角色</th>
                <th class="caps px-4 py-2.5 text-left font-medium">注册时间</th>
                <th class="px-4 py-2.5"></th>
              </tr>
            </thead>
            <tbody class="divide-y divide-ink-200/70">
              <tr v-for="u in users" :key="u.id" class="group transition-colors hover:bg-ink-50/70">
                <td class="px-4 py-3">
                  <div class="flex items-center gap-2.5">
                    <div class="flex h-7 w-7 flex-shrink-0 items-center justify-center rounded border border-ink-200 bg-ink-50 font-serif text-[12px] text-ink-500">
                      {{ u.username.charAt(0).toUpperCase() }}
                    </div>
                    <span class="text-[13.5px] font-medium text-ink-900">{{ u.username }}</span>
                    <span v-if="u.id === auth.user.id" class="text-[11px] text-ink-400">你</span>
                  </div>
                </td>
                <td class="px-4 py-3 text-[13px] text-ink-600">{{ u.email }}</td>
                <td class="px-4 py-3">
                  <span class="inline-flex items-center gap-1.5 text-[12.5px]" :class="roleStyle(u.role)">
                    <span class="h-1.5 w-1.5 rounded-full bg-current"></span>
                    {{ roleLabel(u.role) }}
                  </span>
                </td>
                <td class="px-4 py-3 text-[12.5px] tabular-nums text-ink-500">{{ formatDate(u.created_at) }}</td>
                <td class="px-4 py-3">
                  <div class="flex items-center justify-end gap-0.5 opacity-60 transition-opacity group-hover:opacity-100">
                    <button v-if="canResetPassword(u)" class="btn btn-icon btn-ghost" title="重置密码" @click="handleResetPassword(u)">
                      <svg class="h-4 w-4" fill="none" stroke="currentColor" stroke-width="1.6" viewBox="0 0 24 24">
                        <path stroke-linecap="round" stroke-linejoin="round" d="M14 10a4 4 0 10-3.4 3.95L9 15.5V18H6.5L4 20.5V21h3.5l1.6-1.6a4 4 0 004.9-3.4" />
                      </svg>
                    </button>
                    <button
                      v-if="auth.isOwner && u.role === 'user' && u.id !== auth.user.id"
                      class="btn btn-icon btn-ghost hover:!text-sand-700 hover:!bg-sand-50"
                      title="提升为管理员"
                      @click="handleToggleRole(u)"
                    >
                      <svg class="h-4 w-4" fill="none" stroke="currentColor" stroke-width="1.6" viewBox="0 0 24 24">
                        <path stroke-linecap="round" stroke-linejoin="round" d="M12 19V5m0 0l-5 5m5-5l5 5" />
                      </svg>
                    </button>
                    <button
                      v-if="auth.isOwner && u.role === 'admin' && u.id !== auth.user.id"
                      class="btn btn-icon btn-ghost"
                      title="降级为普通用户"
                      @click="handleToggleRole(u)"
                    >
                      <svg class="h-4 w-4" fill="none" stroke="currentColor" stroke-width="1.6" viewBox="0 0 24 24">
                        <path stroke-linecap="round" stroke-linejoin="round" d="M12 5v14m0 0l5-5m-5 5l-5-5" />
                      </svg>
                    </button>
                    <button v-if="canDelete(u)" class="btn btn-icon btn-danger" title="删除用户" @click="handleDelete(u)">
                      <svg class="h-4 w-4" fill="none" stroke="currentColor" stroke-width="1.6" viewBox="0 0 24 24">
                        <path stroke-linecap="round" stroke-linejoin="round" d="M5 7h14M10 7V5h4v2M8 7l.7 12.1a1 1 0 001 .9h4.6a1 1 0 001-.9L16 7" />
                      </svg>
                    </button>
                  </div>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>

    <!-- 重置密码 -->
    <div
      v-if="resetTarget"
      class="fixed inset-0 z-50 flex items-center justify-center bg-ink-950/25 px-4 backdrop-blur-[2px]"
      @click.self="resetTarget = null"
    >
      <div class="w-full max-w-[380px] rounded-lg border border-ink-200 bg-white p-5 shadow-pop">
        <h3 class="font-serif text-[16px] text-ink-900">重置密码</h3>
        <p class="mt-1 text-[12.5px] text-ink-500">
          为用户「{{ resetTarget.username }}」设置新密码
        </p>
        <input
          v-model="newPassword"
          type="password"
          minlength="6"
          placeholder="输入新密码（至少 6 位）"
          class="input mt-4"
          @keydown.enter="confirmResetPassword"
        />
        <div class="mt-5 flex justify-end gap-2">
          <button class="btn btn-md btn-ghost" @click="resetTarget = null">取消</button>
          <button
            class="btn btn-md btn-primary"
            :disabled="!newPassword || newPassword.length < 6"
            @click="confirmResetPassword"
          >
            确认重置
          </button>
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

function handleResetPassword(u) {
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
  const pad = (n) => n.toString().padStart(2, '0')
  return `${d.getFullYear()}/${pad(d.getMonth() + 1)}/${pad(d.getDate())}`
}

function roleStyle(role) {
  return {
    owner: 'text-seal-700',
    admin: 'text-ink-700',
    user: 'text-ink-400',
  }[role] || 'text-ink-500'
}

function roleLabel(role) {
  return { owner: '站长', admin: '管理员', user: '普通用户' }[role] || role
}
</script>
