import { useCallback, useEffect, useState } from 'react'
import {
  Button,
  Form,
  Input,
  InputNumber,
  Modal,
  Popconfirm,
  Select,
  Space,
  Switch,
  Table,
  Tag,
  message,
} from 'antd'
import type { ColumnsType } from 'antd/es/table'
import {
  createProvider,
  deleteProvider,
  listProviders,
  testProvider,
  updateProvider,
} from '../api/providers'
import type { ProviderItem, ProviderPayload, ProviderType } from '../api/providers'

const TYPE_OPTIONS: { value: ProviderType; label: string }[] = [
  { value: 'openai', label: 'OpenAI' },
  { value: 'anthropic', label: 'Anthropic' },
  { value: 'ark', label: '火山方舟 (Ark)' },
  { value: 'openai-compatible', label: 'OpenAI 兼容端点' },
]

function ProvidersPage() {
  const [providers, setProviders] = useState<ProviderItem[]>([])
  const [loading, setLoading] = useState(false)
  const [modalOpen, setModalOpen] = useState(false)
  const [editing, setEditing] = useState<ProviderItem | null>(null)
  const [saving, setSaving] = useState(false)
  const [form] = Form.useForm<ProviderPayload>()
  const watchedType = Form.useWatch('type', form)

  const refresh = useCallback(async () => {
    setLoading(true)
    try {
      setProviders(await listProviders())
    } catch (err) {
      message.error(err instanceof Error ? err.message : '加载失败')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void refresh()
  }, [refresh])

  const openCreate = () => {
    setEditing(null)
    form.resetFields()
    form.setFieldsValue({ type: 'openai', enabled: true, priority: 0 })
    setModalOpen(true)
  }

  const openEdit = (item: ProviderItem) => {
    setEditing(item)
    form.resetFields()
    form.setFieldsValue({
      name: item.name,
      type: item.type,
      base_url: item.base_url ?? undefined,
      api_key: undefined,
      default_model: item.default_model,
      enabled: item.enabled,
      priority: item.priority,
    })
    setModalOpen(true)
  }

  const handleSubmit = async () => {
    const values = await form.validateFields()
    setSaving(true)
    try {
      if (editing) {
        await updateProvider(editing.id, values)
        message.success('已更新')
      } else {
        await createProvider(values)
        message.success('已创建')
      }
      setModalOpen(false)
      await refresh()
    } catch (err) {
      message.error(err instanceof Error ? err.message : '保存失败')
    } finally {
      setSaving(false)
    }
  }

  const handleDelete = async (item: ProviderItem) => {
    try {
      await deleteProvider(item.id)
      message.success('已删除')
      await refresh()
    } catch (err) {
      message.error(err instanceof Error ? err.message : '删除失败')
    }
  }

  const handleTest = async (item: ProviderItem) => {
    try {
      const result = await testProvider(item.id)
      if (result.ok) {
        message.success(`连接成功：${item.name}`)
      } else {
        message.error(result.message)
      }
    } catch (err) {
      message.error(err instanceof Error ? err.message : '测试失败')
    }
  }

  const handleToggle = async (item: ProviderItem, enabled: boolean) => {
    try {
      await updateProvider(item.id, { enabled })
      await refresh()
    } catch (err) {
      message.error(err instanceof Error ? err.message : '更新失败')
      await refresh()
    }
  }

  const columns: ColumnsType<ProviderItem> = [
    { title: '名称', dataIndex: 'name', key: 'name' },
    {
      title: '类型',
      dataIndex: 'type',
      key: 'type',
      render: (type: ProviderType) => <Tag>{type}</Tag>,
    },
    { title: '默认模型', dataIndex: 'default_model', key: 'default_model' },
    {
      title: 'Base URL',
      dataIndex: 'base_url',
      key: 'base_url',
      render: (url: string | null) => url ?? '—',
    },
    { title: 'API Key', dataIndex: 'api_key_masked', key: 'api_key_masked' },
    { title: '优先级', dataIndex: 'priority', key: 'priority', width: 80 },
    {
      title: '启用',
      dataIndex: 'enabled',
      key: 'enabled',
      width: 80,
      render: (_: unknown, record: ProviderItem) => (
        <Switch checked={record.enabled} onChange={(checked) => void handleToggle(record, checked)} />
      ),
    },
    {
      title: '操作',
      key: 'actions',
      width: 240,
      render: (_: unknown, record: ProviderItem) => (
        <Space>
          <Button size="small" onClick={() => openEdit(record)}>
            编辑
          </Button>
          <Button size="small" onClick={() => void handleTest(record)}>
            测试
          </Button>
          <Popconfirm title="确认删除该 Provider？" onConfirm={() => void handleDelete(record)}>
            <Button size="small" danger>
              删除
            </Button>
          </Popconfirm>
        </Space>
      ),
    },
  ]

  return (
    <div>
      <Space style={{ marginBottom: 16, width: '100%', justifyContent: 'space-between' }}>
        <h2 style={{ margin: 0 }}>Provider 管理</h2>
        <Button type="primary" onClick={openCreate}>
          新建 Provider
        </Button>
      </Space>
      <Table rowKey="id" dataSource={providers} columns={columns} loading={loading} />
      <Modal
        title={editing ? `编辑 ${editing.name}` : '新建 Provider'}
        open={modalOpen}
        onOk={() => void handleSubmit()}
        onCancel={() => setModalOpen(false)}
        confirmLoading={saving}
      >
        <Form form={form} layout="vertical" initialValues={{ enabled: true, priority: 0 }}>
          <Form.Item name="name" label="名称" rules={[{ required: true, message: '请输入名称' }]}>
            <Input placeholder="如 openai-gpt4o" />
          </Form.Item>
          <Form.Item name="type" label="类型" rules={[{ required: true, message: '请选择类型' }]}>
            <Select options={TYPE_OPTIONS} />
          </Form.Item>
          <Form.Item
            name="base_url"
            label="Base URL"
            rules={[
              {
                required: watchedType === 'ark' || watchedType === 'openai-compatible',
                message: '该类型必须提供 Base URL',
              },
            ]}
          >
            <Input placeholder="https://api.example.com/v1" />
          </Form.Item>
          <Form.Item
            name="api_key"
            label={editing ? 'API Key（留空表示不修改）' : 'API Key'}
            rules={[{ required: !editing, message: '请输入 API Key' }]}
          >
            <Input.Password placeholder={editing ? '不修改请留空' : 'sk-...'} />
          </Form.Item>
          <Form.Item
            name="default_model"
            label="默认模型"
            rules={[{ required: true, message: '请输入默认模型' }]}
          >
            <Input placeholder="如 gpt-4o-mini" />
          </Form.Item>
          <Space size="large">
            <Form.Item name="priority" label="优先级（越大越优先）">
              <InputNumber min={0} />
            </Form.Item>
            <Form.Item name="enabled" label="启用" valuePropName="checked">
              <Switch />
            </Form.Item>
          </Space>
        </Form>
      </Modal>
    </div>
  )
}

export default ProvidersPage
