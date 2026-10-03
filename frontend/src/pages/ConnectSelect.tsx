import { useEffect, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { getPendingConnection, finalizeConnection } from '../api/client'

export default function ConnectSelect() {
  const [params] = useSearchParams()
  const pendingId = params.get('pending_id') || ''
  const [customerIds, setCustomerIds] = useState<string[]>([])
  const [selected, setSelected] = useState('')
  const [notifyEmail, setNotifyEmail] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(true)
  const navigate = useNavigate()

  useEffect(() => {
    if (!pendingId) {
      setError('Missing pending connection id.')
      setLoading(false)
      return
    }
    getPendingConnection(pendingId)
      .then((data) => {
        setCustomerIds(data.customer_ids)
        if (data.customer_ids.length > 0) setSelected(data.customer_ids[0])
      })
      .catch(() => setError('This connection link has expired. Please reconnect.'))
      .finally(() => setLoading(false))
  }, [pendingId])

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setError('')
    try {
      await finalizeConnection(pendingId, selected, notifyEmail)
      navigate('/')
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Could not finish connecting this account')
    }
  }

  return (
    <div className="container" style={{ maxWidth: 480, marginTop: 60 }}>
      <div className="card">
        <h2>Finish connecting Google Ads</h2>
        {loading && <p className="muted">Loading...</p>}
        {error && <div className="error">{error}</div>}

        {!loading && !error && (
          <form onSubmit={handleSubmit}>
            <div style={{ marginBottom: 12 }}>
              <label>Google Ads account</label>
              <select value={selected} onChange={(e) => setSelected(e.target.value)}>
                {customerIds.map((cid) => (
                  <option key={cid} value={cid}>{cid}</option>
                ))}
              </select>
              <p className="muted">
                This is the Google login's accessible account list. If the wrong one shows up,
                sign in with a different Google account on the connect screen next time.
              </p>
            </div>
            <div style={{ marginBottom: 16 }}>
              <label>Send recommendations &amp; weekly report to</label>
              <input type="email" value={notifyEmail} onChange={(e) => setNotifyEmail(e.target.value)} required />
            </div>
            <button className="btn" type="submit" style={{ width: '100%' }} disabled={!selected}>
              Finish connecting
            </button>
          </form>
        )}
      </div>
    </div>
  )
}
