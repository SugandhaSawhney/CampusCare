// Token kept in sessionStorage only (cleared when the tab closes). No case data is persisted client-side.
const KEY = 'cc_token'
export const getToken = () => sessionStorage.getItem(KEY)
export const setToken = (t) => (t ? sessionStorage.setItem(KEY, t) : sessionStorage.removeItem(KEY))

export async function api(path, { method = 'GET', body } = {}) {
  const res = await fetch(`/api${path}`, {
    method,
    headers: { 'Content-Type': 'application/json', ...(getToken() ? { Authorization: `Bearer ${getToken()}` } : {}) },
    body: body ? JSON.stringify(body) : undefined,
  })
  if (res.status === 401 && path !== '/auth/login') {
    setToken(null)
    window.location.href = '/login'
  }
  const data = await res.json().catch(() => ({}))
  if (!res.ok) {
    const d = data.detail
    throw new Error(typeof d === 'string' ? d : Array.isArray(d) ? d.map((x) => x.msg).join('; ') : 'Request failed')
  }
  return data
}

export const fmt = (iso) => (iso ? new Date(iso).toLocaleString([], { dateStyle: 'medium', timeStyle: 'short' }) : '—')
export const ago = (iso) => {
  if (!iso) return '—'
  const m = Math.round((Date.now() - new Date(iso)) / 60000)
  if (m < 1) return 'just now'
  if (m < 60) return `${m}m ago`
  if (m < 1440) return `${Math.round(m / 60)}h ago`
  return `${Math.round(m / 1440)}d ago`
}
export const remaining = (s) => {
  if (s == null) return ''
  const neg = s < 0
  const a = Math.abs(s)
  const h = Math.floor(a / 3600), m = Math.floor((a % 3600) / 60)
  const t = h >= 24 ? `${Math.floor(h / 24)}d ${h % 24}h` : `${h}h ${m}m`
  return neg ? `overdue by ${t}` : `${t} left`
}
