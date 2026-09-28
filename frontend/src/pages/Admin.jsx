import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api, fmt } from '../api'
import { Badge, ErrorNote, Section, pretty } from '../components/ui'

const TABS = ['Users', 'Departments & hierarchy', 'Routing rules', 'SLA rules', 'Routing feedback', 'Audit log']

function Users() {
  const [rows, setRows] = useState([])
  const [depts, setDepts] = useState([])
  const [q, setQ] = useState('')
  const [err, setErr] = useState('')
  const [n, setN] = useState({ username: '', full_name: '', email: '', password: '', role: 'DEPARTMENT_STAFF', department_id: '', skills: '', hierarchy_level: 1 })
  const load = () => api('/admin/users').then(setRows)
  useEffect(() => { load(); api('/departments').then(setDepts) }, [])
  const patch = (id, body) => api(`/admin/users/${id}`, { method: 'PATCH', body }).then(load).catch((e) => setErr(e.message))
  const create = async () => {
    setErr('')
    try {
      await api('/admin/users', { method: 'POST', body: { ...n, department_id: n.department_id ? Number(n.department_id) : null, skills: n.skills.split(',').map((s) => s.trim()).filter(Boolean), hierarchy_level: Number(n.hierarchy_level) } })
      setN({ ...n, username: '', full_name: '', email: '', password: '', skills: '' }); load()
    } catch (e) { setErr(e.message) }
  }
  const shown = rows.filter((u) => !q || `${u.username} ${u.full_name} ${u.role} ${u.department || ''}`.toLowerCase().includes(q.toLowerCase()))
  return (
    <div className="space-y-4">
      <ErrorNote error={err} />
      <Section title="Add user">
        <div className="grid sm:grid-cols-4 gap-2">
          {['username', 'full_name', 'email', 'password'].map((k) => <input key={k} className="input" type={k === 'password' ? 'password' : 'text'} placeholder={pretty(k)} value={n[k]} onChange={(e) => setN({ ...n, [k]: e.target.value })} />)}
          <select className="input" value={n.role} onChange={(e) => setN({ ...n, role: e.target.value })}>{['STUDENT', 'TRIAGE_AGENT', 'DEPARTMENT_STAFF', 'DEAN', 'ADMIN'].map((r) => <option key={r} value={r}>{pretty(r)}</option>)}</select>
          <select className="input" value={n.department_id} onChange={(e) => setN({ ...n, department_id: e.target.value })}><option value="">No department</option>{depts.map((d) => <option key={d.id} value={d.id}>{d.name}</option>)}</select>
          <input className="input" placeholder="Skills (comma separated)" value={n.skills} onChange={(e) => setN({ ...n, skills: e.target.value })} />
          <select className="input" value={n.hierarchy_level} onChange={(e) => setN({ ...n, hierarchy_level: e.target.value })}>{[1, 2, 3, 4].map((l) => <option key={l} value={l}>Level {l}</option>)}</select>
        </div>
        <button className="btn-primary mt-3" onClick={create}>Create user</button>
      </Section>
      <Section title={`Users (${rows.length})`} right={<input className="input !w-56 !py-1" placeholder="Search" value={q} onChange={(e) => setQ(e.target.value)} />}>
        <div className="overflow-x-auto max-h-[32rem]">
          <table className="min-w-full text-sm">
            <thead><tr>{['User', 'Role', 'Department', 'Level', 'Skills', 'Active cases', 'Available', 'Account'].map((h) => <th key={h} className="th">{h}</th>)}</tr></thead>
            <tbody className="divide-y divide-paper-line">
              {shown.map((u) => (
                <tr key={u.id}>
                  <td className="td"><div className="font-semibold">{u.full_name}</div><div className="text-xs text-ink-mute font-mono">{u.username}</div></td>
                  <td className="td"><select className="input !py-1 !text-xs" value={u.role} onChange={(e) => patch(u.id, { role: e.target.value })}>{['STUDENT', 'TRIAGE_AGENT', 'DEPARTMENT_STAFF', 'DEAN', 'ADMIN'].map((r) => <option key={r} value={r}>{pretty(r)}</option>)}</select></td>
                  <td className="td text-xs">{u.department || u.batch || '—'}</td>
                  <td className="td">{u.hierarchy_level ? <select className="input !py-1 !text-xs !w-16" value={u.hierarchy_level} onChange={(e) => patch(u.id, { hierarchy_level: Number(e.target.value) })}>{[1, 2, 3, 4].map((l) => <option key={l}>{l}</option>)}</select> : '—'}</td>
                  <td className="td text-xs max-w-[14rem]">{u.skills?.join(', ') || '—'}</td>
                  <td className="td tabular-nums">{u.active_cases ?? '—'}</td>
                  <td className="td">{u.available != null ? <input type="checkbox" checked={u.available} onChange={(e) => patch(u.id, { available: e.target.checked })} /> : '—'}</td>
                  <td className="td"><button className="text-xs font-semibold text-route" onClick={() => patch(u.id, { is_active: !u.is_active })}>{u.is_active ? 'Active' : 'Disabled'}</button></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Section>
    </div>
  )
}

function Departments() {
  const [rows, setRows] = useState([])
  const [users, setUsers] = useState([])
  const [err, setErr] = useState('')
  const load = () => api('/admin/departments').then(setRows)
  useEffect(() => { load(); api('/admin/users').then(setUsers) }, [])
  const put = (id, body) => api(`/admin/departments/${id}`, { method: 'PUT', body }).then(load).catch((e) => setErr(e.message))
  const deans = users.filter((u) => u.role === 'DEAN')
  return (
    <Section title="Departments & escalation hierarchy">
      <ErrorNote error={err} />
      <p className="text-sm text-ink-soft mb-3">L1 assigned staff → L2 department lead → L3 dean → L4 central student administration (any Level-4 dean account).</p>
      <div className="overflow-x-auto">
        <table className="min-w-full text-sm">
          <thead><tr>{['Department', 'Flags', 'Staff', 'L2 lead', 'L3 dean', 'Capabilities'].map((h) => <th key={h} className="th">{h}</th>)}</tr></thead>
          <tbody className="divide-y divide-paper-line">
            {rows.map((d) => (
              <tr key={d.id}>
                <td className="td font-semibold">{d.name}<div className="text-xs text-ink-mute font-mono">{d.code}</div></td>
                <td className="td space-x-1">{d.is_sensitive && <Badge v="CONFIDENTIAL">Restricted</Badge>}{d.is_emergency && <Badge v="HIGH">Emergency path</Badge>}</td>
                <td className="td tabular-nums">{d.staff_count}</td>
                <td className="td"><select className="input !py-1 !text-xs" value={d.lead_id || ''} onChange={(e) => put(d.id, { lead_id: Number(e.target.value) })}>
                  <option value="">—</option>{users.filter((u) => u.department_id === d.id).map((u) => <option key={u.id} value={u.id}>{u.full_name} (L{u.hierarchy_level})</option>)}</select></td>
                <td className="td"><select className="input !py-1 !text-xs" value={d.dean_id || ''} onChange={(e) => put(d.id, { dean_id: Number(e.target.value) })}>
                  <option value="">—</option>{deans.map((u) => <option key={u.id} value={u.id}>{u.full_name}</option>)}</select></td>
                <td className="td text-xs max-w-[18rem]">{d.capabilities?.join(', ')}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Section>
  )
}

function Rules() {
  const [rows, setRows] = useState([])
  const [tax, setTax] = useState(null)
  const [n, setN] = useState({ keyword: '', department_id: '', subcategory: '', weight: 2 })
  const [err, setErr] = useState('')
  const load = () => api('/admin/routing-rules').then(setRows)
  useEffect(() => { load(); api('/triage/taxonomy').then(setTax) }, [])
  const dept = tax?.departments.find((d) => String(d.id) === n.department_id)
  const add = () => api('/admin/routing-rules', { method: 'POST', body: { ...n, department_id: Number(n.department_id), weight: Number(n.weight) } })
    .then(() => { setN({ ...n, keyword: '' }); load() }).catch((e) => setErr(e.message))
  return (
    <Section title="Custom routing rules">
      <p className="text-sm text-ink-soft mb-3">Keyword rules are added on top of the built-in classifier (and applied as a safety net when the LLM is used). Use them to fix mismatches surfaced in Routing feedback.</p>
      <ErrorNote error={err} />
      <div className="grid sm:grid-cols-5 gap-2 mb-4">
        <input className="input" placeholder="Keyword or phrase" value={n.keyword} onChange={(e) => setN({ ...n, keyword: e.target.value })} />
        <select className="input" value={n.department_id} onChange={(e) => setN({ ...n, department_id: e.target.value, subcategory: '' })}><option value="">Department</option>{tax?.departments.map((d) => <option key={d.id} value={d.id}>{d.name}</option>)}</select>
        <select className="input" value={n.subcategory} onChange={(e) => setN({ ...n, subcategory: e.target.value })}><option value="">Subcategory</option>{(dept ? tax.subcategories[dept.name] : []).map((s) => <option key={s}>{s}</option>)}</select>
        <input className="input" type="number" step="0.5" min="0.5" max="10" value={n.weight} onChange={(e) => setN({ ...n, weight: e.target.value })} />
        <button className="btn-primary" disabled={!n.keyword || !n.department_id || !n.subcategory} onClick={add}>Add rule</button>
      </div>
      {rows.length === 0 ? <div className="text-sm text-ink-mute">No custom rules yet.</div> : (
        <table className="min-w-full text-sm"><thead><tr>{['Keyword', 'Department', 'Subcategory', 'Weight', ''].map((h) => <th key={h} className="th">{h}</th>)}</tr></thead>
          <tbody className="divide-y divide-paper-line">{rows.map((r) => (
            <tr key={r.id}><td className="td font-mono">{r.keyword}</td><td className="td">{r.department}</td><td className="td">{r.subcategory}</td><td className="td">{r.weight}</td>
              <td className="td"><button className="text-xs text-breach font-semibold" onClick={() => api(`/admin/routing-rules/${r.id}`, { method: 'DELETE' }).then(load)}>Delete</button></td></tr>
          ))}</tbody></table>
      )}
    </Section>
  )
}

function SLARules() {
  const [rows, setRows] = useState([])
  const [msg, setMsg] = useState('')
  const load = () => api('/admin/sla-rules').then(setRows)
  useEffect(() => { load() }, [])
  const set = (i, k, v) => setRows(rows.map((r, j) => (j === i ? { ...r, [k]: v } : r)))
  const save = (r) => api(`/admin/sla-rules/${r.priority}`, { method: 'PUT', body: { resolution_hours: Number(r.resolution_hours), escalation_window_hours: Number(r.escalation_window_hours), max_escalation_level: Number(r.max_escalation_level) } })
    .then(() => { setMsg(`${r.priority} saved`); load() }).catch((e) => setMsg(e.message))
  return (
    <Section title="SLA rules" right={<span className="text-xs text-route font-semibold">{msg}</span>}>
      <p className="text-sm text-ink-soft mb-3">Prototype targets, not institutional promises. The first-level window is the resolution target; each further level gets the escalation window before climbing again, up to the maximum level.</p>
      <table className="min-w-full text-sm"><thead><tr>{['Priority', 'Resolution target (h)', 'Escalation window (h)', 'Max level', ''].map((h) => <th key={h} className="th">{h}</th>)}</tr></thead>
        <tbody className="divide-y divide-paper-line">{rows.map((r, i) => (
          <tr key={r.priority}><td className="td"><Badge v={r.priority} /></td>
            <td className="td"><input className="input !w-24 !py-1" type="number" value={r.resolution_hours} onChange={(e) => set(i, 'resolution_hours', e.target.value)} /></td>
            <td className="td"><input className="input !w-24 !py-1" type="number" value={r.escalation_window_hours} onChange={(e) => set(i, 'escalation_window_hours', e.target.value)} /></td>
            <td className="td"><select className="input !w-20 !py-1" value={r.max_escalation_level} onChange={(e) => set(i, 'max_escalation_level', e.target.value)}>{[2, 3, 4].map((l) => <option key={l}>{l}</option>)}</select></td>
            <td className="td"><button className="btn-ghost !py-1 !text-xs" onClick={() => save(r)}>Save</button></td></tr>
        ))}</tbody></table>
    </Section>
  )
}

function Feedback() {
  const [rows, setRows] = useState(null)
  useEffect(() => { api('/admin/routing-feedback').then(setRows) }, [])
  return (
    <Section title="Routing feedback (human corrections of AI routing)">
      <p className="text-sm text-ink-soft mb-3">Stored, not auto-retrained. Repeated patterns here are candidates for a new routing rule.</p>
      {rows?.length === 0 && <div className="text-sm text-ink-mute">No corrections recorded.</div>}
      <table className="min-w-full text-sm"><tbody className="divide-y divide-paper-line">{rows?.map((r, i) => (
        <tr key={i}><td className="td font-mono text-xs">{r.action}</td><td className="td">{r.from}</td><td className="td">→ {r.to}</td><td className="td font-bold tabular-nums">{r.count}×</td></tr>
      ))}</tbody></table>
    </Section>
  )
}

function Audit() {
  const [rows, setRows] = useState([])
  const [q, setQ] = useState('')
  useEffect(() => { const t = setTimeout(() => api(`/admin/audit-logs${q ? `?action=${encodeURIComponent(q)}` : ''}`).then(setRows), 250); return () => clearTimeout(t) }, [q])
  return (
    <Section title="Audit log" right={<input className="input !w-56 !py-1" placeholder="Filter by action (e.g. OVERRIDE)" value={q} onChange={(e) => setQ(e.target.value)} />}>
      <div className="overflow-x-auto max-h-[36rem]">
        <table className="min-w-full text-xs"><thead><tr>{['When', 'Request', 'Actor', 'Action', 'Old', 'New', 'Reason'].map((h) => <th key={h} className="th">{h}</th>)}</tr></thead>
          <tbody className="divide-y divide-paper-line">{rows.map((l) => (
            <tr key={l.id}><td className="td whitespace-nowrap">{fmt(l.at)}</td><td className="td">{l.request_id ? <Link className="text-route font-semibold" to={`/staff/requests/${l.request_id}`}>#{l.request_id}</Link> : '—'}</td>
              <td className="td font-semibold">{l.actor}</td><td className="td font-mono">{l.action}</td><td className="td max-w-[10rem] truncate">{l.old}</td><td className="td max-w-[10rem] truncate">{l.new}</td><td className="td max-w-[20rem]">{l.reason}</td></tr>
          ))}</tbody></table>
      </div>
    </Section>
  )
}

export default function Admin() {
  const [tab, setTab] = useState(TABS[0])
  const View = { Users, 'Departments & hierarchy': Departments, 'Routing rules': Rules, 'SLA rules': SLARules, 'Routing feedback': Feedback, 'Audit log': Audit }[tab]
  return (
    <div className="space-y-5">
      <h1 className="text-2xl font-extrabold">Administration</h1>
      <div className="flex flex-wrap gap-1 border-b border-paper-line">
        {TABS.map((t) => <button key={t} onClick={() => setTab(t)} className={`px-3 py-2 text-sm font-semibold -mb-px border-b-2 ${tab === t ? 'border-route text-ink' : 'border-transparent text-ink-mute hover:text-ink'}`}>{t}</button>)}
      </div>
      <View />
    </div>
  )
}
