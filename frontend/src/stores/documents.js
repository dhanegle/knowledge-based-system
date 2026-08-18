import { defineStore } from 'pinia'
import { ref } from 'vue'
import { listDocuments, uploadDocument, deleteDocument, reingestDocument } from '../api'

export const useDocumentStore = defineStore('documents', () => {
  const documents = ref([])
  const loading = ref(false)

  async function fetchDocuments() {
    loading.value = true
    try {
      documents.value = await listDocuments()
    } finally {
      loading.value = false
    }
  }

  async function upload(file) {
    const result = await uploadDocument(file)
    await fetchDocuments()
    return result
  }

  async function remove(docId) {
    await deleteDocument(docId)
    await fetchDocuments()
  }

  async function reingest(docId, file) {
    const result = await reingestDocument(docId, file)
    await fetchDocuments()
    return result
  }

  return { documents, loading, fetchDocuments, upload, remove, reingest }
})
