import { useEffect, useMemo, useState } from 'react'
import { Button, Card, Flex, Form, Input, Select, Skeleton, Typography, message } from 'antd'
import { Bubble, Sender } from '@ant-design/x'
import type { BubbleItemType } from '@ant-design/x'
import { resumeBlogThread, startBlogThread } from '../api/blog'
import type { GraphEvent } from '../api/blog'
import { getProviderApiKey, getProviderApiKeys, listProviders } from '../api/providers'
import type { ProviderItem } from '../api/providers'

const { Title, Paragraph } = Typography

interface GenerateForm {
  topic: string
  keyword?: string
  provider?: string
}

interface OutlineDraft {
  title: string
  outline: string[]
}

type ChatItem =
  | { key: string; kind: 'user'; text: string }
  | { key: string; kind: 'outline'; title: string; outline: string[] }
  | { key: string; kind: 'loading' }

let chatKeySeq = 0
function nextChatKey(): string {
  chatKeySeq += 1
  return `msg-${chatKeySeq}`
}

function dropLoading(items: ChatItem[]): ChatItem[] {
  return items.filter((item) => item.kind !== 'loading')
}

interface OutlinePanelProps {
  draft: OutlineDraft
  editable: boolean
  onChange?: (draft: OutlineDraft) => void
}

function OutlinePanel({ draft, editable, onChange }: OutlinePanelProps) {
  const update = (next: Partial<OutlineDraft>) => onChange?.({ ...draft, ...next })
  const move = (index: number, offset: number) => {
    const outline = [...draft.outline]
    const [item] = outline.splice(index, 1)
    outline.splice(index + offset, 0, item)
    update({ outline })
  }
  return (
    <div style={{ minWidth: 320 }}>
      <Paragraph strong style={{ marginBottom: 8 }}>
        <Typography.Text
          editable={
            editable
              ? { onChange: (title) => update({ title: title.trim() || draft.title }) }
              : false
          }
        >
          {draft.title}
        </Typography.Text>
      </Paragraph>
      {draft.outline.map((section, index) => (
        <div key={index} style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
          <span style={{ flexShrink: 0 }}>{index + 1}.</span>
          <Typography.Text
            style={{ flex: 1 }}
            editable={
              editable
                ? {
                    onChange: (text) => {
                      const outline = [...draft.outline]
                      outline[index] = text.trim() || outline[index]
                      update({ outline })
                    },
                  }
                : false
            }
          >
            {section}
          </Typography.Text>
          {editable && (
            <>
              <Button type="text" size="small" disabled={index === 0} onClick={() => move(index, -1)}>
                上移
              </Button>
              <Button
                type="text"
                size="small"
                disabled={index === draft.outline.length - 1}
                onClick={() => move(index, 1)}
              >
                下移
              </Button>
              <Button
                type="text"
                size="small"
                danger
                disabled={draft.outline.length <= 1}
                onClick={() => update({ outline: draft.outline.filter((_, i) => i !== index) })}
              >
                删除
              </Button>
            </>
          )}
        </div>
      ))}
      {editable && (
        <Button
          size="small"
          style={{ marginTop: 8 }}
          onClick={() => update({ outline: [...draft.outline, '新小节'] })}
        >
          添加小节
        </Button>
      )}
    </div>
  )
}

function GeneratePage() {
  const [providers, setProviders] = useState<ProviderItem[]>([])
  const [chat, setChat] = useState<ChatItem[]>([])
  const [threadId, setThreadId] = useState<string | null>(null)
  const [draft, setDraft] = useState<OutlineDraft | null>(null)
  const [outlining, setOutlining] = useState(false)
  const [generating, setGenerating] = useState(false)
  const [finished, setFinished] = useState(false)
  const [article, setArticle] = useState('')
  const [articleMeta, setArticleMeta] = useState<{ provider_name: string; model: string } | null>(null)
  const [instruction, setInstruction] = useState('')
  const [form] = Form.useForm<GenerateForm>()

  useEffect(() => {
    listProviders()
      .then((items) => setProviders(items.filter((p) => p.enabled)))
      .catch(() => setProviders([]))
  }, [])

  const latestOutlineKey = useMemo(() => {
    for (let i = chat.length - 1; i >= 0; i -= 1) {
      if (chat[i].kind === 'outline') return chat[i].key
    }
    return null
  }, [chat])

  const handleOutlineEvent = (event: GraphEvent) => {
    if (event.type === 'interrupt') {
      const next = { title: event.title, outline: event.outline }
      setDraft(next)
      setChat((prev) => [
        ...dropLoading(prev),
        { key: nextChatKey(), kind: 'outline', title: next.title, outline: next.outline },
      ])
    } else if (event.type === 'error') {
      setChat(dropLoading)
      message.error(event.message)
    } else if (event.type === 'done') {
      setOutlining(false)
    }
  }

  const handleStart = async () => {
    const values = await form.validateFields()
    setChat([{ key: nextChatKey(), kind: 'loading' }])
    setThreadId(null)
    setDraft(null)
    setArticle('')
    setArticleMeta(null)
    setFinished(false)
    setOutlining(true)
    try {
      await startBlogThread(
        {
          topic: values.topic,
          keyword: values.keyword ?? '',
          provider: values.provider,
          provider_api_keys: getProviderApiKeys(),
        },
        (event) => {
          if (event.type === 'thread') setThreadId(event.threadId)
          else handleOutlineEvent(event)
        },
      )
    } catch (err) {
      setChat(dropLoading)
      setOutlining(false)
      message.error(err instanceof Error ? err.message : '大纲生成失败')
    }
  }

  const handleRevise = async (text: string) => {
    if (!threadId || !draft || outlining || generating || finished) return
    setChat((prev) => [
      ...prev,
      { key: nextChatKey(), kind: 'user', text },
      { key: nextChatKey(), kind: 'loading' },
    ])
    setOutlining(true)
    try {
      await resumeBlogThread(threadId, { action: 'revise', instruction: text }, handleOutlineEvent)
    } catch (err) {
      setChat(dropLoading)
      setOutlining(false)
      message.error(err instanceof Error ? err.message : '大纲修订失败')
    }
  }

  const handleApprove = async () => {
    if (!threadId || !draft || outlining || generating) return
    setGenerating(true)
    setArticle('')
    setArticleMeta(null)
    try {
      await resumeBlogThread(
        threadId,
        { action: 'approve', title: draft.title, outline: draft.outline },
        (event) => {
          if (event.type === 'article_token') {
            setArticle((prev) => prev + event.text)
          } else if (event.type === 'result') {
            setArticleMeta({ provider_name: event.provider_name, model: event.model })
            setFinished(true)
          } else if (event.type === 'error') {
            message.error(event.message)
          } else if (event.type === 'done') {
            setGenerating(false)
          }
        },
      )
    } catch (err) {
      setGenerating(false)
      message.error(err instanceof Error ? err.message : '文章生成失败')
    }
  }

  const bubbleItems: BubbleItemType[] = chat.map((item) => {
    if (item.kind === 'user') {
      return { key: item.key, role: 'user', content: item.text }
    }
    if (item.kind === 'loading') {
      return { key: item.key, role: 'ai', content: '', loading: true }
    }
    const isLatest = item.key === latestOutlineKey && !finished
    return {
      key: item.key,
      role: 'ai',
      content: (
        <OutlinePanel
          draft={isLatest && draft ? draft : { title: item.title, outline: item.outline }}
          editable={isLatest && !outlining && !generating}
          onChange={setDraft}
        />
      ),
    }
  })

  return (
    <div>
      <Title level={2}>博客生成</Title>
      <Form form={form} layout="vertical" style={{ maxWidth: 640 }}>
        <Form.Item name="topic" label="主题" rules={[{ required: true, message: '请输入主题' }]}>
          <Input placeholder="如：LangGraph 最佳实践" />
        </Form.Item>
        <Form.Item name="keyword" label="目标关键词（可选）">
          <Input placeholder="如：langgraph tutorial" />
        </Form.Item>
        <Form.Item name="provider" label="Provider（不选则用系统默认）">
          <Select
            allowClear
            placeholder="系统默认"
            options={providers.map((p) => ({
              value: p.name,
              label: `${p.name} (${p.default_model})${getProviderApiKey(p.id) ? '' : ' · 未配置 Key'}`,
            }))}
          />
        </Form.Item>
        <Form.Item>
          <Button type="primary" loading={outlining && chat.length <= 1} onClick={() => void handleStart()}>
            生成大纲
          </Button>
        </Form.Item>
      </Form>

      {chat.length > 0 && (
        <Card title="大纲确认" style={{ maxWidth: 900, marginTop: 24 }}>
          <Bubble.List items={bubbleItems} style={{ maxHeight: 480 }} />
          {!finished && (
            <Flex vertical gap={12} style={{ marginTop: 16 }}>
              <Button
                type="primary"
                disabled={!draft || outlining || generating}
                onClick={() => void handleApprove()}
              >
                确认大纲，生成文章
              </Button>
              <Sender
                value={instruction}
                onChange={setInstruction}
                onSubmit={(text) => {
                  setInstruction('')
                  void handleRevise(text)
                }}
                loading={outlining}
                disabled={!draft || generating}
                placeholder={
                  draft
                    ? '输入对大纲的调整要求，如：增加一节关于性能优化的内容'
                    : '等待大纲生成…'
                }
              />
            </Flex>
          )}
        </Card>
      )}

      {(generating || article) && (
        <Card title="生成文章" style={{ maxWidth: 900, marginTop: 24 }}>
          {generating && !article ? (
            <Skeleton active paragraph={{ rows: 14 }} />
          ) : (
            <>
              {articleMeta && (
                <Paragraph>
                  实际使用：<strong>{articleMeta.provider_name}</strong> / {articleMeta.model}
                </Paragraph>
              )}
              <pre
                style={{
                  whiteSpace: 'pre-wrap',
                  background: '#fff',
                  padding: 16,
                  borderRadius: 8,
                  border: '1px solid #f0f0f0',
                }}
              >
                {article}
              </pre>
            </>
          )}
        </Card>
      )}
    </div>
  )
}

export default GeneratePage
