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

export function generateBlog(payload: GenerateRequest): Promise<GenerateResponse> {
  return http.post<GenerateResponse>('/blog/generate', payload)
}
