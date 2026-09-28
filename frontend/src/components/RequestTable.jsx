import { useNavigate } from 'react-router-dom'
import { ago } from '../api'
import { Badge, Confidence } from './ui'

export default function RequestTable({ rows, extra, empty = 'No requests match.' }) {
  const nav = useNavigate()
  if (!rows?.length) return <div className="text-sm text-ink-mute p-4">{empty}</div>
  return (
    <div className="overflow-x-auto">
      <table className="min-w-full">
        <thead className="border-b border-paper-line">
          <tr>
            {['Request', 'Category', 'Priority', 'Sensitivity', 'Scope', 'Affected', 'AI conf.', 'Primary dept.', 'Assigned', 'Status', 'SLA'].map((h) => <th key={h} className="th">{h}</th>)}
            {extra && <th className="th">{extra.header}</th>}
          </tr>
        </thead>
        <tbody className="divide-y divide-paper-line">
          {rows.map((r) => (
            <tr key={r.id} className="hover:bg-paper cursor-pointer" onClick={() => nav(`/staff/requests/${r.id}`)}>
              <td className="td max-w-[16rem]">
                <div className="font-mono text-xs text-ink-mute">{r.request_number}{r.routing_mismatch && <span className="ml-1 text-signal font-sans font-bold" title="Routing mismatch">⟲</span>}</div>
                <div className="font-semibold truncate">{r.title}</div>
                <div className="text-[11px] text-ink-mute">{ago(r.created_at)}</div>
              </td>
              <td className="td"><div className="font-medium">{r.category}</div><div className="text-xs text-ink-mute">{r.subcategory}</div></td>
              <td className="td"><Badge v={r.priority} /></td>
              <td className="td"><Badge v={r.sensitivity} kind="sens" /></td>
              <td className="td text-xs font-semibold">{r.scope}</td>
              <td className="td tabular-nums">{r.affected_count}</td>
              <td className="td"><Confidence value={r.ai_confidence} /></td>
              <td className="td">
                <div className="font-medium">{r.primary_department || <span className="text-signal">{r.suggested_department ? `Suggested: ${r.suggested_department}` : 'Unrouted'}</span>}</div>
                {r.supporting_departments?.length > 0 && <div className="text-[11px] text-ink-mute">+ {r.supporting_departments.join(', ')}</div>}
              </td>
              <td className="td text-sm">{r.assigned_staff || '—'}</td>
              <td className="td"><Badge v={r.status} />{r.escalation_level > 1 && <div className="text-[11px] text-breach font-semibold mt-0.5">Level {r.escalation_level}</div>}</td>
              <td className="td"><Badge v={r.sla_status}>{r.sla_status === 'WITHIN' ? 'Within' : r.sla_status === 'APPROACHING' ? 'At risk' : r.sla_status === 'BREACHED' ? 'Breached' : undefined}</Badge></td>
              {extra && <td className="td" onClick={(e) => e.stopPropagation()}>{extra.cell(r)}</td>}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
