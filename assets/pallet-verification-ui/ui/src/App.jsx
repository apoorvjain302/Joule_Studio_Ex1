import { useState } from 'react'
import {
  ShellBar,
  Page,
  FlexBox,
} from '@ui5/webcomponents-react'
import VerifyPanel from './components/VerifyPanel.jsx'
import ResultPanel from './components/ResultPanel.jsx'
import './App.css'

export default function App() {
  const [result, setResult] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)

  const handleVerify = async ({ deliveryOrder, imageUrl, channel }) => {
    setLoading(true)
    setError(null)
    setResult(null)
    try {
      const resp = await fetch('/api/verify', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ deliveryOrder, imageUrl, channel }),
      })
      const data = await resp.json()
      if (!resp.ok) {
        setError(data?.error?.message || `Request failed: ${resp.status}`)
      } else {
        setResult(data?.value ?? data)
      }
    } catch (err) {
      setError(`Network error: ${err.message}`)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="app-shell">
      <ShellBar
        primaryTitle="EWM Pallet Verification"
        secondaryTitle="AI-Powered Warehouse Verification"
        logo={
          <img
            src="https://www.sap.com/dam/application/shared/logos/sap-logo-svg.svg"
            alt="SAP"
            style={{ height: '32px' }}
          />
        }
      />
      <Page className="app-page">
        <FlexBox className="app-content" wrap="Wrap" alignItems="Start">
          <VerifyPanel onVerify={handleVerify} loading={loading} />
          <ResultPanel result={result} error={error} loading={loading} />
        </FlexBox>
      </Page>
    </div>
  )
}
