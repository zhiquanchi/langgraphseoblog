// 博客生成工作流 API：LangGraph + SSE 流式
// 事件序列：thread → node/outline_token → interrupt（待确认）
//          →（approve 后）node/article_token → result → done

export interface GraphStartPayload {
  topic: string
  keyword?: string
  provider?: string | number
  provider_api_keys?: Record<string, string>
}

export interface GraphRevisePayload {
  action: 'revise'
  instruction: string
}

export interface GraphApprovePayload {
  action: 'approve'
  title?: string
  outline?: string[]
}

export type GraphEvent =
  | { type: 'thread'; threadId: string }
  | { type: 'node'; node: string }
  | { type: 'outline_token'; text: string }
  | { type: 'interrupt'; title: string; outline: string[] }
  | { type: 'article_token'; text: string }
  | { type: 'result'; article: string; provider_name: string; model: string }
  | { type: 'error'; message: string }
  | { type: 'done' }

const EVENT_TYPES = new Set([
  'thread',
  'node',
  'outline_token',
  'interrupt',
  'article_token',
  'result',
  'error',
  'done',
])

function parseEventBlock(block: string): GraphEvent | null {
  let event = ''
  let data = ''
  for (const line of block.split('\n')) {
    if (line.startsWith('event: ')) event = line.slice(7).trim()
    else if (line.startsWith('data: ')) data += line.slice(6)
  }
  if (!event || !data || !EVENT_TYPES.has(event)) return null
  const parsed = JSON.parse(data) as Record<string, unknown>
  switch (event) {
    case 'thread':
      return { type: 'thread', threadId: String(parsed.thread_id) }
    case 'node':
      return { type: 'node', node: String(parsed.node) }
    case 'outline_token':
      return { type: 'outline_token', text: String(parsed.text) }
    case 'interrupt':
      return {
        type: 'interrupt',
        title: String(parsed.title),
        outline: (parsed.outline as string[]) ?? [],
      }
    case 'article_token':
      return { type: 'article_token', text: String(parsed.text) }
    case 'result':
      return {
        type: 'result',
        article: String(parsed.article),
        provider_name: String(parsed.provider_name),
        model: String(parsed.model),
      }
    case 'error':
      return { type: 'error', message: String(parsed.message) }
    default:
      return { type: 'done' }
  }
}

async function streamGraph(
  path: string,
  body: unknown,
  onEvent: (event: GraphEvent) => void,
): Promise<void> {
  const resp = await fetch(`/api${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  if (!resp.ok) {
    let detail = `请求失败 (${resp.status})`
    try {
      const errorBody = (await resp.json()) as { detail?: string }
      detail = errorBody.detail ?? detail
    } catch {
      // 响应体非 JSON 时使用默认提示
    }
    throw new Error(detail)
  }
  if (!resp.body) throw new Error('浏览器不支持流式响应')

  const reader = resp.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  for (;;) {
    const { done, value } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })
    const blocks = buffer.split('\n\n')
    buffer = blocks.pop() ?? ''
    for (const block of blocks) {
      const event = parseEventBlock(block.trim())
      if (event) onEvent(event)
    }
  }
  const tail = parseEventBlock(buffer.trim())
  if (tail) onEvent(tail)
}

export function startBlogThread(
  payload: GraphStartPayload,
  onEvent: (event: GraphEvent) => void,
): Promise<void> {
  return streamGraph('/blog/threads', payload, onEvent)
}

export function resumeBlogThread(
  threadId: string,
  payload: GraphRevisePayload | GraphApprovePayload,
  onEvent: (event: GraphEvent) => void,
): Promise<void> {
  return streamGraph(`/blog/threads/${threadId}/resume`, payload, onEvent)
}
