import { useEffect, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import {
  Account, AuditEntry, Recommendation,
  getAccount, updateAccountSettings, disconnectAccount, runNow,
  listAuditEntries, listRecommendations, updateRecommendation,
} from '../api/client'

export default function AccountDetail() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const [account, setAccount] = useState<Account | null>(null)
  const [audit, setAudit] = useState<AuditEntry[]>([])
  const [recs, setRecs] = useState<Recommendation[]>([])
  const [tab, setTab] = useState<'recommendations' | 'changes' | 'settings'>('recommendations')
  const [running, setRunning] = useState(false)
  const [runResult, setRunResult] = useState<string>('')

  function reload() {
    if (!id) return
    getAccount(id).then(setAccount)
    listAuditEntries(id).then(setAudit)
    listRecommendations(id, 'open').then(setRecs)
  }

  useEffect(reload, [id])

  async function handleRunNow() {
    if (!id) return
    setRunning(true)
    setRunResult('')
    try {
      const result = await runNow(id)
      setRunResult(JSON.stringify(result))
      reload()
    } finally {
      setRunning(false)
    }
  }

  async function handleRecAction(recId: string, status: 'dismissed' | 'applied') {
    if (!id) return
    await updateRecommendation(id, recId, status)
    setRecs((prev) => prev.filter((r) => r.id !== recId))
  }

  async function handleToggleDryRun() {
    if (!id || !account) return
    const updated = await updateAccountSettings(id, { dry_run: !account.dry_run })
    setAccount(updated)
  }

  async function handleToggleActive() {
    if (!id || !account) return
    const updated = await updateAccountSettings(id, { is_active: !account.is_active })
    setAccount(updated)
  }

  async function handleDisconnect() {
    if (!id) return
    if (!confirm('Disconnect this Google Ads account? This cannot be undone and all history will be deleted.')) return
    await disconnectAccount(id)
    navigate('/')
  }

  if (!account) return <div className="container"><p className="muted">Loading...</p></div>

  return (
    <div className="container">
      <Link to="/" className="muted">← Back</Link>
      <div className="flex-between" style={{ margin: '12px 0 20px 0' }}>
        <div>
          <h1 style={{ margin: 0 }}>{account.descriptive_name || `Account ${account.customer_id}`}</h1>
          <span className="muted">Customer ID: {account.customer_id}</span>
        </div>
        <div className="flex">
          {!account.is_active && <span className="badge badge-paused">Paused</span>}
          {account.is_active && account.dry_run && <span className="badge badge-dry">Dry run</span>}
          {account.is_active && !account.dry_run && <span className="badge badge-live">Live</span>}
          <button className="btn" onClick={handleRunNow} disabled={running}>
            {running ? 'Running...' : 'Run now'}
          </button>
        </div>
      </div>

      {runResult && <div className="card muted">Last manual run result: <code>{runResult}</code></div>}

      <div className="flex" style={{ marginBottom: 16, borderBottom: '1px solid #e5e5e5' }}>
        {(['recommendations', 'changes', 'settings'] as const).map((t) => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className="btn-secondary"
            style={{
              border: 'none', borderBottom: tab === t ? '2px solid #1a73e8' : '2px solid transparent',
              borderRadius: 0, background: 'none', padding: '10px 16px', cursor: 'pointer',
              fontWeight: tab === t ? 600 : 400,
            }}
          >
            {t === 'recommendations' && `Recommendations (${recs.length})`}
            {t === 'changes' && 'Change history'}
            {t === 'settings' && 'Settings'}
          </button>
        ))}
      </div>

      {tab === 'recommendations' && (
        <div className="card">
          <p className="muted">
            Budget and bidding changes are never applied automatically. Review each one and apply it
            yourself in Google Ads, then mark it here.
          </p>
          {recs.length === 0 && <p className="muted">No open recommendations right now.</p>}
          {recs.map((r) => (
            <div key={r.id} style={{ borderTop: '1px solid #eee', padding: '12px 0' }}>
              <div className="flex-between">
                <div>
                  <b>{r.campaign_name}</b>{' '}
                  <span className="badge" style={{ background: '#eef2ff', color: '#3730a3' }}>
                    {r.kind === 'budget' ? 'Budget' : 'Bid'}
                  </span>
                </div>
                <div className="flex">
                  <button className="btn btn-secondary" onClick={() => handleRecAction(r.id, 'dismissed')}>Dismiss</button>
                  <button className="btn" onClick={() => handleRecAction(r.id, 'applied')}>Mark applied</button>
                </div>
              </div>
              <p style={{ margin: '8px 0 0 0' }}>{r.detail}</p>
            </div>
          ))}
        </div>
      )}

      {tab === 'changes' && (
        <div className="card">
          <table>
            <thead>
              <tr><th>When</th><th>Action</th><th>Reason</th><th>Status</th></tr>
            </thead>
            <tbody>
              {audit.map((e) => (
                <tr key={e.id}>
                  <td className="muted">{new Date(e.timestamp).toLocaleString()}</td>
                  <td><code>{e.action}</code></td>
                  <td>{e.reason}</td>
                  <td>
                    {e.dry_run && <span className="badge badge-dry">dry run</span>}
                    {!e.dry_run && e.success && <span className="badge badge-live">applied</span>}
                    {!e.dry_run && !e.success && <span className="badge badge-paused" title={e.error || ''}>failed</span>}
                  </td>
                </tr>
              ))}
              {audit.length === 0 && (
                <tr><td colSpan={4} className="muted">No changes logged yet.</td></tr>
              )}
            </tbody>
          </table>
        </div>
      )}

      {tab === 'settings' && (
        <div className="card">
          <div className="flex-between" style={{ marginBottom: 16 }}>
            <div>
              <b>Dry run mode</b>
              <p className="muted" style={{ margin: '4px 0 0 0' }}>
                When on, the optimizer logs what it would do but makes no real changes.
              </p>
            </div>
            <button className="btn" onClick={handleToggleDryRun}>
              {account.dry_run ? 'Turn dry run OFF (go live)' : 'Turn dry run ON'}
            </button>
          </div>

          <div className="flex-between" style={{ marginBottom: 16 }}>
            <div>
              <b>Automation active</b>
              <p className="muted" style={{ margin: '4px 0 0 0' }}>
                Pausing stops the daily job from touching this account at all.
              </p>
            </div>
            <button className="btn btn-secondary" onClick={handleToggleActive}>
              {account.is_active ? 'Pause automation' : 'Resume automation'}
            </button>
          </div>

          <div style={{ marginBottom: 16 }}>
            <b>Notify email:</b> {account.notify_email}
          </div>
          <div style={{ marginBottom: 24 }}>
            <b>Max actions per run:</b> {account.max_actions_per_run}
          </div>

          <button className="btn btn-danger" onClick={handleDisconnect}>Disconnect this account</button>
        </div>
      )}
    </div>
  )
}
