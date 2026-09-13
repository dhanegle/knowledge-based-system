<template>
  <div class="flex h-full flex-col">
    <!-- 页头 -->
    <header class="page-head">
      <div>
        <h2 class="page-title">文档管理</h2>
        <p class="page-sub">
          {{ auth.isAdmin ? '上传、管理与查看知识库文档' : '查看知识库文档（只读）' }}
        </p>
      </div>
      <button class="btn btn-md btn-outline" :disabled="loading" @click="refresh">
        <svg class="h-3.5 w-3.5" :class="loading && 'animate-spin'" fill="none" stroke="currentColor" stroke-width="1.7" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" d="M20 11a8 8 0 10-2.3 5.7M20 5v6h-6" />
        </svg>
        刷新
      </button>
    </header>

    <div class="min-h-0 flex-1 overflow-y-auto">
      <div class="mx-auto max-w-4xl px-8 py-6">
        <!-- 上传区 -->
        <div
          v-if="auth.isAdmin"
          class="mb-6 rounded-lg border border-dashed transition-colors duration-150"
          :class="dragOver ? 'border-seal-400 bg-seal-50/50' : 'border-ink-300 bg-white/60'"
          @dragover.prevent="dragOver = true"
          @dragleave.prevent="dragOver = false"
          @drop.prevent="handleDrop"
        >
          <input
            ref="fileInput"
            type="file"
            class="hidden"
            accept=".pdf,.docx,.pptx,.xlsx,.md,.txt,.py,.js,.ts,.go,.java,.rs"
            multiple
            @change="handleFileSelect"
          />
          <div class="flex flex-col items-center px-6 py-8 text-center">
            <svg class="h-5 w-5 text-ink-400" fill="none" stroke="currentColor" stroke-width="1.4" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" d="M12 16V4m0 0L7.5 8.5M12 4l4.5 4.5M4 16v2a2 2 0 002 2h12a2 2 0 002-2v-2" />
            </svg>
            <p class="mt-3 text-[13.5px] text-ink-700">
              拖放文件到此处，或
              <button class="font-medium text-seal-700 underline underline-offset-2 hover:text-seal-800" @click="fileInput.click()">
                选择文件
              </button>
            </p>
            <p class="mt-1.5 text-[12px] text-ink-400">
              支持 PDF / Word / PPT / Excel / Markdown / 代码文件
            </p>

            <div v-if="uploading" class="mt-4 flex items-center gap-2 text-[12.5px] text-ink-600">
              <svg class="h-3.5 w-3.5 animate-spin" fill="none" viewBox="0 0 24 24">
                <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="3" />
                <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
              </svg>
              正在上传并摄入…
            </div>
          </div>
        </div>

        <!-- 统计行 -->
        <div v-if="docs.length" class="mb-2 flex items-baseline justify-between px-1">
          <span class="caps">文档 · {{ docs.length }}</span>
          <span class="text-[11.5px] tabular-nums text-ink-400">
            {{ indexedCount }} 已入库
          </span>
        </div>

        <!-- 空态 -->
        <div v-if="docs.length === 0 && !loading" class="flex flex-col items-center py-20 text-center">
          <svg class="h-5 w-5 text-ink-300" fill="none" stroke="currentColor" stroke-width="1.4" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" d="M9 3h6l4 4v12a2 2 0 01-2 2H7a2 2 0 01-2-2V5a2 2 0 012-2h2zm5 1.5V8h3.5" />
          </svg>
          <p class="mt-3 text-[13.5px] text-ink-600">
            {{ auth.isAdmin ? '暂无文档，上传第一个文档开始使用知识库' : '暂无文档' }}
          </p>
        </div>

        <!-- 列表 -->
        <div v-else class="card divide-y divide-ink-200/70 overflow-hidden">
          <div
            v-for="doc in docs"
            :key="doc.id"
            class="flex items-center gap-4 px-4 py-3.5 transition-colors hover:bg-ink-50/70"
          >
            <!-- 类型 -->
            <div class="flex h-9 w-9 flex-shrink-0 items-center justify-center rounded border border-ink-200 bg-ink-50 font-mono text-[10px] uppercase tracking-wide text-ink-500">
              {{ extLabel(doc.file_type) }}
            </div>

            <!-- 信息 -->
            <div class="min-w-0 flex-1">
              <p class="truncate text-[14px] font-medium text-ink-900">{{ doc.filename }}</p>
              <div class="mt-1 flex items-center gap-2.5 text-[11.5px] text-ink-400">
                <span class="tabular-nums">{{ formatSize(doc.file_size) }}</span>
                <span class="h-3 w-px bg-ink-200"></span>
                <span class="tabular-nums">{{ doc.chunk_count }} 分块</span>
                <span class="h-3 w-px bg-ink-200"></span>
                <span class="tabular-nums">{{ formatDate(doc.created_at) }}</span>
              </div>
              <p v-if="doc.error" class="mt-1.5 text-[12px] leading-snug text-seal-700">{{ doc.error }}</p>
              <p v-else-if="doc.extraction_notes" class="mt-1.5 text-[12px] leading-snug text-ink-500">
                {{ doc.extraction_notes }}
              </p>
            </div>

            <!-- 状态 -->
            <span class="inline-flex flex-shrink-0 items-center gap-1.5 rounded-full border px-2 py-[3px] text-[11px]" :class="statusStyle(doc.status)">
              <span class="h-1.5 w-1.5 rounded-full bg-current"></span>
              {{ statusLabel(doc.status) }}
            </span>

            <!-- 操作 -->
            <div v-if="auth.isAdmin" class="flex flex-shrink-0 items-center gap-0.5">
              <button
                v-if="doc.status === 'failed' || doc.status === 'indexed'"
                class="btn btn-icon btn-ghost"
                title="重新摄入"
                @click="handleReingest(doc)"
              >
                <svg class="h-4 w-4" fill="none" stroke="currentColor" stroke-width="1.6" viewBox="0 0 24 24">
                  <path stroke-linecap="round" stroke-linejoin="round" d="M20 11a8 8 0 10-2.3 5.7M20 5v6h-6" />
                </svg>
              </button>
              <button class="btn btn-icon btn-danger" title="删除" @click="handleDelete(doc)">
                <svg class="h-4 w-4" fill="none" stroke="currentColor" stroke-width="1.6" viewBox="0 0 24 24">
                  <path stroke-linecap="round" stroke-linejoin="round" d="M5 7h14M10 7V5h4v2M8 7l.7 12.1a1 1 0 001 .9h4.6a1 1 0 001-.9L16 7" />
                </svg>
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useDocumentStore } from '../stores/documents'
import { useAuthStore } from '../stores/auth'

const store = useDocumentStore()
const auth = useAuthStore()
const uploading = ref(false)
const dragOver = ref(false)
const fileInput = ref(null)
let pollTimer = null

const docs = computed(() => store.documents)
const loading = computed(() => store.loading)
const indexedCount = computed(() => docs.value.filter(d => d.status === 'indexed').length)

onMounted(async () => {
  await store.fetchDocuments()
  // 有非终态文档或正在上传时轮询刷新
  pollTimer = setInterval(async () => {
    const hasPending = docs.value.some(d =>
      ['pending', 'parsing', 'chunking', 'embedding'].includes(d.status)
    )
    if (hasPending || uploading.value) {
      await store.fetchDocuments()
    }
  }, 3000)
})

onUnmounted(() => {
  if (pollTimer) clearInterval(pollTimer)
})

async function refresh() {
  await store.fetchDocuments()
}

async function handleFileSelect(e) {
  const files = Array.from(e.target.files)
  for (const file of files) {
    await uploadFile(file)
  }
  e.target.value = ''
}

async function handleDrop(e) {
  dragOver.value = false
  const files = Array.from(e.dataTransfer.files)
  for (const file of files) {
    await uploadFile(file)
  }
}

async function uploadFile(file) {
  uploading.value = true
  try {
    await store.upload(file)
  } catch (e) {
    alert(e.detail || e.error || '上传失败')
  } finally {
    uploading.value = false
  }
}

async function handleDelete(doc) {
  if (!confirm(`确认删除「${doc.filename}」？`)) return
  try {
    await store.remove(doc.id)
  } catch (e) {
    alert(e.detail || e.error || '删除失败')
  }
}

async function handleReingest(doc) {
  const input = document.createElement('input')
  input.type = 'file'
  input.accept = '.pdf,.docx,.pptx,.xlsx,.md,.txt,.py,.js,.ts,.go,.java,.rs'
  input.onchange = async (e) => {
    const file = e.target.files[0]
    if (!file) return
    try {
      await store.reingest(doc.id, file)
    } catch (e) {
      alert(e.detail || e.error || '重新摄入失败')
    }
  }
  input.click()
}

function formatSize(bytes) {
  if (!bytes) return '-'
  if (bytes < 1024) return bytes + ' B'
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB'
  return (bytes / (1024 * 1024)).toFixed(1) + ' MB'
}

function formatDate(iso) {
  if (!iso) return '-'
  const d = new Date(iso)
  const pad = (n) => n.toString().padStart(2, '0')
  return `${d.getMonth() + 1}/${d.getDate()} ${pad(d.getHours())}:${pad(d.getMinutes())}`
}

function extLabel(ext) {
  return (ext || '?').replace('.', '').slice(0, 4) || '?'
}

function statusStyle(status) {
  return {
    indexed: 'border-moss-200 bg-moss-50 text-moss-700',
    failed: 'border-seal-200 bg-seal-50 text-seal-700',
    pending: 'border-sand-200 bg-sand-50 text-sand-700',
  }[status] || 'border-ink-200 bg-ink-50 text-ink-600'
}

function statusLabel(status) {
  return {
    pending: '等待中',
    parsing: '解析中',
    chunking: '分块中',
    embedding: '向量化中',
    indexed: '已入库',
    failed: '失败',
  }[status] || status
}
</script>
