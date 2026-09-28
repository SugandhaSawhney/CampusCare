import { useEffect, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { api, ago, fmt } from '../api'
import { useAuth } from '../auth'
import { Badge, Confidence, ErrorNote, RouteTrace, Section, SlaBadge, Stat, pretty } from '../components/ui'

const HINTS = ['', 'Fees or scholarship', 'Classes, exams or registration', 'Portal, Wi-Fi or accounts', 'Hostel', 'Health',
  'Wellbeing or someone to talk to', 'Placements', 'Accessibility', 'Safety']
const HINT_MAP = { 'Fees or scholarship': 'Finance / Scholarship', 'Classes, exams or registration': 'Academics', 'Portal, Wi-Fi or accounts': 'IT Services',
  Hostel: 'Hostel', Health: 'Medical', 'Wellbeing or someone to talk to': 'Mental Health / Counselling', Placements: 'Placement',
  Accessibility: 'Disability Support', Safety: 'Campus Safety' }

function RequestList({ items }) {
  if (!items.length) return <div className="text-sm text-ink-mute">Nothing here yet.</div>
  return (
    <ul className="divide-y divide-paper-line">
      {items.map((r) => (
        <li key={r.id}>
          <Link to={`/student/requests/${r.id}`} className="flex flex-wrap items-center gap-3 py-3 hover:bg-paper -mx-2 px-2 rounded">
            <span className="text-xs font-mono text-ink-mute w-24">{r.request_number}</span>
            <span className="font-semibold flex-1 min-w-[12rem]">{r.title}</span>
            <span className="text-sm text-ink-soft">{r.human_review ? 'Being verified' : r.primary_department || '—'}</span>
            <Badge v={r.status} />
            <span className="text-xs text-ink-mute w-20 text-right">{ago(r.updated_at)}</span>
          </Link>
        </li>
      ))}
    </ul>
  )
}

export function StudentDashboard() {
  const { user } = useAuth()
  const [items, setItems] = useState([])
  useEffect(() => { api('/requests/my').then(setItems) }, [])
  const active = items.filter((r) => !['RESOLVED', 'CLOSED'].includes(r.status))
  const resolved = items.filter((r) => ['RESOLVED', 'CLOSED'].includes(r.status))
  return (
    <div className="space-y-6">
      <div className="card p-6 flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-extrabold">Hi {user.full_name.split(' ')[0]}, what do you need help with?</h1>
          <p className="text-ink-soft mt-1">You don't need to know which office handles it. Tell us in your own words and we'll route it.</p>
        </div>
        <Link to="/student/new-request" className="btn-primary text-base px-5 py-2.5">Get support</Link>
      </div>
      <div className="grid grid-cols-3 gap-3 max-w-xl">
        <Stat label="All requests" value={items.length} />
        <Stat label="Active" value={active.length} />
        <Stat label="Resolved" value={resolved.length} />
      </div>
      <Section title="Active requests"><RequestList items={active} /></Section>
      <Section title="Resolved requests"><RequestList items={resolved} /></Section>
    </div>
  )
}

export function MyRequests() {
  const [items, setItems] = useState([])
  useEffect(() => { api('/requests/my').then(setItems) }, [])
  return <Section title="My requests"><RequestList items={items} /></Section>
}

function TriageResult({ r }) {
  if (r.is_crisis) return (
    <div className="rounded-lg border-2 border-breach bg-breach-tint p-5">
      <h2 className="text-lg font-extrabold text-breach">You're not alone. Help is on the way.</h2>
      <p className="mt-2">{r.summary}</p>
      <p className="mt-2 text-sm">Request ID: <b className="font-mono">{r.request_number}</b></p>
    </div>
  )
  return (
    <div className="card p-5 border-route">
      <div className="flex items-center gap-2 text-route font-bold"><span className="h-2 w-2 rounded-full bg-route" />AI triage complete</div>
      {r.human_review ? (
        <p className="mt-3 text-lg font-semibold">Your request has been sent to a support specialist for verification.</p>
      ) : (
        <div className="mt-4">
          <RouteTrace steps={[
            { label: 'You', value: 'Request sent', sub: r.request_number },
            { label: 'Category', value: r.category, sub: r.subcategory },
            { label: 'Primary department', value: r.primary_department, state: r.privacy_mode !== 'NORMAL' ? 'restricted' : 'active' },
            ...(r.supporting_departments.length ? [{ label: 'Supporting', value: r.supporting_departments.join(', ') }] : []),
          ]} />
        </div>
      )}
      <div className="mt-4 grid sm:grid-cols-3 gap-3 text-sm">
        <div><div className="text-ink-mute font-medium">Priority</div><Badge v={r.priority} /></div>
        <div><div className="text-ink-mute font-medium">AI confidence</div><Confidence value={r.ai_confidence} /></div>
        <div><div className="text-ink-mute font-medium">Target response</div><SlaBadge sla={r.sla} /></div>
      </div>
      <p className="mt-4 text-sm text-ink-soft">{r.summary}</p>
      {r.anonymous && <p className="mt-2 text-sm text-restricted font-semibold">Anonymous: staff handling this see your request ID only, not your identity.</p>}
    </div>
  )
}

export function NewRequest() {
  const nav = useNavigate()
  const [f, setF] = useState({ title: '', description: '', hint: '', privacy_mode: 'NORMAL' })
  const [err, setErr] = useState('')
  const [busy, setBusy] = useState(false)
  const [result, setResult] = useState(null)
  const submit = async (e) => {
    e.preventDefault(); setErr(''); setBusy(true)
    try {
      setResult(await api('/requests', { method: 'POST', body: { title: f.title, description: f.description, privacy_mode: f.privacy_mode, category_hint: HINT_MAP[f.hint] || null } }))
    } catch (x) { setErr(x.message) } finally { setBusy(false) }
  }
  if (result) return (
    <div className="max-w-3xl space-y-4">
      <TriageResult r={result} />
      <div className="flex gap-2">
        <button className="btn-primary" onClick={() => nav(`/student/requests/${result.id}`)}>Track this request</button>
        <button className="btn-ghost" onClick={() => { setResult(null); setF({ title: '', description: '', hint: '', privacy_mode: 'NORMAL' }) }}>Submit another</button>
      </div>
    </div>
  )
  return (
    <form onSubmit={submit} className="max-w-3xl card p-6 space-y-5">
      <div>
        <h1 className="text-2xl font-extrabold">Get support</h1>
        <p className="text-ink-soft mt-1">You don't choose a department. CampusCare reads your request and routes it to the right team.</p>
      </div>
      <ErrorNote error={err} />
      <div><label className="label" htmlFor="t">Short title</label><input id="t" className="input" value={f.title} onChange={(e) => setF({ ...f, title: e.target.value })} required minLength={4} placeholder="e.g. Fee payment keeps failing" /></div>
      <div>
        <label className="label" htmlFor="d">What's happening?</label>
        <textarea id="d" className="input min-h-[140px]" value={f.description} onChange={(e) => setF({ ...f, description: e.target.value })} required minLength={10}
          placeholder="Include any deadline, and whether others (your class or batch) have the same problem." />
      </div>
      <div>
        <label className="label" htmlFor="h">Topic (optional)</label>
        <select id="h" className="input" value={f.hint} onChange={(e) => setF({ ...f, hint: e.target.value })}>
          {HINTS.map((h) => <option key={h} value={h}>{h || "Not sure, that's fine"}</option>)}
        </select>
        <p className="text-xs text-ink-mute mt-1">Only a hint. The routing engine decides the department.</p>
      </div>
      <fieldset>
        <legend className="label">Privacy</legend>
        <div className="grid sm:grid-cols-3 gap-2">
          {[['NORMAL', 'Normal', 'Handled by the relevant team as usual.'], ['CONFIDENTIAL', 'Confidential', 'Never grouped with other cases; restricted to need-to-know staff.'],
            ['ANONYMOUS', 'Anonymous', 'Staff see a request ID, not your name. You track it here.']].map(([v, l, d]) => (
            <label key={v} className={`cursor-pointer rounded-md border p-3 ${f.privacy_mode === v ? (v === 'NORMAL' ? 'border-route bg-route-tint' : 'border-restricted bg-restricted-tint') : 'border-paper-line'}`}>
              <input type="radio" className="sr-only" name="privacy" value={v} checked={f.privacy_mode === v} onChange={() => setF({ ...f, privacy_mode: v })} />
              <div className="font-bold text-sm">{l}</div><div className="text-xs text-ink-soft mt-0.5">{d}</div>
            </label>
          ))}
        </div>
      </fieldset>
      <button className="btn-primary" disabled={busy}>{busy ? 'Running AI triage…' : 'Submit request'}</button>
    </form>
  )
}

export function StudentRequestDetail() {
  const { id } = useParams()
  const [r, setR] = useState(null)
  const [msg, setMsg] = useState('')
  const [err, setErr] = useState('')
  const load = () => api(`/requests/${id}`).then(setR).catch((e) => setErr(e.message))
  useEffect(() => { load() }, [id])
  const act = async (path, body) => { setErr(''); try { setR(await api(`/requests/${id}/${path}`, { method: 'POST', body })); setMsg('') } catch (x) { setErr(x.message) } }
  if (!r) return err ? <ErrorNote error={err} /> : <div className="text-ink-mute">Loading…</div>
  return (
    <div className="grid lg:grid-cols-[1fr_22rem] gap-6">
      <div className="space-y-5">
        <div className="card p-5">
          <div className="text-xs font-mono text-ink-mute">{r.request_number}</div>
          <h1 className="text-2xl font-extrabold mt-1">{r.title}</h1>
          <p className="mt-3 whitespace-pre-wrap text-ink-soft">{r.description}</p>
          {r.is_crisis && <div className="mt-4 rounded-md bg-breach-tint text-breach p-3 font-semibold">{r.summary}</div>}
        </div>
        <Section title="Progress">
          <ol className="relative border-l-2 border-paper-line ml-2 space-y-4">
            {r.timeline.map((s) => (
              <li key={s.step} className="pl-5 relative">
                <span className={`absolute -left-[9px] top-1 h-4 w-4 rounded-full border-2 ${s.done ? 'bg-route border-route' : s.current ? 'bg-signal border-signal' : 'bg-white border-paper-line'}`} />
                <div className={`font-semibold ${s.done ? '' : 'text-ink-mute'}`}>{s.step}</div>
                {s.at && <div className="text-xs text-ink-mute">{fmt(s.at)}</div>}
              </li>
            ))}
          </ol>
        </Section>
        <Section title="Messages">
          <ErrorNote error={err} />
          <div className="space-y-3">
            {r.messages.length === 0 && <div className="text-sm text-ink-mute">No messages yet.</div>}
            {r.messages.map((m) => (
              <div key={m.id} className={`rounded-md p-3 text-sm ${m.from_staff ? 'bg-route-tint' : 'bg-paper'}`}>
                <div className="text-xs font-semibold text-ink-mute">{m.author}, {ago(m.created_at)}</div>
                <div className="mt-1 whitespace-pre-wrap">{m.body}</div>
              </div>
            ))}
          </div>
          {!['CLOSED'].includes(r.status) && (
            <div className="mt-4 flex gap-2">
              <input className="input" value={msg} onChange={(e) => setMsg(e.target.value)} placeholder="Add a follow-up" />
              <button className="btn-primary" disabled={!msg.trim()} onClick={() => act('message', { body: msg })}>Send</button>
            </div>
          )}
        </Section>
      </div>
      <aside className="space-y-4">
        <Section title="Status">
          <div className="space-y-3 text-sm">
            <div><Badge v={r.status} /></div>
            <div><div className="text-ink-mute">Support area</div><div className="font-semibold">{r.human_review ? 'Being verified by a specialist' : r.primary_department}</div>
              {r.supporting_departments?.length > 0 && <div className="text-xs text-ink-soft">with {r.supporting_departments.join(', ')}</div>}</div>
            {r.assigned_to && <div><div className="text-ink-mute">Handled by</div><div className="font-semibold">{r.assigned_to}</div></div>}
            <div><div className="text-ink-mute">Priority</div><Badge v={r.priority} /></div>
            <div><div className="text-ink-mute">Target response</div><SlaBadge sla={r.sla} /></div>
            <div><div className="text-ink-mute">Privacy</div>{pretty(r.privacy_mode)}</div>
            <div><div className="text-ink-mute">Last update</div>{fmt(r.updated_at)}</div>
          </div>
        </Section>
        {r.status === 'RESOLVED' && (
          <Section title="Was this resolved?">
            {r.resolution_note && <p className="text-sm mb-3">{r.resolution_note}</p>}
            <div className="flex gap-2">
              <button className="btn-primary" onClick={() => act('confirm')}>Yes, close it</button>
              <button className="btn-ghost" onClick={() => { const why = prompt('What is still not working?'); if (why) act('reopen', { body: why }) }}>No, reopen</button>
            </div>
          </Section>
        )}
      </aside>
    </div>
  )
}
