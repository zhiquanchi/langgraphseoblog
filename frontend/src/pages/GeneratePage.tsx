import { useEffect, useState } from 'react'
import { Button, Card, Form, Input, List, Select, Space, Typography, message } from 'antd'
import { generateBlog, researchTopic } from '../api/blog'
import type { GenerateResponse, ResearchResponse } from '../api/blog'
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
  const [researching, setResearching] = useState(false)
  const [research, setResearch] = useState<ResearchResponse | null>(null)
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

  const handleResearch = async () => {
    const values = await form.validateFields(['topic', 'keyword', 'provider'])
    setResearching(true)
    try {
      const resp = await researchTopic({
        topic: values.topic,
        keyword: values.keyword ?? '',
        provider: values.provider,
        provider_api_keys: getProviderApiKeys(),
      })
      setResearch(resp)
      message.success('选题研究完成')
    } catch (err) {
      message.error(err instanceof Error ? err.message : '选题研究失败')
    } finally {
      setResearching(false)
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
          <Space>
            <Button loading={researching} onClick={() => void handleResearch()}>
              研究选题
            </Button>
            <Button type="primary" loading={generating} onClick={() => void handleGenerate()}>
              生成文章
            </Button>
          </Space>
        </Form.Item>
      </Form>
      {research && (
        <Card
          title="选题研究简报"
          extra={`分析来源：${research.provider_name} / ${research.model}`}
          style={{ maxWidth: 900, marginTop: 24 }}
        >
          <Typography.Paragraph>
            <strong>核心受众：</strong>{research.audience}
          </Typography.Paragraph>
          <Typography.Paragraph>
            <strong>搜索意图：</strong>{research.search_intent}
          </Typography.Paragraph>
          <Typography.Title level={5}>内容角度</Typography.Title>
          <List size="small" dataSource={research.content_angles} renderItem={(item) => <List.Item>{item}</List.Item>} />
          <Typography.Title level={5}>用户问题</Typography.Title>
          <List size="small" dataSource={research.related_questions} renderItem={(item) => <List.Item>{item}</List.Item>} />
          <Typography.Title level={5}>可填补的内容空白</Typography.Title>
          <List size="small" dataSource={research.competitor_gaps} renderItem={(item) => <List.Item>{item}</List.Item>} />
          <Typography.Title level={5}>推荐标题</Typography.Title>
          <Typography.Paragraph>{research.recommended_title}</Typography.Paragraph>
          <Typography.Title level={5}>建议大纲</Typography.Title>
          <List
            size="small"
            bordered
            dataSource={research.outline}
            renderItem={(item, index) => <List.Item>{index + 1}. {item}</List.Item>}
          />
          <Typography.Title level={5}>参考来源</Typography.Title>
          <List
            size="small"
            dataSource={research.sources}
            locale={{ emptyText: '没有检索到可用来源' }}
            renderItem={(source) => (
              <List.Item>
                <a href={source.url} target="_blank" rel="noreferrer">
                  {source.title}
                </a>
              </List.Item>
            )}
          />
        </Card>
      )}
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
