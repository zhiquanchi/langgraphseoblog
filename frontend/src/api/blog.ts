import { http } from './client'

export interface GenerateRequest {
  topic: string
  keyword?: string
  provider?: string | number
  model?: string
}

export interface GenerateResponse {
  article: string
  provider_name: string
  model: string
}

export function generateBlog(payload: GenerateRequest): Promise<GenerateResponse> {
  return http.post<GenerateResponse>('/blog/generate', payload)
}
