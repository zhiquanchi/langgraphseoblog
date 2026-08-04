import { http } from './client'

export interface GenerateRequest {
  topic: string
  keyword?: string
  provider?: string | number
  model?: string
  // 前端本地保存的密钥映射（provider id -> api_key），仅本次请求使用
  provider_api_keys?: Record<string, string>
}

export interface GenerateResponse {
  article: string
  provider_name: string
  model: string
}

export interface ResearchRequest {
  topic: string
  keyword?: string
  provider?: string | number
  model?: string
  provider_api_keys?: Record<string, string>
  search_api_key?: string
}

export interface ResearchResponse {
  topic: string
  keyword: string
  audience: string
  search_intent: string
  content_angles: string[]
  related_questions: string[]
  competitor_gaps: string[]
  recommended_title: string
  outline: string[]
  provider_name: string
  model: string
  sources: ResearchSource[]
}

export interface ResearchSource {
  title: string
  url: string
  published_at: string | null
}

export function generateBlog(payload: GenerateRequest): Promise<GenerateResponse> {
  return http.post<GenerateResponse>('/blog/generate', payload)
}

export function researchTopic(payload: ResearchRequest): Promise<ResearchResponse> {
  return http.post<ResearchResponse>('/research/topic', payload)
}

const TAVILY_API_KEY_STORAGE_KEY = 'tavily_api_key'

export function getTavilyApiKey(): string {
  return localStorage.getItem(TAVILY_API_KEY_STORAGE_KEY) ?? ''
}

export function setTavilyApiKey(apiKey: string): void {
  if (apiKey) {
    localStorage.setItem(TAVILY_API_KEY_STORAGE_KEY, apiKey)
  } else {
    localStorage.removeItem(TAVILY_API_KEY_STORAGE_KEY)
  }
}
