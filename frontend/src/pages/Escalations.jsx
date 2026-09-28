import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api, ago } from '../api'
import { Badge, ErrorNote, Section, pretty } from '../components/ui'

export function EscalationTable({ rows, onChange }) {
  const [closing, setClosing] = useState(null)
  const [note, setNote] = useState('')
  const [err, setErr] = useState('')
  if (!rows?.length) return <div className="text-sm text-ink-mute">No open escalations in your scope.</div>
  const close = async (id) => {
    setErr('')
    try { await api(`/staff/escalations/${id}/close`, { method: 'POST', body: { decision_note: note } }); setClosing(null); setNote(''); onChange?.() } catch (e) { setErr(e.message) }
  }
  return (
    <div className="overflow-x-auto">
      <ErrorNote error={err} />
      <table className="min-w-full">
        <thead className="border-b border-paper-line"><tr>{['Request', 'Current department', 'Level', 'SLA', 'Reason', 'Escalated', 'Next authority', ''].map((h) => <th key={h} className="th">{h}</th>)}</tr></thead>
        <tbody className="divide-y divide-paper-line">
          {rows.map((e) => (
            <tr key={e.id} className="align-top">
              <td className="td"><Link to={`/staff/requests/${e.request_id}`} className="font-mono text-xs text-route font-bold">{e.request_number}</Link><div className="font-semibold text-sm max-w-[14rem] truncate">{e.title}</div><Badge v={e.priority} /></td>
              <td className="td text-sm">{e.department}</td>
              <td className="td"><div className="font-bold text-breach">Level {e.level}</div><div className="text-xs text-ink-mute">{e.level_label}{e.target ? `: ${e.target}` : ''}</div></td>
              <td className="td"><Badge v={e.sla_status}>{e.sla_status === 'BREACHED' ? 'Breached' : pretty(e.sla_status)}</Badge></td>
              <td className="td text-sm max-w-[16rem]"><div className="text-xs font-semibold text-ink-mute">{pretty(e.trigger)}</div>{e.reason}</td>
              <td className="td text-xs whitespace-nowrap">{ago(e.escalated_at)}</td>
              <td className="td text-xs">{e.next_authority}</td>
              <td className="td">
                {e.is_mine && !e.closed && (closing === e.id ? (
                  <div className="w-56 space-y-1">
                    <textarea className="input !text-xs" rows={2} placeholder="Decision / note" value={note} onChange={(x) => setNote(x.target.value)} />
                    <div className="flex gap-1"><button className="btn-primary !py-1 !text-xs" disabled={note.length < 3} onClick={() => close(e.id)}>Close escalation</button><button className="btn-ghost !py-1 !text-xs" onClick={() => setClosing(null)}>Cancel</button></div>
                  </div>
                ) : <button className="btn-ghost !py-1 !text-xs" onClick={() => setClosing(e.id)}>Decide</button>)}
                {e.closed && <span className="text-xs text-route-dark">Closed: {e.decision_note}</span>}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

export default function Escalations() {
  const [rows, setRows] = useState(null)
  const [closed, setClosed] = useState(false)
  const load = () => api(`/staff/escalations${closed ? '?include_closed=true' : ''}`).then(setRows)
  useEffect(() => { load() }, [closed])
  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-extrabold">Escalations</h1>
          <p className="text-sm text-ink-soft max-w-3xl">L1 assigned staff → L2 department lead → L3 dean → L4 central student administration. Cases climb one level at a time on SLA breach, repeated reassignment or manual escalation; critical safety and medical cases follow the emergency path.</p>
        </div>
        <label className="text-sm font-semibold flex items-center gap-2"><input type="checkbox" checked={closed} onChange={(e) => setClosed(e.target.checked)} />Show closed</label>
      </div>
      <Section title={`Escalated cases (${rows?.length ?? '…'})`}><EscalationTable rows={rows} onChange={load} /></Section>
    </div>
  )
}
