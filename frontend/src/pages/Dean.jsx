import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../api'
import { useAuth } from '../auth'
import { Section, Stat } from '../components/ui'
import { EscalationTable } from './Escalations'
import RequestTable from '../components/RequestTable'
import { Analytics } from './StaffDashboard'

export default function DeanDashboard() {
  const { user } = useAuth()
  const [d, setD] = useState(null)
  const [esc, setEsc] = useState(null)
  const [clusters, setClusters] = useState([])
  const [rows, setRows] = useState([])
  const load = () => {
    api('/staff/dashboard').then(setD)
    api('/staff/escalations').then(setEsc)
    api('/staff/clusters').then(setClusters)
    api('/staff/requests').then(setRows)
  }
  useEffect(load, [])
  const c = d?.cards || {}
  const mine = esc?.filter((e) => e.is_mine) || []
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-extrabold">Escalation oversight</h1>
        <p className="text-sm text-ink-soft">{user.title || 'Dean'}. You see only cases escalated into your hierarchy, not every request.</p>
      </div>
      <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
        <Stat label="Waiting on your decision" value={mine.length} tone={mine.length ? 'bad' : ''} />
        <Stat label="Escalated cases in scope" value={esc?.length} />
        <Stat label="SLA breached" value={c.sla_breached} tone={c.sla_breached ? 'bad' : ''} />
        <Stat label="High priority open" value={c.high_priority} />
        <Stat label="High-impact clusters" value={clusters.filter((x) => x.priority === 'HIGH' || x.priority === 'CRITICAL').length} to="/staff/clusters" />
      </div>
      <Section title="Escalations requiring your attention"><EscalationTable rows={esc} onChange={load} /></Section>
      {clusters.length > 0 && (
        <Section title="High-impact issue clusters (non-sensitive)">
          <ul className="divide-y divide-paper-line">
            {clusters.slice(0, 6).map((x) => (
              <li key={x.id}><Link to={`/staff/clusters/${x.id}`} className="flex items-center gap-3 py-2 hover:bg-paper -mx-2 px-2 rounded">
                <span className="font-semibold flex-1">{x.label}</span><span className="text-sm text-ink-soft">{x.primary_department}</span>
                <span className="font-bold tabular-nums">{x.affected_count}{x.population ? ` / ${x.population}` : ''}</span>
                {x.affected_pct != null && <span className="text-xs text-ink-mute w-10 text-right">{x.affected_pct}%</span>}
              </Link></li>
            ))}
          </ul>
        </Section>
      )}
      <Section title="Cases in your hierarchy"><RequestTable rows={rows} empty="Nothing escalated to your level." /></Section>
      <Analytics a={d?.analytics} />
    </div>
  )
}
