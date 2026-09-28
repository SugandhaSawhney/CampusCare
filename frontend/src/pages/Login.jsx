import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { homeFor, useAuth } from '../auth'
import { ErrorNote } from '../components/ui'

// Usernames only. Passwords are never embedded in frontend code (see README for the demo password).
const DEMO = [
  ['student01', 'Student'], ['triage.priya', 'Triage agent'], ['fin.anita', 'Finance staff'], ['fin.lead', 'Finance lead'],
  ['mh.rao', 'Counsellor'], ['dean.academic', 'Dean'], ['admin', 'Admin'],
]

export default function Login({ register }) {
  const { login, register: doRegister } = useAuth()
  const nav = useNavigate()
  const [f, setF] = useState({ username: '', password: '', full_name: '', email: '', program: 'CSE', batch_year: 2027 })
  const [err, setErr] = useState('')
  const [busy, setBusy] = useState(false)
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value })

  const submit = async (e) => {
    e.preventDefault(); setErr(''); setBusy(true)
    try {
      const u = register ? await doRegister({ ...f, batch_year: Number(f.batch_year) }) : await login(f.username, f.password)
      nav(homeFor(u.role))
    } catch (x) { setErr(x.message) } finally { setBusy(false) }
  }

  return (
    <div className="min-h-screen grid lg:grid-cols-[1.1fr_1fr]">
      <div className="bg-ink text-white px-8 lg:px-16 py-12 flex flex-col justify-between">
        <div className="font-extrabold text-lg">CampusCare</div>
        <div className="max-w-xl">
          <h1 className="text-4xl lg:text-5xl font-extrabold leading-[1.08] tracking-tight">One place to ask.<br />The right team answers.</h1>
          <p className="mt-5 text-white/75 text-lg leading-relaxed">
            Describe what's going on in your own words. CampusCare works out which of nine support teams should own it,
            keeps sensitive requests private, spots when many students share the same problem, and escalates anything that stalls.
          </p>
          <div className="mt-10 flex flex-wrap items-center gap-2 text-sm">
            {['Your words', 'AI triage', 'Right department', 'Right person', 'Escalation if stalled'].map((s, i, a) => (
              <span key={s} className="flex items-center gap-2">
                <span className="rounded border border-white/25 px-2.5 py-1">{s}</span>
                {i < a.length - 1 && <svg width="18" height="10" viewBox="0 0 18 10" aria-hidden><path d="M0 5h15M11 1l4 4-4 4" stroke="#5FD4CF" strokeWidth="1.8" fill="none" /></svg>}
              </span>
            ))}
          </div>
        </div>
        <div className="text-xs text-white/50">Hackathon prototype, track 01: Student Triage & Routing</div>
      </div>

      <div className="flex items-center justify-center px-6 py-12">
        <form onSubmit={submit} className="w-full max-w-sm space-y-4">
          <h2 className="text-2xl font-extrabold">{register ? 'Create a student account' : 'Sign in'}</h2>
          <ErrorNote error={err} />
          {register && (<>
            <div><label className="label" htmlFor="fn">Full name</label><input id="fn" className="input" value={f.full_name} onChange={set('full_name')} required /></div>
            <div><label className="label" htmlFor="em">Email</label><input id="em" type="email" className="input" value={f.email} onChange={set('email')} required /></div>
            <div className="grid grid-cols-2 gap-3">
              <div><label className="label" htmlFor="pg">Program</label><input id="pg" className="input" value={f.program} onChange={set('program')} /></div>
              <div><label className="label" htmlFor="by">Batch year</label><input id="by" type="number" className="input" value={f.batch_year} onChange={set('batch_year')} /></div>
            </div>
          </>)}
          <div><label className="label" htmlFor="un">Username</label><input id="un" className="input" value={f.username} onChange={set('username')} autoComplete="username" required /></div>
          <div><label className="label" htmlFor="pw">Password</label><input id="pw" type="password" className="input" value={f.password} onChange={set('password')} autoComplete={register ? 'new-password' : 'current-password'} required minLength={register ? 8 : 1} /></div>
          <button className="btn-primary w-full" disabled={busy}>{busy ? 'Please wait…' : register ? 'Create account' : 'Sign in'}</button>
          <div className="text-sm text-ink-soft">
            {register ? <Link className="text-route font-semibold" to="/login">I already have an account</Link>
              : <>New student? <Link className="text-route font-semibold" to="/register">Create an account</Link></>}
          </div>
          {!register && (
            <div className="pt-4 border-t border-paper-line">
              <div className="text-xs font-semibold text-ink-mute mb-2">Demo accounts (password in README)</div>
              <div className="flex flex-wrap gap-1.5">
                {DEMO.map(([u, l]) => (
                  <button type="button" key={u} className="rounded border border-paper-line bg-white px-2 py-1 text-xs hover:border-route" onClick={() => setF({ ...f, username: u })}>
                    <span className="font-semibold">{l}</span> <span className="text-ink-mute">{u}</span>
                  </button>
                ))}
              </div>
            </div>
          )}
        </form>
      </div>
    </div>
  )
}
