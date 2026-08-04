import { http } from './client'

export interface ProviderStat {
  provider_name: string
  calls: number
  success_rate: number
  total_tokens: number
  avg_latency_ms: number
  failovers: number
}

export interface NodeStat {
  node: string
  calls: number
  success_rate: number
  total_tokens: number
  avg_latency_ms: number
}

export interface StatsOut {
  by_provider: ProviderStat[]
  by_node: NodeStat[]
}

export interface LLMCallItem {
  provider_name: string
  model: string
  node: string | null
  thread_id: string | null
  prompt_tokens: number
  completion_tokens: number
  total_tokens: number
  latency_ms: number
  success: boolean
  error: string | null
  failover_from: number[]
  created_at: string
}

export function getStats(): Promise<StatsOut> {
  return http.get<StatsOut>('/llm/stats')
}

export function getCalls(limit = 50): Promise<LLMCallItem[]> {
  return http.get<LLMCallItem[]>(`/llm/calls?limit=${limit}`)
}
