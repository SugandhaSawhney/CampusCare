import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { Bar, BarChart, Cell, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { api } from '../api'
import { useAuth } from '../auth'
import RequestTable from '../components/RequestTable'
import { Section, Stat } from '../components/ui'

const PRIO_COLORS = { LOW: '#9AA5B4', MEDIUM: '#B7791F', HIGH: '#E07A5F', CRITICAL: '#C0392B' }

export function Analytics({ a }) {
  if (!a) return null
  return (
    <div className="grid lg:grid-cols-3 gap-4">
      <Section title="Requests by department" className="lg:col-span-2">
        <div className="h-56">
          <ResponsiveContainer>
            <BarChart data={a.by_department} layout="vertical" margin={{ left: 40 }}>
              <XAxis type="number" allowDecimals={false} tick={{ fontSize: 11 }} />
              <YAxis type="category" dataKey="name" width={150} tick={{ fontSize: 11 }} />
              <Tooltip />
              <Bar dataKey="count" fill="#0E7C7B" radius={[0, 3, 3, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </Section>
      <Section title="Routing quality">
        <dl className="grid grid-cols-2 gap-3 text-sm">
          {[['AI auto-routed', `${a.auto_route_rate}%`], ['Human fallback', `${a.human_fallback_rate}%`], ['Avg. time to route', a.avg_routing_minutes != null ? `${a.avg_routing_minutes} min` : '—'],
            ['SLA breaches', a.sla_breach_count], ['Reassignments', a.reassignment_count], ['Multi-department', a.multi_department_cases],
            ['Sensitive (count only)', a.sensitive_cases_total]].map(([k, v]) => (
            <div key={k}><dt className="text-ink-mute text-xs font-semibold">{k}</dt><dd className="text-lg font-extrabold tabular-nums">{v}</dd></div>
          ))}
        </dl>
        <div className="h-24 mt-3">
          <ResponsiveContainer>
            <BarChart data={a.by_priority}><XAxis dataKey="name" tick={{ fontSize: 10 }} /><Tooltip />
              <Bar dataKey="count">{a.by_priority.map((p) => <Cell key={p.name} fill={PRIO_COLORS[p.name]} />)}</Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
        <div className="text-[11px] text-ink-mute mt-2">Classifier: {a.engine}</div>
      </Section>
      {a.top_clusters.length > 0 && (
        <Section title="Most affected issue clusters" className="lg:col-span-2">
          <ul className="space-y-2">
            {a.top_clusters.map((c) => (
              <li key={c.id}><Link to={`/staff/clusters/${c.id}`} className="flex items-center gap-3 hover:bg-paper rounded -mx-2 px-2 py-1">
                <span className="font-semibold flex-1">{c.label}</span>
                <span className="text-sm text-ink-soft">{c.primary_department}</span>
                <span className="text-sm tabular-nums font-bold">{c.affected_count}{c.population ? ` / ${c.population}` : ''} students</span>
                {c.affected_pct != null && <span className="text-xs text-ink-mute w-12 text-right">{c.affected_pct}%</span>}
              </Link></li>
            ))}
          </ul>
        </Section>
      )}
      {a.routing_mismatches.length > 0 && (
        <Section title="Potential routing rule mismatch detected">
          <ul className="text-sm space-y-1.5">
            {a.routing_mismatches.map((r) => <li key={r.id}><Link className="text-route font-semibold" to={`/staff/requests/${r.id}`}>{r.request_number}</Link> bounced between departments ({r.reassignment_count} reassignments)</li>)}
          </ul>
        </Section>
      )}
    </div>
  )
}

export default function StaffDashboard() {
  const { user } = useAuth()
  const [d, setD] = useState(null)
  const [rows, setRows] = useState([])
  const [depts, setDepts] = useState([])
  const [f, setF] = useState({ department: '', priority: '', status: '', sensitivity: '', scope: '', sla: '', conf: '', mine: false })

  useEffect(() => { api('/staff/dashboard').then(setD); api('/departments').then(setDepts) }, [])
  useEffect(() => {
    const p = new URLSearchParams()
    Object.entries(f).forEach(([k, v]) => { if (v && k !== 'conf') p.set(k, v) })
    if (f.conf === 'high') p.set('min_conf', 0.85)
    if (f.conf === 'medium') { p.set('min_conf', 0.6); p.set('max_conf', 0.85) }
    if (f.conf === 'low') p.set('max_conf', 0.6)
    api(`/staff/requests?${p}`).then(setRows)
  }, [f])
  const c = d?.cards || {}
  const sel = (k, opts, label) => (
    <select className="input !w-auto !py-1.5" value={f[k]} onChange={(e) => setF({ ...f, [k]: e.target.value })} aria-label={label}>
      <option value="">{label}: all</option>
      {opts.map((o) => (Array.isArray(o) ? <option key={o[0]} value={o[0]}>{o[1]}</option> : <option key={o} value={o}>{o.replaceAll('_', ' ')}</option>))}
    </select>
  )
  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-extrabold">{user.role === 'DEPARTMENT_STAFF' ? `${user.department} desk` : 'Routing overview'}</h1>
          <p className="text-ink-soft text-sm">What is the issue, where is it routed, why, and is it at risk.</p>
        </div>
        {user.role !== 'DEPARTMENT_STAFF' && <Link to="/staff/triage" className="btn-primary">Open human triage queue ({c.human_review ?? 0})</Link>}
      </div>
      <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-7 gap-3">
        <Stat label="Open requests" value={c.total_open} />
        <Stat label="Human review queue" value={c.human_review} tone={c.human_review ? 'warn' : ''} to={user.role !== 'DEPARTMENT_STAFF' ? '/staff/triage' : undefined} />
        <Stat label="High priority" value={c.high_priority} />
        <Stat label="SLA at risk" value={c.sla_at_risk} tone={c.sla_at_risk ? 'warn' : ''} />
        <Stat label="SLA breached" value={c.sla_breached} tone={c.sla_breached ? 'bad' : ''} />
        <Stat label="Active clusters" value={c.active_clusters} to="/staff/clusters" />
        <Stat label="Escalated" value={c.escalated} tone={c.escalated ? 'bad' : ''} to="/staff/escalations" />
      </div>
      <Section title="Requests" right={<span className="text-xs text-ink-mute">{rows.length} shown</span>}>
        <div className="flex flex-wrap gap-2 mb-4">
          {user.role !== 'DEPARTMENT_STAFF' && sel('department', depts.map((x) => x.name), 'Department')}
          {sel('priority', ['CRITICAL', 'HIGH', 'MEDIUM', 'LOW'], 'Priority')}
          {sel('status', ['AWAITING_HUMAN_REVIEW', 'ASSIGNED', 'IN_PROGRESS', 'WAITING_FOR_STUDENT', 'ESCALATED', 'RESOLVED', 'REOPENED', 'CLOSED'], 'Status')}
          {sel('sensitivity', ['NORMAL', 'CONFIDENTIAL', 'HIGH'], 'Sensitivity')}
          {sel('scope', ['INDIVIDUAL', 'CLASS', 'BATCH', 'DEPARTMENT', 'CAMPUS'], 'Scope')}
          {sel('conf', [['high', '≥ 85%'], ['medium', '60–84%'], ['low', '< 60%']], 'AI confidence')}
          {sel('sla', [['WITHIN', 'Within SLA'], ['APPROACHING', 'Approaching'], ['BREACHED', 'Breached']], 'SLA')}
          {user.role === 'DEPARTMENT_STAFF' && (
            <label className="flex items-center gap-2 text-sm font-semibold px-2"><input type="checkbox" checked={f.mine} onChange={(e) => setF({ ...f, mine: e.target.checked })} />Assigned to me</label>
          )}
        </div>
        <RequestTable rows={rows} />
      </Section>
      <Analytics a={d?.analytics} />
    </div>
  )
}
