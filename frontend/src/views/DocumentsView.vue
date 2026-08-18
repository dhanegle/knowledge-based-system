<template>
  <div class="flex flex-col h-full">
    <!-- 顶栏 -->
    <div class="px-6 py-4 border-b border-gray-200 bg-white flex items-center justify-between">
      <div>
        <h2 class="text-lg font-semibold text-gray-800">文档管理</h2>
        <p class="text-sm text-gray-500">上传、管理和查看知识库文档</p>
      </div>
      <button
        @click="refresh"
        class="px-4 py-2 text-sm text-zhiyuan-600 hover:bg-zhiyuan-50 rounded-lg transition flex items-center gap-1.5"
      >
        <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
        </svg>
        刷新
      </button>
    </div>

    <div class="flex-1 overflow-y-auto p-6">
      <!-- 上传区 -->
      <div
        class="mb-6 border-2 border-dashed rounded-xl p-8 text-center transition-colors"
        :class="dragOver ? 'border-zhiyuan-500 bg-zhiyuan-50' : 'border-gray-300'"
        @dragover.prevent="dragOver = true"
        @dragleave.prevent="dragOver = false"
        @drop.prevent="handleDrop"
      >
        <input ref="fileInput" type="file" class="hidden" accept=".pdf,.docx,.pptx,.xlsx,.md,.txt,.py,.js,.ts,.go,.java,.rs" multiple @change="handleFileSelect" />
        <svg class="w-12 h-12 mx-auto mb-3 text-zhiyuan-300" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12" />
        </svg>
        <p class="text-gray-600 mb-2">拖放文件到此处，或</p>
        <button @click="$refs.fileInput.click()" class="text-zhiyuan-600 hover:underline font-medium">
          点击选择文件
        </button>
        <p class="text-xs text-gray-400 mt-2">支持 PDF / Word / PPT / Excel / Markdown / 代码文件</p>

        <!-- 上传中 -->
        <div v-if="uploading" class="mt-4">
          <div class="inline-flex items-center gap-2 text-zhiyuan-600 text-sm">
            <svg class="w-4 h-4 animate-spin" fill="none" viewBox="0 0 24 24">
              <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"/>
              <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"/>
            </svg>
            正在上传并摄入...
          </div>
        </div>
      </div>

      <!-- 文档列表 -->
      <div v-if="docs.length === 0 && !loading" class="text-center text-gray-400 py-12">
        暂无文档，上传第一个文档开始使用知识库
      </div>

      <div v-else class="space-y-3">
        <div
          v-for="doc in docs"
          :key="doc.id"
          class="bg-white border border-gray-200 rounded-xl p-4 flex items-center gap-4 hover:border-zhiyuan-300 transition"
        >
          <!-- 文件图标 -->
          <div class="w-10 h-10 flex items-center justify-center rounded-lg flex-shrink-0"
            :class="fileIconClass(doc.file_type)">
            <span class="text-xs font-bold uppercase">{{ doc.file_type?.replace('.', '') || '?' }}</span>
          </div>

          <!-- 文件信息 -->
          <div class="flex-1 min-w-0">
            <p class="font-medium text-gray-800 truncate">{{ doc.filename }}</p>
            <div class="flex items-center gap-3 text-xs text-gray-500 mt-1">
              <span>{{ formatSize(doc.file_size) }}</span>
              <span>{{ doc.chunk_count }} chunks</span>
              <span>{{ formatDate(doc.created_at) }}</span>
            </div>
            <!-- 状态标签 -->
            <span class="inline-flex items-center mt-1.5 px-2 py-0.5 text-xs rounded-full"
              :class="statusClass(doc.status)">
              {{ statusLabel(doc.status) }}
            </span>
            <!-- 错误信息 -->
            <p v-if="doc.error" class="text-xs text-red-500 mt-1">{{ doc.error }}</p>
          </div>

          <!-- 操作 -->
          <div class="flex items-center gap-2 flex-shrink-0">
            <button
              v-if="doc.status === 'failed' || doc.status === 'indexed'"
              @click="handleReingest(doc)"
              class="p-2 text-gray-400 hover:text-zhiyuan-600 hover:bg-zhiyuan-50 rounded-lg transition"
              title="重新摄入"
            >
              <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
              </svg>
            </button>
            <button
              @click="handleDelete(doc)"
              class="p-2 text-gray-400 hover:text-red-500 hover:bg-red-50 rounded-lg transition"
              title="删除"
            >
              <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
              </svg>
            </button>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted } from 'vue'
import { useDocumentStore } from '../stores/documents'

const store = useDocumentStore()
const docs = ref(store.documents)
const loading = ref(store.loading)
const uploading = ref(false)
const dragOver = ref(false)
const fileInput = ref(null)
let pollTimer = null

const docs_ref = docs

onMounted(async () => {
  await store.fetchDocuments()
  docs.value = store.documents
  // 自动轮询：如果有非终态文档则持续刷新
  pollTimer = setInterval(async () => {
    const hasPending = docs.value.some(d =>
      ['pending', 'parsing', 'chunking', 'embedding'].includes(d.status)
    )
    if (hasPending || uploading.value) {
      await store.fetchDocuments()
      docs.value = store.documents
    }
  }, 3000)
})

onUnmounted(() => {
  if (pollTimer) clearInterval(pollTimer)
})

async function refresh() {
  await store.fetchDocuments()
  docs.value = store.documents
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
    docs.value = store.documents
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
    docs.value = store.documents
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
      docs.value = store.documents
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
  return `${d.getMonth() + 1}/${d.getDate()} ${d.getHours().toString().padStart(2, '0')}:${d.getMinutes().toString().padStart(2, '0')}`
}

function fileIconClass(ext) {
  const classes = {
    '.pdf': 'bg-red-100 text-red-600',
    '.docx': 'bg-blue-100 text-blue-600',
    '.pptx': 'bg-orange-100 text-orange-600',
    '.xlsx': 'bg-green-100 text-green-600',
    '.md': 'bg-purple-100 text-purple-600',
  }
  return classes[ext] || 'bg-gray-100 text-gray-600'
}

function statusClass(status) {
  const classes = {
    indexed: 'bg-green-100 text-green-700',
    pending: 'bg-yellow-100 text-yellow-700',
    parsing: 'bg-blue-100 text-blue-700',
    chunking: 'bg-blue-100 text-blue-700',
    embedding: 'bg-indigo-100 text-indigo-700',
    failed: 'bg-red-100 text-red-700',
  }
  return classes[status] || 'bg-gray-100 text-gray-600'
}

function statusLabel(status) {
  const labels = {
    pending: '等待中',
    parsing: '解析中',
    chunking: '分块中',
    embedding: '向量化中',
    indexed: '已入库',
    failed: '失败',
  }
  return labels[status] || status
}
</script>
