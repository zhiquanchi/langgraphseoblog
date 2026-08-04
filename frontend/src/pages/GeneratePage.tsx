import { useEffect, useState } from 'react'
import { Button, Form, Input, Select, Typography, message } from 'antd'
import { generateBlog } from '../api/blog'
import type { GenerateResponse } from '../api/blog'
import { getProviderApiKey, getProviderApiKeys, listProviders } from '../api/providers'
import type { ProviderItem } from '../api/providers'

const { Title, Paragraph } = Typography

interface GenerateForm {
  topic: string
  keyword?: string
  provider?: string
}

function GeneratePage() {
  const [providers, setProviders] = useState<ProviderItem[]>([])
  const [generating, setGenerating] = useState(false)
  const [result, setResult] = useState<GenerateResponse | null>(null)
  const [form] = Form.useForm<GenerateForm>()

  useEffect(() => {
    listProviders()
      .then((items) => setProviders(items.filter((p) => p.enabled)))
      .catch(() => setProviders([]))
  }, [])

  const handleGenerate = async () => {
    const values = await form.validateFields()
    setGenerating(true)
    try {
      const resp = await generateBlog({
        topic: values.topic,
        keyword: values.keyword ?? '',
        provider: values.provider,
        provider_api_keys: getProviderApiKeys(),
      })
      setResult(resp)
    } catch (err) {
      message.error(err instanceof Error ? err.message : '生成失败')
    } finally {
      setGenerating(false)
    }
  }

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
          <Button type="primary" loading={generating} onClick={() => void handleGenerate()}>
            生成文章
          </Button>
        </Form.Item>
      </Form>
      {result && (
        <div style={{ marginTop: 24 }}>
          <Paragraph>
            实际使用：<strong>{result.provider_name}</strong> / {result.model}
          </Paragraph>
          <pre
            style={{
              whiteSpace: 'pre-wrap',
              background: '#fff',
              padding: 16,
              borderRadius: 8,
              border: '1px solid #f0f0f0',
            }}
          >
            {result.article}
          </pre>
        </div>
      )}
    </div>
  )
}

export default GeneratePage
