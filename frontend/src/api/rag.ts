import { http } from './client'

export interface RagStatus {
  enabled: boolean
  vector_store: string
  doc_count: number
  chunk_count: number
}

export interface RagDocument {
  id: number
  title: string
  source: string
  chunks: number
  created_at: string
}

export interface RagIngestResult {
  doc_id: number
  chunks: number
}

export interface RagHit {
  content: string
  title: string
  source: string
  doc_id: number | null
  score: number
}

export interface RagSeedResult {
  ingested: RagIngestResult[]
  skipped: string[]
}

export function getRagStatus(): Promise<RagStatus> {
  return http.get<RagStatus>('/rag/status')
}

export function listRagDocuments(): Promise<RagDocument[]> {
  return http.get<RagDocument[]>('/rag/documents')
}

export function addRagDocument(payload: {
  title: string
  content: string
  source?: string
}): Promise<RagIngestResult> {
  return http.post<RagIngestResult>('/rag/documents', payload)
}

export function deleteRagDocument(docId: number): Promise<void> {
  return http.delete<void>(`/rag/documents/${docId}`)
}

export function searchRag(query: string, k = 4): Promise<{ query: string; hits: RagHit[] }> {
  return http.post<{ query: string; hits: RagHit[] }>('/rag/search', { query, k })
}

export function seedRagCorpus(): Promise<RagSeedResult> {
  return http.post<RagSeedResult>('/rag/seed')
}
