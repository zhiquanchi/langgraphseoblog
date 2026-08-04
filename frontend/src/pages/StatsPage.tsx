import { useEffect, useState } from 'react'
import { Card, Col, Row, Statistic, Table, Tag, Typography } from 'antd'
import type { ColumnsType } from 'antd/es/table'
import { getCalls, getStats } from '../api/stats'
import type { LLMCallItem, NodeStat, ProviderStat, StatsOut } from '../api/stats'

const { Title } = Typography

const providerColumns: ColumnsType<ProviderStat> = [
  { title: 'Provider', dataIndex: 'provider_name', key: 'provider_name' },
  { title: '调用次数', dataIndex: 'calls', key: 'calls' },
  {
    title: '成功率',
    dataIndex: 'success_rate',
    key: 'success_rate',
    render: (rate: number) => `${(rate * 100).toFixed(1)}%`,
  },
  { title: '总 Token', dataIndex: 'total_tokens', key: 'total_tokens' },
  {
    title: '平均耗时 (ms)',
    dataIndex: 'avg_latency_ms',
    key: 'avg_latency_ms',
    render: (ms: number) => ms.toFixed(0),
  },
  { title: '降级次数', dataIndex: 'failovers', key: 'failovers' },
]

const nodeColumns: ColumnsType<NodeStat> = [
  { title: '节点', dataIndex: 'node', key: 'node' },
  { title: '调用次数', dataIndex: 'calls', key: 'calls' },
  {
    title: '成功率',
    dataIndex: 'success_rate',
    key: 'success_rate',
    render: (rate: number) => `${(rate * 100).toFixed(1)}%`,
  },
  { title: '总 Token', dataIndex: 'total_tokens', key: 'total_tokens' },
  {
    title: '平均耗时 (ms)',
    dataIndex: 'avg_latency_ms',
    key: 'avg_latency_ms',
    render: (ms: number) => ms.toFixed(0),
  },
]

const callColumns: ColumnsType<LLMCallItem> = [
  { title: '时间', dataIndex: 'created_at', key: 'created_at' },
  { title: 'Provider', dataIndex: 'provider_name', key: 'provider_name' },
  { title: '模型', dataIndex: 'model', key: 'model' },
  { title: '节点', dataIndex: 'node', key: 'node', render: (node: string | null) => node ?? '—' },
  {
    title: '结果',
    dataIndex: 'success',
    key: 'success',
    render: (success: boolean) =>
      success ? <Tag color="green">成功</Tag> : <Tag color="red">失败</Tag>,
  },
  { title: 'Token', dataIndex: 'total_tokens', key: 'total_tokens' },
  { title: '耗时 (ms)', dataIndex: 'latency_ms', key: 'latency_ms' },
  {
    title: '错误',
    dataIndex: 'error',
    key: 'error',
    ellipsis: true,
    render: (error: string | null) => error ?? '—',
  },
]

function StatsPage() {
  const [stats, setStats] = useState<StatsOut | null>(null)
  const [calls, setCalls] = useState<LLMCallItem[]>([])

  useEffect(() => {
    getStats()
      .then(setStats)
      .catch(() => setStats(null))
    getCalls(50)
      .then(setCalls)
      .catch(() => setCalls([]))
  }, [])

  const totalCalls = stats?.by_provider.reduce((acc, p) => acc + p.calls, 0) ?? 0
  const totalTokens = stats?.by_provider.reduce((acc, p) => acc + p.total_tokens, 0) ?? 0
  const avgSuccess =
    stats && stats.by_provider.length > 0
      ? stats.by_provider.reduce((acc, p) => acc + p.success_rate, 0) / stats.by_provider.length
      : 0
  const avgLatency =
    stats && stats.by_provider.length > 0
      ? stats.by_provider.reduce((acc, p) => acc + p.avg_latency_ms, 0) / stats.by_provider.length
      : 0

  return (
    <div>
      <Title level={2}>调用统计</Title>
      <Row gutter={16} style={{ marginBottom: 24 }}>
        <Col span={6}>
          <Card>
            <Statistic title="总调用次数" value={totalCalls} />
          </Card>
        </Col>
        <Col span={6}>
          <Card>
            <Statistic title="总 Token" value={totalTokens} />
          </Card>
        </Col>
        <Col span={6}>
          <Card>
            <Statistic title="平均成功率" value={avgSuccess * 100} suffix="%" precision={1} />
          </Card>
        </Col>
        <Col span={6}>
          <Card>
            <Statistic title="平均耗时 (ms)" value={avgLatency} precision={0} />
          </Card>
        </Col>
      </Row>
      <Card title="按 Provider" style={{ marginBottom: 24 }}>
        <Table
          rowKey="provider_name"
          dataSource={stats?.by_provider ?? []}
          columns={providerColumns}
          pagination={false}
          size="small"
        />
      </Card>
      <Card title="按节点" style={{ marginBottom: 24 }}>
        <Table
          rowKey="node"
          dataSource={stats?.by_node ?? []}
          columns={nodeColumns}
          pagination={false}
          size="small"
        />
      </Card>
      <Card title="最近调用明细">
        <Table
          rowKey={(record) => `${record.created_at}-${record.provider_name}-${record.latency_ms}`}
          dataSource={calls}
          columns={callColumns}
          size="small"
        />
      </Card>
    </div>
  )
}

export default StatsPage
