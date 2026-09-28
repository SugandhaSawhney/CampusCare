import { useEffect, useState } from 'react'
import { api } from '../api'
import RequestTable from '../components/RequestTable'
import { Section } from '../components/ui'

export default function TriageQueue() {
  const [rows, setRows] = useState(null)
  useEffect(() => { api('/triage/queue').then(setRows) }, [])
  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-2xl font-extrabold">Human triage queue</h1>
        <p className="text-sm text-ink-soft max-w-3xl">Requests the AI would not route on its own: confidence below 85%, conflicting signals, ambiguous multi-department routing, or no department match. Open a case to confirm or correct the AI suggestion. Restricted mental-health cases never appear here; they go straight to the counselling team.</p>
      </div>
      <Section title={`Waiting for a human decision (${rows?.length ?? '…'})`}>
        <RequestTable rows={rows || []} empty="Queue is clear." extra={{ header: 'Why', cell: (r) => <span className="text-xs text-signal font-semibold">{r.human_review_reason}</span> }} />
      </Section>
    </div>
  )
}
