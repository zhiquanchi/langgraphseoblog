import { http } from './client'

export type ProviderType = 'openai' | 'anthropic' | 'ark' | 'openai-compatible'

export interface ProviderItem {
  id: number
  name: string
  type: ProviderType
  base_url: string | null
  api_key_masked: string
  default_model: string
  enabled: boolean
  priority: number
  updated_at: string
}

export interface ProviderPayload {
  name: string
  type: ProviderType
  base_url?: string
  api_key?: string
  default_model: string
  enabled?: boolean
  priority?: number
}

export interface TestResult {
  ok: boolean
  message: string
}

export function listProviders(): Promise<ProviderItem[]> {
  return http.get<ProviderItem[]>('/providers')
}

export function createProvider(payload: ProviderPayload): Promise<ProviderItem> {
  return http.post<ProviderItem>('/providers', payload)
}

export function updateProvider(
  id: number,
  payload: Partial<ProviderPayload>,
): Promise<ProviderItem> {
  return http.patch<ProviderItem>(`/providers/${id}`, payload)
}

export function deleteProvider(id: number): Promise<void> {
  return http.delete<void>(`/providers/${id}`)
}

export function testProvider(id: number): Promise<TestResult> {
  return http.post<TestResult>(`/providers/${id}/test`)
}
