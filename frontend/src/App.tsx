import { Layout, Menu } from 'antd'
import { Link, Route, Routes, useLocation } from 'react-router-dom'
import GeneratePage from './pages/GeneratePage'
import ProvidersPage from './pages/ProvidersPage'
import StatsPage from './pages/StatsPage'

const { Header, Content } = Layout

function App() {
  const location = useLocation()
  const selectedKey = location.pathname.startsWith('/providers')
    ? '/providers'
    : location.pathname.startsWith('/stats')
      ? '/stats'
      : '/'

  return (
    <Layout style={{ minHeight: '100vh' }}>
      <Header>
        <Menu
          theme="dark"
          mode="horizontal"
          selectedKeys={[selectedKey]}
          items={[
            { key: '/', label: <Link to="/">博客生成</Link> },
            { key: '/providers', label: <Link to="/providers">Provider 管理</Link> },
            { key: '/stats', label: <Link to="/stats">调用统计</Link> },
          ]}
        />
      </Header>
      <Content style={{ padding: 24 }}>
        <Routes>
          <Route path="/" element={<GeneratePage />} />
          <Route path="/providers" element={<ProvidersPage />} />
          <Route path="/stats" element={<StatsPage />} />
        </Routes>
      </Content>
    </Layout>
  )
}

export default App
