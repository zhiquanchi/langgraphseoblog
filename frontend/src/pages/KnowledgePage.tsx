import { useCallback, useEffect, useState } from 'react'
import {
  Button,
  Card,
  Empty,
  Form,
  Input,
  List,
  Popconfirm,
  Space,
  Tag,
  Typography,
  message,
} from 'antd'
import {
  addRagDocument,
  deleteRagDocument,
  getRagStatus,
  listRagDocuments,
  searchRag,
  seedRagCorpus,
} from '../api/rag'
import type { RagDocument, RagHit, RagStatus } from '../api/rag'

const { Title, Paragraph, Text } = Typography

interface DocForm {
  title: string
  content: string
}

function KnowledgePage() {
  const [status, setStatus] = useState<RagStatus | null>(null)
  const [docs, setDocs] = useState<RagDocument[]>([])
  const [loading, setLoading] = useState(false)
  const [seeding, setSeeding] = useState(false)
  const [hits, setHits] = useState<RagHit[] | null>(null)
  const [form] = Form.useForm<DocForm>()

  const refresh = useCallback(async () => {
    setLoading(true)
    try {
      const [nextStatus, nextDocs] = await Promise.all([getRagStatus(), listRagDocuments()])
      setStatus(nextStatus)
      setDocs(nextDocs)
    } catch (err) {
      message.error(err instanceof Error ? err.message : '加载知识库状态失败')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void refresh()
  }, [refresh])

  const handleSeed = async () => {
    setSeeding(true)
    try {
      const result = await seedRagCorpus()
      const imported = result.ingested.length
      message.success(
        imported > 0
          ? `导入 ${imported} 篇内置语料${result.skipped.length ? `，跳过 ${result.skipped.length} 篇（已存在）` : ''}`
          : '内置语料均已入库',
      )
      await refresh()
    } catch (err) {
      message.error(err instanceof Error ? err.message : '导入内置语料失败')
    } finally {
      setSeeding(false)
    }
  }

  const handleAdd = async (values: DocForm) => {
    try {
      const result = await addRagDocument({ title: values.title, content: values.content })
      message.success(`已入库，切分为 ${result.chunks} 个分块`)
      form.resetFields()
      await refresh()
    } catch (err) {
      message.error(err instanceof Error ? err.message : '文档入库失败')
    }
  }

  const handleDelete = async (doc: RagDocument) => {
    try {
      await deleteRagDocument(doc.id)
      message.success('已删除')
      await refresh()
    } catch (err) {
      message.error(err instanceof Error ? err.message : '删除失败')
    }
  }

  const handleSearch = async (query: string) => {
    const keyword = query.trim()
    if (!keyword) return
    try {
      const result = await searchRag(keyword, 4)
      setHits(result.hits)
    } catch (err) {
      setHits(null)
      message.error(err instanceof Error ? err.message : '检索失败')
    }
  }

  return (
    <div>
      <Title level={2}>知识库（RAG）</Title>
      <Space wrap style={{ marginBottom: 16 }}>
        {status ? (
          status.enabled ? (
            <Tag color="green">已启用 · 向量库 {status.vector_store}</Tag>
          ) : (
            <Tag color="red">未启用：请配置 EMBEDDING_PROVIDER 环境变量</Tag>
          )
        ) : (
          <Tag>加载中…</Tag>
        )}
        {status && (
          <Text type="secondary">
            文档 {status.doc_count} 篇 / 分块 {status.chunk_count} 个
          </Text>
        )}
        <Button type="primary" loading={seeding} onClick={() => void handleSeed()}>
          导入内置语料
        </Button>
      </Space>

      <Card title="检索测试" style={{ maxWidth: 900, marginBottom: 24 }}>
        <Input.Search
          placeholder="输入查询，测试语义检索效果"
          enterButton="检索"
          onSearch={(value) => void handleSearch(value)}
          style={{ maxWidth: 560 }}
        />
        {hits !== null && (
          <List
            style={{ marginTop: 16 }}
            dataSource={hits}
            locale={{ emptyText: <Empty description="没有命中结果" /> }}
            renderItem={(hit) => (
              <List.Item>
                <div>
                  <Space wrap>
                    <Text strong>{hit.title}</Text>
                    <Tag>相似度 {hit.score.toFixed(3)}</Tag>
                    {hit.source && <Text type="secondary">来源：{hit.source}</Text>}
                  </Space>
                  <Paragraph style={{ marginBottom: 0, marginTop: 4 }} type="secondary">
                    {hit.content}
                  </Paragraph>
                </div>
              </List.Item>
            )}
          />
        )}
      </Card>

      <Card title="已入库文档" style={{ maxWidth: 900, marginBottom: 24 }}>
        <List
          loading={loading}
          dataSource={docs}
          locale={{ emptyText: <Empty description="还没有文档，先导入内置语料或手动添加" /> }}
          renderItem={(doc) => (
            <List.Item
              actions={[
                <Popconfirm
                  key="delete"
                  title="删除该文档？"
                  description="将同时移除向量索引中的分块"
                  onConfirm={() => void handleDelete(doc)}
                >
                  <Button danger type="text" size="small">
                    删除
                  </Button>
                </Popconfirm>,
              ]}
            >
              <List.Item.Meta
                title={
                  <Space wrap>
                    {doc.title}
                    <Tag>{doc.chunks} 分块</Tag>
                  </Space>
                }
                description={doc.source || '手动添加'}
              />
            </List.Item>
          )}
        />
      </Card>

      <Card title="添加文档" style={{ maxWidth: 900 }}>
        <Form form={form} layout="vertical" onFinish={(values) => void handleAdd(values)}>
          <Form.Item
            name="title"
            label="标题"
            rules={[{ required: true, message: '请输入标题' }]}
          >
            <Input placeholder="如：内部产品 FAQ" maxLength={200} />
          </Form.Item>
          <Form.Item
            name="content"
            label="正文（Markdown，入库时自动切分）"
            rules={[{ required: true, message: '请输入正文' }]}
          >
            <Input.TextArea rows={8} maxLength={50_000} showCount />
          </Form.Item>
          <Button type="primary" htmlType="submit">
            入库
          </Button>
        </Form>
      </Card>
    </div>
  )
}

export default KnowledgePage
