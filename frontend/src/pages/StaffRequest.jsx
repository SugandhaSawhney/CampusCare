import { useEffect, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { api, fmt, ago } from '../api'
import { useAuth } from '../auth'
import { Badge, Confidence, ErrorNote, Field, RouteTrace, Section, SlaBadge, pretty } from '../components/ui'

function Candidates({ rows, onPick }) {
  if (!rows?.length) return <div className="text-sm text-ink-mute">No staff in this department.</div>
  return (
    <div className="overflow-x-auto">
      <table className="min-w-full text-sm">
        <thead><tr>{['Staff', 'Skill', 'Active', 'Available', 'Score', ''].map((h) => <th key={h} className="th">{h}</th>)}</tr></thead>
        <tbody className="divide-y divide-paper-line">
          {rows.map((c) => (
            <tr key={c.user_id} className={c.eligible ? '' : 'opacity-50'}>
              <td className="td font-semibold">{c.name}</td>
              <td className="td">{c.skill_match ? '✓' : '—'}</td>
              <td className="td tabular-nums">{c.active_cases} / {c.max}</td>
              <td className="td">{c.available ? 'Yes' : 'No'}</td>
              <td className="td tabular-nums font-bold" title={c.parts ? Object.entries(c.parts).map(([k, v]) => `${k}: ${v}`).join(', ') : ''}>{c.score}</td>
              <td className="td">{onPick && c.eligible && <button className="btn-ghost !py-1 !text-xs" onClick={() => onPick(c.user_id)}>Assign</button>}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function OverrideForm({ r, onDone }) {
  const [tax, setTax] = useState(null)
  const ai = r.ai_analysis || {}
  const [f, setF] = useState({ primary: '', secondary: [], subcategory: '', priority: r.priority || 'MEDIUM', sensitivity: r.sensitivity || 'NORMAL', scope: r.scope || 'INDIVIDUAL', staff: '', reason: '' })
  const [opts, setOpts] = useState([])
  const [err, setErr] = useState('')
  useEffect(() => {
    api('/triage/taxonomy').then((t) => {
      setTax(t)
      const sug = t.departments.find((d) => d.name === ai.primary_department)
      if (sug) setF((x) => ({ ...x, primary: String(sug.id), subcategory: ai.subcategory || '', secondary: t.departments.filter((d) => (ai.secondary_departments || []).includes(d.name)).map((d) => d.id) }))
    })
  }, [])
  useEffect(() => { if (f.primary) api(`/routing/${r.id}/staff-options?department_id=${f.primary}`).then((o) => setOpts(o.candidates)); else setOpts([]) }, [f.primary])
  if (!tax) return null
  const dept = tax.departments.find((d) => String(d.id) === f.primary)
  const subs = dept ? tax.subcategories[dept.name] || [] : []
  const submit = async () => {
    setErr('')
    try {
      await api(`/triage/${r.id}/override`, { method: 'POST', body: {
        primary_department_id: Number(f.primary), secondary_department_ids: f.secondary.filter((x) => String(x) !== f.primary),
        category: dept?.name, subcategory: f.subcategory || null, priority: f.priority, sensitivity_level: f.sensitivity, scope: f.scope,
        assigned_staff_id: f.staff ? Number(f.staff) : null, reason: f.reason } })
      onDone()
    } catch (e) { setErr(e.message) }
  }
  const sel = (k, list) => <select className="input" value={f[k]} onChange={(e) => setF({ ...f, [k]: e.target.value })}>{list.map((o) => <option key={o} value={o}>{pretty(o)}</option>)}</select>
  return (
    <Section title="Human triage decision" className="border-signal">
      <p className="text-sm text-ink-soft mb-3">The AI suggestion is pre-filled. Confirm or correct it. Every change is written to the audit log with your reason.</p>
      <div className="grid sm:grid-cols-2 gap-3">
        <div><label className="label">Primary department (owner)</label>
          <select className="input" value={f.primary} onChange={(e) => setF({ ...f, primary: e.target.value, subcategory: '', staff: '' })}>
            <option value="">Select…</option>{tax.departments.map((d) => <option key={d.id} value={d.id}>{d.name}</option>)}
          </select></div>
        <div><label className="label">Subcategory / required skill</label>
          <select className="input" value={f.subcategory} onChange={(e) => setF({ ...f, subcategory: e.target.value })}>
            <option value="">—</option>{subs.map((s) => <option key={s}>{s}</option>)}
          </select></div>
        <div><label className="label">Priority</label>{sel('priority', ['LOW', 'MEDIUM', 'HIGH', 'CRITICAL'])}</div>
        <div><label className="label">Sensitivity</label>{sel('sensitivity', ['NORMAL', 'CONFIDENTIAL', 'HIGH'])}</div>
        <div><label className="label">Scope</label>{sel('scope', ['INDIVIDUAL', 'CLASS', 'BATCH', 'DEPARTMENT', 'CAMPUS'])}</div>
        <div><label className="label">Assign to (blank = workload-aware auto pick)</label>
          <select className="input" value={f.staff} onChange={(e) => setF({ ...f, staff: e.target.value })}>
            <option value="">Auto-assign</option>{opts.filter((o) => o.eligible).map((o) => <option key={o.user_id} value={o.user_id}>{o.name} ({o.active_cases} active{o.skill_match ? ', skill ✓' : ''})</option>)}
          </select></div>
      </div>
      <div className="mt-3"><label className="label">Supporting departments</label>
        <div className="flex flex-wrap gap-2">
          {tax.departments.filter((d) => String(d.id) !== f.primary).map((d) => (
            <label key={d.id} className="flex items-center gap-1.5 text-sm border border-paper-line rounded px-2 py-1">
              <input type="checkbox" checked={f.secondary.includes(d.id)} onChange={(e) => setF({ ...f, secondary: e.target.checked ? [...f.secondary, d.id] : f.secondary.filter((x) => x !== d.id) })} />{d.name}
            </label>
          ))}
        </div></div>
      <div className="mt-3"><label className="label">Reason for decision (audit-logged)</label>
        <input className="input" value={f.reason} onChange={(e) => setF({ ...f, reason: e.target.value })} placeholder="e.g. Hostel Wi-Fi outage, not an academic issue" /></div>
      <div className="mt-3 flex items-center gap-3"><button className="btn-primary" disabled={!f.primary || f.reason.length < 3} onClick={submit}>Confirm routing & assign</button><ErrorNote error={err} /></div>
    </Section>
  )
}

export default function StaffRequest() {
  const { id } = useParams()
  const { user } = useAuth()
  const nav = useNavigate()
  const [r, setR] = useState(null)
  const [err, setErr] = useState('')
  const [audit, setAudit] = useState([])
  const [depts, setDepts] = useState([])
  const [cands, setCands] = useState(null)
  const [note, setNote] = useState('')
  const [msg, setMsg] = useState('')
  const [act, setAct] = useState({ status: '', statusNote: '', priority: '', prioReason: '', escReason: '', rDept: '', rReason: '' })

  const load = () => {
    api(`/requests/${id}`).then(setR).catch((e) => setErr(e.message))
    api(`/requests/${id}/audit`).then(setAudit).catch(() => {})
  }
  useEffect(() => { load(); api('/departments').then(setDepts) }, [id])

  const run = async (fn) => { setErr(''); try { const out = await fn(); if (out && out.moved) { nav(-1); return } load() } catch (e) { setErr(e.message) } }
  if (err && !r) return <ErrorNote error={err} />
  if (!r) return <div className="text-ink-mute">Loading…</div>

  const role = user.role
  const review = r.status === 'AWAITING_HUMAN_REVIEW'
  const open = !['RESOLVED', 'CLOSED'].includes(r.status)
  const restricted = r.sensitivity === 'HIGH'
  const ar = r.assignment_reason
  const steps = [
    { label: 'Student', value: r.anonymous ? 'Anonymous' : (r.student?.batch || 'Student'), sub: pretty(r.privacy_mode) },
    { label: `AI triage (${r.ai_engine === 'llm' ? 'LLM' : 'rules'})`, value: `${Math.round((r.ai_confidence || 0) * 100)}% confident`, sub: r.subcategory, state: r.ai_confidence >= 0.85 ? 'active' : 'warn' },
    ...(review ? [{ label: 'Human triage', value: 'Review required', sub: r.human_review_reason, state: 'warn' }] : []),
    ...(r.impact ? [{ label: 'Cluster', value: `${r.impact.affected_count}${r.impact.population ? ` / ${r.impact.population}` : ''} affected`, sub: r.impact.label }] : restricted ? [{ label: 'Clustering', value: 'Bypassed', sub: 'Sensitive case', state: 'restricted' }] : []),
    { label: 'Owner', value: r.primary_department?.name || (r.ai_analysis?.primary_department ? `Suggested: ${r.ai_analysis.primary_department}` : 'Unrouted'), sub: r.supporting_departments.length ? `+ ${r.supporting_departments.map((d) => d.name).join(', ')}` : null, state: restricted ? 'restricted' : review ? 'pending' : 'active' },
    { label: 'Assigned', value: r.assigned_staff?.name || 'Pending', sub: r.escalation_level > 1 ? `Escalated: ${r.escalation_label}` : null, state: r.assigned_staff ? (r.escalation_level > 1 ? 'warn' : 'active') : 'pending' },
  ]

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <button onClick={() => nav(-1)} className="text-sm text-route font-semibold">← Back</button>
          <div className="font-mono text-xs text-ink-mute mt-2">{r.request_number}</div>
          <h1 className="text-2xl font-extrabold">{r.title}</h1>
          <div className="flex flex-wrap gap-2 mt-2">
            <Badge v={r.status} /><Badge v={r.priority} /><Badge v={r.sensitivity} kind="sens" /><Badge v={r.scope}>{r.scope}</Badge>
            {r.anonymous && <Badge v="CONFIDENTIAL">Identity protected</Badge>}
            {r.routing_mismatch && <Badge v="APPROACHING">Potential routing rule mismatch detected</Badge>}
          </div>
        </div>
        {['TRIAGE_AGENT', 'ADMIN'].includes(role) && open && !review && (
          <button className="btn-ghost" title="Demo mode only" onClick={() => run(() => api(`/demo/simulate-breach/${r.id}`, { method: 'POST' }))}>Demo: simulate SLA breach</button>
        )}
      </div>
      <ErrorNote error={err} />

      <Section title="Route trace"><RouteTrace steps={steps} /></Section>

      {review && ['TRIAGE_AGENT', 'ADMIN'].includes(role) && <OverrideForm r={r} onDone={load} />}

      <div className="grid lg:grid-cols-5 gap-5">
        <div className="lg:col-span-2 space-y-5">
          <Section title="Student request">
            <Field label="From">{r.student_label}{r.student?.email && <div className="text-xs text-ink-mute">{r.student.email}</div>}</Field>
            <Field label="Created">{fmt(r.created_at)}</Field>
            <Field label="Last update">{ago(r.updated_at)}</Field>
            <p className="mt-3 text-sm whitespace-pre-wrap leading-relaxed">{r.description}</p>
            {r.resolution_note && <div className="mt-3 text-sm bg-route-tint rounded p-2"><b>Resolution:</b> {r.resolution_note}</div>}
            {r.reopen_requested && <div className="mt-2 text-sm text-signal font-semibold">Student requested reopening.</div>}
          </Section>

          <Section title="Conversation with student">
            <div className="space-y-2 max-h-72 overflow-auto">
              {r.messages.length === 0 && <div className="text-sm text-ink-mute">No messages yet.</div>}
              {r.messages.map((m) => (
                <div key={m.id} className={`rounded p-2 text-sm ${m.from_staff ? 'bg-route-tint ml-6' : 'bg-paper mr-6'}`}>
                  <div className="text-[11px] font-semibold text-ink-mute">{m.author} · {ago(m.created_at)}</div>{m.body}
                </div>
              ))}
            </div>
            {open && (
              <div className="mt-3 flex gap-2">
                <input className="input" value={msg} onChange={(e) => setMsg(e.target.value)} placeholder="Reply to student" />
                <button className="btn-ghost" disabled={!msg} onClick={() => run(async () => { await api(`/requests/${r.id}/message`, { method: 'POST', body: { body: msg } }); setMsg('') })}>Send</button>
                <button className="btn-ghost whitespace-nowrap" disabled={!msg} title="Sets status to Waiting for student" onClick={() => run(async () => { await api(`/requests/${r.id}/message`, { method: 'POST', body: { body: msg, request_info: true } }); setMsg('') })}>Ask info</button>
              </div>
            )}
          </Section>

          <Section title="Internal notes" right={<span className="text-[11px] text-restricted font-semibold">Staff only, never shown to student</span>}>
            {r.notes.length === 0 && <div className="text-sm text-ink-mute">No notes.</div>}
            {r.notes.map((n) => <div key={n.id} className="text-sm border-l-2 border-restricted pl-2 mb-2"><div className="text-[11px] text-ink-mute">{n.author} · {ago(n.created_at)}</div>{n.body}</div>)}
            <div className="mt-2 flex gap-2">
              <input className="input" value={note} onChange={(e) => setNote(e.target.value)} placeholder="Add internal note" />
              <button className="btn-ghost" disabled={!note} onClick={() => run(async () => { await api(`/requests/${r.id}/notes`, { method: 'POST', body: { body: note } }); setNote('') })}>Add</button>
            </div>
          </Section>
        </div>

        <div className="lg:col-span-3 space-y-5">
          <Section title="AI triage" right={<span className="text-[11px] text-ink-mute">Decision support, not final authority</span>}>
            <div className="flex items-center gap-4 mb-3"><Confidence value={r.ai_confidence} big />
              <span className="text-sm font-semibold">{r.ai_confidence >= 0.85 ? 'High: auto-routing allowed' : r.ai_confidence >= 0.6 ? 'Medium: suggestion, human verifies' : 'Low: human triage required'}</span></div>
            <Field label="Category">{r.category}</Field>
            <Field label="Subcategory">{r.subcategory}</Field>
            <Field label="Required skill">{r.required_skill}</Field>
            <Field label="Sensitivity"><Badge v={r.sensitivity} kind="sens" /></Field>
            <Field label="Scope">{r.scope}{r.batch_label && ` · ${r.batch_label}`}</Field>
            {r.deadline_hours != null && <Field label="Deadline">~{r.deadline_hours}h detected in text</Field>}
            <Field label="Routing reason"><span className="whitespace-pre-wrap">{r.routing_reason}</span></Field>
            {r.priority_reason && <Field label="Priority reason">{r.priority_reason}</Field>}
            {r.human_review_reason && <Field label="Human review"><span className="text-signal font-semibold">{r.human_review_reason}</span></Field>}
            {r.ai_analysis?.matched_signals?.length > 0 && <Field label="Signals"><span className="text-xs text-ink-mute">{r.ai_analysis.matched_signals.join(', ')}</span></Field>}
          </Section>

          <Section title="Routing & assignment">
            <div className="grid sm:grid-cols-2 gap-4 mb-3">
              <div><div className="text-[11px] font-bold text-ink-mute tracking-wide">PRIMARY OWNER</div><div className="text-lg font-extrabold">{r.primary_department?.name || '—'}</div></div>
              <div><div className="text-[11px] font-bold text-ink-mute tracking-wide">SUPPORTING</div><div className="font-semibold">{r.supporting_departments.map((d) => d.name).join(', ') || '—'}</div></div>
            </div>
            <Field label="Assigned staff">{r.assigned_staff?.name}</Field>
            {ar && (
              <div className="mt-2 rounded bg-paper p-3 text-sm">
                <div className="font-semibold mb-1">Assigned because:</div>
                <ul className="list-disc ml-5 space-y-0.5">{ar.reasons?.map((x, i) => <li key={i}>{x}</li>)}</ul>
                {ar.weights && <div className="text-[11px] text-ink-mute mt-1">Deterministic score (not ML): skill {ar.weights.skill} + department {ar.weights.department} + availability {ar.weights.availability} + workload {ar.weights.workload}</div>}
              </div>
            )}
            {r.routing_history?.length > 1 && <Field label="Routing path">{r.routing_history.join(' → ')} <span className="text-xs text-ink-mute">({r.reassignment_count} reassignments)</span></Field>}
            {r.primary_department && !restricted && (
              <div className="mt-3">
                <button className="btn-ghost !text-xs" onClick={() => cands ? setCands(null) : api(`/routing/${r.id}`, { method: 'POST' }).then((x) => setCands(x.candidates))}>{cands ? 'Hide' : 'Show'} candidate scoring</button>
                {cands && <div className="mt-2"><Candidates rows={cands} onPick={(role === 'ADMIN' || role === 'TRIAGE_AGENT' || role === 'DEAN' || user.hierarchy_level >= 2) && open ? (sid) => run(() => api(`/routing/${r.id}/assign`, { method: 'POST', body: { staff_id: sid, reason: 'Manual assignment from candidate list' } })) : null} /></div>}
              </div>
            )}
          </Section>

          <div className="grid sm:grid-cols-2 gap-5">
            <Section title="Impact">
              {r.impact ? (
                <>
                  <Link to={`/staff/clusters/${r.impact.cluster_id}`} className="font-bold text-route">{r.impact.label}</Link>
                  <div className="text-2xl font-extrabold mt-1 tabular-nums">{r.impact.affected_count}{r.impact.population ? ` / ${r.impact.population}` : ''}</div>
                  <div className="text-sm text-ink-soft">students affected{r.impact.affected_pct != null ? ` · ${r.impact.affected_pct}% impact` : ''}</div>
                  <div className="text-xs text-ink-mute mt-1">{r.impact.request_count} separate requests ({r.impact.open_count} open). Cases are linked, never merged.</div>
                </>
              ) : restricted ? <div className="text-sm text-restricted">Sensitive case: excluded from clustering and cluster analytics.</div>
                : <div className="text-sm text-ink-mute">No similar recent cases. Affected: {r.affected_count}</div>}
            </Section>
            <Section title="SLA & escalation">
              <Field label="Due">{fmt(r.sla?.due_at)}</Field>
              <Field label="Status"><SlaBadge sla={r.sla} /></Field>
              <Field label="Level">L{r.escalation_level || 1}: {r.escalation_label}</Field>
              {open && <Field label="Next">{r.next_authority || 'Top of hierarchy'}</Field>}
            </Section>
          </div>

          {r.escalations.length > 0 && (
            <Section title="Escalation history">
              <ul className="text-sm space-y-2">{r.escalations.map((e) => (
                <li key={e.id} className="border-l-2 border-breach pl-2"><b>L{e.from_level} → L{e.to_level}</b> {e.target && `to ${e.target}`} · {pretty(e.trigger)} · {ago(e.at)}<div className="text-ink-soft">{e.reason}</div>{e.decision_note && <div className="text-route-dark">Decision: {e.decision_note}</div>}</li>
              ))}</ul>
            </Section>
          )}

          {!review && open && (
            <Section title="Actions">
              <div className="grid sm:grid-cols-2 gap-4">
                <div>
                  <label className="label">Change status</label>
                  <div className="flex gap-2">
                    <select className="input" value={act.status} onChange={(e) => setAct({ ...act, status: e.target.value })}>
                      <option value="">Select…</option>{['IN_PROGRESS', 'WAITING_FOR_STUDENT', 'RESOLVED'].map((s) => <option key={s} value={s}>{pretty(s)}</option>)}
                    </select>
                    <button className="btn-primary" disabled={!act.status} onClick={() => run(() => api(`/requests/${r.id}/status`, { method: 'POST', body: { status: act.status, note: act.statusNote || null } }))}>Save</button>
                  </div>
                  {act.status === 'RESOLVED' && <input className="input mt-2" placeholder="Resolution note (shown to student)" value={act.statusNote} onChange={(e) => setAct({ ...act, statusNote: e.target.value })} />}
                </div>
                <div>
                  <label className="label">Change priority</label>
                  <div className="flex gap-2">
                    <select className="input" value={act.priority} onChange={(e) => setAct({ ...act, priority: e.target.value })}>
                      <option value="">Select…</option>{['LOW', 'MEDIUM', 'HIGH', 'CRITICAL'].map((s) => <option key={s}>{s}</option>)}
                    </select>
                    <button className="btn-ghost" disabled={!act.priority || act.prioReason.length < 3} onClick={() => run(() => api(`/requests/${r.id}/priority`, { method: 'POST', body: { priority: act.priority, reason: act.prioReason } }))}>Save</button>
                  </div>
                  {act.priority && <input className="input mt-2" placeholder="Reason (audit-logged)" value={act.prioReason} onChange={(e) => setAct({ ...act, prioReason: e.target.value })} />}
                </div>
                <div>
                  <label className="label">Escalate to {r.next_authority || '—'}</label>
                  <div className="flex gap-2">
                    <input className="input" placeholder="Reason" value={act.escReason} onChange={(e) => setAct({ ...act, escReason: e.target.value })} />
                    <button className="btn-ghost !text-breach" disabled={act.escReason.length < 3 || !r.next_authority} onClick={() => run(() => api(`/requests/${r.id}/escalate`, { method: 'POST', body: { reason: act.escReason } }))}>Escalate</button>
                  </div>
                </div>
                <div>
                  <label className="label">Reassign department (owner)</label>
                  <div className="flex gap-2">
                    <select className="input" value={act.rDept} onChange={(e) => setAct({ ...act, rDept: e.target.value })}>
                      <option value="">Select…</option>{depts.filter((d) => d.id !== r.primary_department?.id).map((d) => <option key={d.id} value={d.id}>{d.name}</option>)}
                    </select>
                    <button className="btn-ghost" disabled={!act.rDept || act.rReason.length < 3} onClick={() => run(() => api(`/routing/${r.id}/reassign`, { method: 'POST', body: { department_id: Number(act.rDept), reason: act.rReason } }))}>Move</button>
                  </div>
                  {act.rDept && <input className="input mt-2" placeholder="Why is this the wrong department?" value={act.rReason} onChange={(e) => setAct({ ...act, rReason: e.target.value })} />}
                </div>
              </div>
            </Section>
          )}

          <Section title="Audit trail">
            <div className="max-h-64 overflow-auto">
              <table className="min-w-full text-xs">
                <tbody className="divide-y divide-paper-line">
                  {audit.map((l) => (
                    <tr key={l.id}><td className="py-1.5 pr-2 text-ink-mute whitespace-nowrap">{fmt(l.at)}</td><td className="py-1.5 pr-2 font-semibold">{l.actor}</td>
                      <td className="py-1.5 pr-2 font-mono">{l.action}</td><td className="py-1.5 text-ink-soft">{[l.old && `${l.old} →`, l.new, l.reason && `(${l.reason})`].filter(Boolean).join(' ')}</td></tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Section>
        </div>
      </div>
    </div>
  )
}
