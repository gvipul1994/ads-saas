import { useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { listAccounts, startGoogleConnect, Account } from '../api/client'

export default function Dashboard() {
  const [accounts, setAccounts] = useState<Account[]>([])
  const [loading, setLoading] = useState(true)
  const navigate = useNavigate()

  useEffect(() => {
    listAccounts().then(setAccounts).finally(() => setLoading(false))
  }, [])

  function logout() {
    localStorage.removeItem('access_token')
    navigate('/login')
  }

  return (
    <div className="container">
      <div className="flex-between" style={{ marginBottom: 20 }}>
        <h1>Ads Optimizer</h1>
        <div className="flex">
          <button className="btn" onClick={() => startGoogleConnect()}>+ Connect Google Ads account</button>
          <button className="btn btn-secondary" onClick={logout}>Log out</button>
        </div>
      </div>

      {loading && <p className="muted">Loading...</p>}

      {!loading && accounts.length === 0 && (
        <div className="card">
          <p>No Google Ads accounts connected yet.</p>
          <p className="muted">
            Click "Connect Google Ads account" above to grant access once — after that,
            the optimizer runs automatically every day.
          </p>
        </div>
      )}

      {accounts.map((acc) => (
        <Link to={`/accounts/${acc.id}`} key={acc.id} style={{ textDecoration: 'none', color: 'inherit' }}>
          <div className="card flex-between">
            <div>
              <h3 style={{ margin: '0 0 4px 0' }}>{acc.descriptive_name || `Account ${acc.customer_id}`}</h3>
              <span className="muted">Customer ID: {acc.customer_id}</span>
              <div style={{ marginTop: 8 }}>
                {!acc.is_active && <span className="badge badge-paused">Paused</span>}
                {acc.is_active && acc.dry_run && <span className="badge badge-dry">Dry run</span>}
                {acc.is_active && !acc.dry_run && <span className="badge badge-live">Live</span>}
              </div>
            </div>
            <div className="muted">
              {acc.last_run_at ? `Last run: ${new Date(acc.last_run_at).toLocaleString()}` : 'Never run yet'}
            </div>
          </div>
        </Link>
      ))}
    </div>
  )
}
