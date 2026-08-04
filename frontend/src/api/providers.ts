import { http } from './client'

export type ProviderType = 'openai' | 'anthropic' | 'ark' | 'openai-compatible'

export interface ProviderItem {
  id: number
  name: string
  type: ProviderType
  base_url: string | null
  default_model: string
  enabled: boolean
  priority: number
  updated_at: string
}

export interface ProviderPayload {
  name: string
  type: ProviderType
  base_url?: string
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

export function testProvider(id: number, apiKey: string): Promise<TestResult> {
  return http.post<TestResult>(`/providers/${id}/test`, { api_key: apiKey })
}

// ---- api_key 本地存储：密钥仅保存在浏览器 localStorage，不提交后端 ----

const API_KEYS_STORAGE_KEY = 'provider_api_keys'

function readApiKeys(): Record<string, string> {
  try {
    const raw = localStorage.getItem(API_KEYS_STORAGE_KEY)
    return raw ? (JSON.parse(raw) as Record<string, string>) : {}
  } catch {
    return {}
  }
}

function writeApiKeys(keys: Record<string, string>): void {
  localStorage.setItem(API_KEYS_STORAGE_KEY, JSON.stringify(keys))
}

export function getProviderApiKey(providerId: number): string | undefined {
  return readApiKeys()[String(providerId)]
}

export function getProviderApiKeys(): Record<string, string> {
  return readApiKeys()
}

export function setProviderApiKey(providerId: number, apiKey: string): void {
  const keys = readApiKeys()
  keys[String(providerId)] = apiKey
  writeApiKeys(keys)
}

export function removeProviderApiKey(providerId: number): void {
  const keys = readApiKeys()
  delete keys[String(providerId)]
  writeApiKeys(keys)
}
