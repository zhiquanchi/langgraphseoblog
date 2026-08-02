import { useEffect, useState } from 'react'
import './App.css'

interface HealthResponse {
  status: string
}

function App() {
  const [backendStatus, setBackendStatus] = useState('checking...')

  useEffect(() => {
    fetch('/api/health')
      .then((res) => res.json() as Promise<HealthResponse>)
      .then((data) => setBackendStatus(data.status))
      .catch(() => setBackendStatus('unreachable'))
  }, [])

  return (
    <main className="app">
      <h1>LangGraph SEO Blog</h1>
      <p>
        Backend status: <strong>{backendStatus}</strong>
      </p>
    </main>
  )
}

export default App
