import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { login } from '../api/client'

export default function Login() {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const navigate = useNavigate()

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setError('')
    try {
      const data = await login(email, password)
      localStorage.setItem('access_token', data.access_token)
      navigate('/')
    } catch {
      setError('Incorrect email or password')
    }
  }

  return (
    <div className="container" style={{ maxWidth: 400, marginTop: 80 }}>
      <div className="card">
        <h2>Log in</h2>
        <form onSubmit={handleSubmit}>
          <div style={{ marginBottom: 12 }}>
            <label>Email</label>
            <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} required />
          </div>
          <div style={{ marginBottom: 12 }}>
            <label>Password</label>
            <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} required />
          </div>
          {error && <div className="error">{error}</div>}
          <button className="btn" type="submit" style={{ width: '100%' }}>Log in</button>
        </form>
        <p className="muted" style={{ marginTop: 16 }}>
          No account? <Link to="/signup">Sign up</Link>
        </p>
      </div>
    </div>
  )
}
