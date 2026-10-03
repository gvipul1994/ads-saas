import axios from 'axios'

const API_BASE = import.meta.env.VITE_API_BASE || 'http://localhost:8000'

export const api = axios.create({ baseURL: API_BASE })

api.interceptors.request.use((config) => {
  const token = localStorage.getItem('access_token')
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})

api.interceptors.response.use(
  (res) => res,
  (err) => {
    if (err.response?.status === 401) {
      localStorage.removeItem('access_token')
      window.location.href = '/login'
    }
    return Promise.reject(err)
  }
)

// --- Types matching backend schemas.py ---
export interface Account {
  id: string
  customer_id: string
  descriptive_name: string | null
  notify_email: string
  dry_run: boolean
  max_actions_per_run: number
  is_active: boolean
  connected_at: string
  last_run_at: string | null
}

export interface AuditEntry {
  id: string
  timestamp: string
  action: string
  params: Record<string, unknown>
  reason: string
  dry_run: boolean
  success: boolean
  error: string | null
}

export interface Recommendation {
  id: string
  kind: 'budget' | 'bid'
  campaign_id: string
  campaign_name: string
  detail: string
  metrics: Record<string, number>
  status: 'open' | 'dismissed' | 'applied'
  created_at: string
}

// --- Auth ---
export async function signup(email: string, password: string) {
  const { data } = await api.post('/auth/signup', { email, password })
  return data
}

export async function login(email: string, password: string) {
  const { data } = await api.post('/auth/login', { email, password })
  return data
}

// --- Accounts ---
export async function listAccounts(): Promise<Account[]> {
  const { data } = await api.get('/accounts')
  return data
}

export async function getAccount(id: string): Promise<Account> {
  const { data } = await api.get(`/accounts/${id}`)
  return data
}

export async function updateAccountSettings(id: string, body: Partial<Account>): Promise<Account> {
  const { data } = await api.patch(`/accounts/${id}`, body)
  return data
}

export async function disconnectAccount(id: string) {
  const { data } = await api.delete(`/accounts/${id}`)
  return data
}

export async function runNow(id: string) {
  const { data } = await api.post(`/accounts/${id}/run-now`)
  return data
}

// --- OAuth connect flow ---
export async function startGoogleConnect() {
  // Authenticated call (JWT attached by the axios interceptor above) to get
  // the Google consent URL, then a real browser navigation to Google - the
  // navigation itself can't carry our JWT, which is why we don't just
  // redirect straight to the backend's /start route.
  const { data } = await api.get('/oauth/google/start')
  window.location.href = data.auth_url
}

export async function getPendingConnection(pendingId: string) {
  const { data } = await api.get(`/oauth/google/pending/${pendingId}`)
  return data as { pending_id: string; customer_ids: string[] }
}

export async function finalizeConnection(pendingId: string, customerId: string, notifyEmail: string) {
  const { data } = await api.post('/oauth/google/finalize', null, {
    params: { pending_id: pendingId, customer_id: customerId, notify_email: notifyEmail },
  })
  return data
}

// --- Audit ---
export async function listAuditEntries(accountId: string): Promise<AuditEntry[]> {
  const { data } = await api.get(`/accounts/${accountId}/audit`)
  return data
}

// --- Recommendations ---
export async function listRecommendations(accountId: string, status?: string): Promise<Recommendation[]> {
  const { data } = await api.get(`/accounts/${accountId}/recommendations`, { params: { status } })
  return data
}

export async function updateRecommendation(accountId: string, recId: string, status: 'dismissed' | 'applied') {
  const { data } = await api.patch(`/accounts/${accountId}/recommendations/${recId}`, { status })
  return data
}
