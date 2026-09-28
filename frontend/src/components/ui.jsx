import { useEffect, useState } from 'react'
import { Link, NavLink, useNavigate } from 'react-router-dom'
import { api, ago, remaining } from '../api'
import { useAuth } from '../auth'

const tone = {
  CRITICAL: 'bg-breach text-white', HIGH: 'bg-breach-tint text-breach', MEDIUM: 'bg-signal-tint text-signal', LOW: 'bg-paper text-ink-soft',
  NORMAL: 'bg-paper text-ink-soft', CONFIDENTIAL: 'bg-restricted-tint text-restricted', 'HIGH-S': 'bg-restricted text-white',
  WITHIN: 'bg-route-tint text-route-dark', APPROACHING: 'bg-signal-tint text-signal', BREACHED: 'bg-breach text-white',
  MET: 'bg-route-tint text-route-dark', RESOLVED_LATE: 'bg-signal-tint text-signal', PAUSED: 'bg-paper text-ink-soft', NONE: 'bg-paper text-ink-soft',
  AWAITING_HUMAN_REVIEW: 'bg-signal-tint text-signal', ESCALATED: 'bg-breach-tint text-breach', RESOLVED: 'bg-route-tint text-route-dark',
  CLOSED: 'bg-paper text-ink-mute', ASSIGNED: 'bg-sky-50 text-sky-800', IN_PROGRESS: 'bg-sky-100 text-sky-900',
  WAITING_FOR_STUDENT: 'bg-paper text-ink-soft', REOPENED: 'bg-signal-tint text-signal', NEW: 'bg-paper text-ink-soft',
}
const pretty = (s) => (s || '').replaceAll('_', ' ').toLowerCase().replace(/^\w/, (c) => c.toUpperCase())

export function Badge({ v, kind, children }) {
  if (!v && !children) return null
  const key = kind === 'sens' && v === 'HIGH' ? 'HIGH-S' : v
  return <span className={`inline-flex items-center rounded px-2 py-0.5 text-xs font-semibold whitespace-nowrap ${tone[key] || 'bg-paper text-ink-soft'}`}>{children || (kind === 'sens' && v === 'HIGH' ? 'Restricted' : pretty(v))}</span>
}

export function SlaBadge({ sla, status }) {
  const st = sla?.status || status
  return (
    <span className="inline-flex flex-col">
      <Badge v={st}>{st === 'WITHIN' ? 'Within SLA' : st === 'APPROACHING' ? 'Approaching SLA' : st === 'BREACHED' ? 'SLA breached' : pretty(st)}</Badge>
      {sla?.seconds_remaining != null && <span className="text-[11px] text-ink-mute mt-0.5">{remaining(sla.seconds_remaining)}</span>}
    </span>
  )
}

export function Confidence({ value, big }) {
  if (value == null) return <span className="text-ink-mute">—</span>
  const p = Math.round(value * 100)
  const c = value >= 0.85 ? 'bg-route' : value >= 0.6 ? 'bg-signal' : 'bg-breach'
  return (
    <span className="inline-flex items-center gap-2">
      <span className={`relative ${big ? 'w-28 h-2' : 'w-14 h-1.5'} rounded-full bg-paper-line overflow-hidden`}>
        <span className={`absolute inset-y-0 left-0 ${c}`} style={{ width: `${p}%` }} />
      </span>
      <span className={`${big ? 'text-lg font-bold' : 'text-xs font-semibold'} tabular-nums`}>{p}%</span>
    </span>
  )
}

/** The signature element: the visible path a request took, from student to owner. */
export function RouteTrace({ steps }) {
  return (
    <ol className="flex flex-wrap items-stretch gap-y-3">
      {steps.map((s, i) => (
        <li key={i} className="flex items-stretch">
          <div className={`rounded-md border px-3 py-2 min-w-[8.5rem] ${s.state === 'active' ? 'border-route bg-route-tint' : s.state === 'warn' ? 'border-signal bg-signal-tint' : s.state === 'restricted' ? 'border-restricted bg-restricted-tint' : s.state === 'pending' ? 'border-dashed border-paper-line bg-white' : 'border-paper-line bg-white'}`}>
            <div className="text-[11px] font-semibold text-ink-mute">{s.label}</div>
            <div className="text-sm font-bold leading-snug">{s.value}</div>
            {s.sub && <div className="text-xs text-ink-soft mt-0.5">{s.sub}</div>}
          </div>
          {i < steps.length - 1 && (
            <div className="flex items-center px-1.5" aria-hidden>
              <svg width="28" height="12" viewBox="0 0 28 12"><path d="M0 6h24M19 1l5 5-5 5" fill="none" stroke="#0E7C7B" strokeWidth="2" /></svg>
            </div>
          )}
        </li>
      ))}
    </ol>
  )
}

export function Stat({ label, value, tone: t, to }) {
  const inner = (
    <div className={`card px-4 py-3 h-full ${t === 'warn' ? 'border-signal' : t === 'bad' ? 'border-breach' : ''}`}>
      <div className="text-2xl font-extrabold tabular-nums">{value ?? '—'}</div>
      <div className="text-xs font-semibold text-ink-mute mt-0.5">{label}</div>
    </div>
  )
  return to ? <Link to={to} className="block hover:opacity-90">{inner}</Link> : inner
}

export function Section({ title, right, children, className = '' }) {
  return (
    <section className={`card ${className}`}>
      {(title || right) && (
        <header className="flex items-center justify-between gap-3 px-4 py-3 border-b border-paper-line">
          <h2 className="text-sm font-bold">{title}</h2>
          {right}
        </header>
      )}
      <div className="p-4">{children}</div>
    </section>
  )
}

export function Field({ label, children }) {
  return (
    <div className="py-1.5 grid grid-cols-[9rem_1fr] gap-3 text-sm">
      <div className="text-ink-mute font-medium">{label}</div>
      <div className="min-w-0">{children ?? '—'}</div>
    </div>
  )
}

export function ErrorNote({ error }) {
  return error ? <div className="rounded-md bg-breach-tint text-breach text-sm px-3 py-2">{error}</div> : null
}

function Notifications() {
  const [open, setOpen] = useState(false)
  const [items, setItems] = useState([])
  const load = () => api('/notifications').then(setItems).catch(() => {})
  useEffect(() => { load(); const t = setInterval(load, 30000); return () => clearInterval(t) }, [])
  const unread = items.filter((n) => !n.read).length
  return (
    <div className="relative">
      <button className="btn-ghost !py-1.5" onClick={() => { setOpen(!open); if (!open && unread) api('/notifications/read-all', { method: 'POST' }).then(load) }}>
        Alerts{unread > 0 && <span className="rounded-full bg-breach text-white text-[11px] px-1.5">{unread}</span>}
      </button>
      {open && (
        <div className="absolute right-0 mt-2 w-80 max-h-96 overflow-auto card shadow-lg z-20">
          {items.length === 0 && <div className="p-3 text-sm text-ink-mute">No notifications</div>}
          {items.map((n) => (
            <div key={n.id} className="px-3 py-2 border-b border-paper-line text-sm">
              <div className={n.kind === 'EMERGENCY' || n.kind === 'ESCALATION' ? 'text-breach font-semibold' : ''}>{n.message}</div>
              <div className="text-[11px] text-ink-mute">{ago(n.created_at)}</div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

export function Layout({ children }) {
  const { user, logout } = useAuth()
  const nav = useNavigate()
  const r = user?.role
  const links =
    r === 'STUDENT' ? [['/student/dashboard', 'Home'], ['/student/new-request', 'Get support'], ['/student/requests', 'My requests']]
      : [
          ...(r === 'DEAN' ? [['/dean/dashboard', 'Oversight']] : [['/staff/dashboard', 'Dashboard']]),
          ...(['TRIAGE_AGENT', 'ADMIN'].includes(r) ? [['/staff/triage', 'Human triage']] : []),
          ['/staff/clusters', 'Clusters'], ['/staff/escalations', 'Escalations'],
          ...(r === 'ADMIN' ? [['/admin', 'Admin']] : []),
        ]
  return (
    <div className="min-h-screen">
      <header className="bg-ink text-white">
        <div className="max-w-7xl mx-auto px-4 h-14 flex items-center gap-6">
          <Link to="/" className="flex items-center gap-2 font-extrabold tracking-tight">
            <svg width="22" height="22" viewBox="0 0 22 22" aria-hidden><circle cx="4" cy="11" r="3" fill="#5FD4CF" /><path d="M7 11h6l4-6M13 11l4 6" stroke="#5FD4CF" strokeWidth="2" fill="none" /><circle cx="18" cy="5" r="2.2" fill="#fff" /><circle cx="18" cy="17" r="2.2" fill="#fff" /></svg>
            CampusCare
          </Link>
          <nav className="flex gap-1 overflow-x-auto">
            {links.map(([to, l]) => (
              <NavLink key={to} to={to} className={({ isActive }) => `px-3 py-1.5 rounded text-sm font-semibold whitespace-nowrap ${isActive ? 'bg-white/15' : 'text-white/75 hover:text-white'}`}>{l}</NavLink>
            ))}
          </nav>
          <div className="ml-auto flex items-center gap-3 text-ink">
            <Notifications />
            <div className="hidden md:block text-right text-white leading-tight">
              <div className="text-sm font-semibold">{user?.full_name}</div>
              <div className="text-[11px] text-white/60">{pretty(r)}{user?.department ? `, ${user.department}` : ''}</div>
            </div>
            <button className="text-sm text-white/80 hover:text-white" onClick={() => { logout(); nav('/login') }}>Sign out</button>
          </div>
        </div>
      </header>
      <main className="max-w-7xl mx-auto px-4 py-6">{children}</main>
    </div>
  )
}

export { pretty }
