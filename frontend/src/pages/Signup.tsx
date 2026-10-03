import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { signup } from '../api/client'

export default function Signup() {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const navigate = useNavigate()

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setError('')
    try {
      const data = await signup(email, password)
      localStorage.setItem('access_token', data.access_token)
      navigate('/')
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Could not sign up')
    }
  }

  return (
    <div className="container" style={{ maxWidth: 400, marginTop: 80 }}>
      <div className="card">
        <h2>Create account</h2>
        <form onSubmit={handleSubmit}>
          <div style={{ marginBottom: 12 }}>
            <label>Email</label>
            <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} required />
          </div>
          <div style={{ marginBottom: 12 }}>
            <label>Password</label>
            <input type="password" value={password} onChange={(e) => setPassword(e.target.value)}
                   minLength={8} required />
          </div>
          {error && <div className="error">{error}</div>}
          <button className="btn" type="submit" style={{ width: '100%' }}>Sign up</button>
        </form>
        <p className="muted" style={{ marginTop: 16 }}>
          Already have an account? <Link to="/login">Log in</Link>
        </p>
      </div>
    </div>
  )
}
