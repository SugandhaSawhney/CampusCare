import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { api, ago } from '../api'
import { useAuth } from '../auth'
import RequestTable from '../components/RequestTable'
import { Badge, ErrorNote, Section, pretty } from '../components/ui'

const Impact = ({ c }) => (
  <div>
    <div className="text-2xl font-extrabold tabular-nums">{c.affected_count}{c.population ? <span className="text-ink-mute text-lg"> / {c.population}</span> : null}</div>
    <div className="text-xs text-ink-mute">students affected{c.affected_pct != null ? ` · ${c.affected_pct}% impact` : ''}</div>
    {c.affected_pct != null && <div className="h-1.5 rounded-full bg-paper-line mt-2 overflow-hidden"><div className="h-full bg-route" style={{ width: `${Math.min(100, c.affected_pct)}%` }} /></div>}
  </div>
)

export function Clusters() {
  const [rows, setRows] = useState(null)
  const [all, setAll] = useState(false)
  useEffect(() => { api(`/staff/clusters${all ? '?all=true' : ''}`).then(setRows) }, [all])
  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-extrabold">Issue clusters</h1>
          <p className="text-sm text-ink-soft max-w-3xl">Similar non-sensitive requests grouped for impact analysis. Each student's case keeps its own ID, SLA, status and resolution. Sensitive and mental-health cases are never clustered.</p>
        </div>
        <label className="text-sm font-semibold flex items-center gap-2"><input type="checkbox" checked={all} onChange={(e) => setAll(e.target.checked)} />Include single-case clusters</label>
      </div>
      {rows && rows.length === 0 && <div className="text-ink-mute text-sm">No clusters visible to you.</div>}
      <div className="grid md:grid-cols-2 xl:grid-cols-3 gap-4">
        {rows?.map((c) => (
          <Link key={c.id} to={`/staff/clusters/${c.id}`} className="card p-4 hover:border-route block">
            <div className="flex items-start justify-between gap-2">
              <div><div className="font-extrabold text-lg leading-tight">{c.label}</div><div className="text-sm text-ink-soft">{c.primary_department}{c.batch_label ? ` · ${c.batch_label}` : ''}</div></div>
              <Badge v={c.priority} />
            </div>
            <div className="mt-3"><Impact c={c} /></div>
            <div className="mt-3 flex items-center justify-between text-xs text-ink-mute">
              <span>{c.request_count} requests · {c.open_count} open · {c.scope}</span><Badge v={c.status === 'RESOLVED' ? 'RESOLVED' : 'APPROACHING'}>{pretty(c.status)}</Badge>
            </div>
            <div className="text-[11px] text-ink-mute mt-1">Last activity {ago(c.updated_at)}</div>
          </Link>
        ))}
      </div>
    </div>
  )
}

export function ClusterDetail() {
  const { id } = useParams()
  const { user } = useAuth()
  const [c, setC] = useState(null)
  const [err, setErr] = useState('')
  const load = () => api(`/staff/clusters/${id}`).then(setC).catch((e) => setErr(e.message))
  useEffect(() => { load() }, [id])
  if (err) return <ErrorNote error={err} />
  if (!c) return <div className="text-ink-mute">Loading…</div>
  const setStatus = (s) => api(`/staff/clusters/${id}/status`, { method: 'POST', body: { status: s } }).then(load).catch((e) => setErr(e.message))
  return (
    <div className="space-y-5">
      <Link to="/staff/clusters" className="text-sm text-route font-semibold">← All clusters</Link>
      <div className="grid md:grid-cols-4 gap-4">
        <div className="card p-4 md:col-span-2">
          <div className="text-xs font-bold text-ink-mute">CLUSTER</div>
          <h1 className="text-2xl font-extrabold">{c.label}</h1>
          <div className="text-sm text-ink-soft">{c.category} / {c.subcategory}{c.batch_label ? ` · ${c.batch_label}` : ''}</div>
          <div className="flex gap-2 mt-2"><Badge v={c.priority} /><Badge v="APPROACHING">{pretty(c.status)}</Badge><span className="text-xs font-semibold self-center">{c.scope}</span></div>
        </div>
        <div className="card p-4"><Impact c={c} /></div>
        <div className="card p-4">
          <div className="text-xs font-bold text-ink-mute">PRIMARY DEPARTMENT</div>
          <div className="font-extrabold">{c.primary_department}</div>
          {user.role !== 'STUDENT' && (
            <select className="input mt-2 !py-1" value="" onChange={(e) => e.target.value && setStatus(e.target.value)}>
              <option value="">Update investigation…</option>{['INVESTIGATING', 'ROOT_CAUSE_FOUND', 'FIX_DEPLOYED', 'MONITORING'].map((s) => <option key={s} value={s}>{pretty(s)}</option>)}
            </select>
          )}
        </div>
      </div>
      <div className="rounded-md bg-route-tint text-route-dark text-sm px-4 py-2 font-semibold">
        {c.request_count} individual requests: linked for impact analysis, never merged. Each keeps its own student, SLA, status and resolution.
      </div>
      <Section title="Individual requests in this cluster">
        <RequestTable rows={c.members} extra={{ header: 'Similarity', cell: (m) => <span className="text-xs tabular-nums">{m.similarity != null ? `${Math.round(m.similarity * 100)}%` : 'seed'}<span className="text-ink-mute"> {m.method}</span></span> }} />
      </Section>
    </div>
  )
}
