import { Navigate, Route, Routes } from 'react-router-dom'
import { Layout } from './components/ui'
import { homeFor, useAuth } from './auth'
import Login from './pages/Login'
import { StudentDashboard, NewRequest, MyRequests, StudentRequestDetail } from './pages/Student'
import StaffDashboard from './pages/StaffDashboard'
import StaffRequest from './pages/StaffRequest'
import TriageQueue from './pages/TriageQueue'
import { Clusters, ClusterDetail } from './pages/Clusters'
import Escalations from './pages/Escalations'
import DeanDashboard from './pages/Dean'
import Admin from './pages/Admin'

const STAFF = ['TRIAGE_AGENT', 'DEPARTMENT_STAFF', 'DEAN', 'ADMIN']

// UI-level guard. The backend independently enforces every rule; this only avoids showing dead ends.
function Guard({ roles, children }) {
  const { user, ready } = useAuth()
  if (!ready) return <div className="p-10 text-ink-mute">Loading…</div>
  if (!user) return <Navigate to="/login" replace />
  if (roles && !roles.includes(user.role)) return <Navigate to={homeFor(user.role)} replace />
  return <Layout>{children}</Layout>
}

export default function App() {
  const { user, ready } = useAuth()
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route path="/register" element={<Login register />} />
      <Route path="/student/dashboard" element={<Guard roles={['STUDENT']}><StudentDashboard /></Guard>} />
      <Route path="/student/new-request" element={<Guard roles={['STUDENT']}><NewRequest /></Guard>} />
      <Route path="/student/requests" element={<Guard roles={['STUDENT']}><MyRequests /></Guard>} />
      <Route path="/student/requests/:id" element={<Guard roles={['STUDENT']}><StudentRequestDetail /></Guard>} />
      <Route path="/staff/dashboard" element={<Guard roles={['TRIAGE_AGENT', 'DEPARTMENT_STAFF', 'ADMIN']}><StaffDashboard /></Guard>} />
      <Route path="/staff/requests/:id" element={<Guard roles={STAFF}><StaffRequest /></Guard>} />
      <Route path="/staff/triage" element={<Guard roles={['TRIAGE_AGENT', 'ADMIN']}><TriageQueue /></Guard>} />
      <Route path="/staff/clusters" element={<Guard roles={STAFF}><Clusters /></Guard>} />
      <Route path="/staff/clusters/:id" element={<Guard roles={STAFF}><ClusterDetail /></Guard>} />
      <Route path="/staff/escalations" element={<Guard roles={STAFF}><Escalations /></Guard>} />
      <Route path="/dean/dashboard" element={<Guard roles={['DEAN', 'ADMIN']}><DeanDashboard /></Guard>} />
      <Route path="/admin" element={<Guard roles={['ADMIN']}><Admin /></Guard>} />
      <Route path="*" element={!ready ? null : <Navigate to={user ? homeFor(user.role) : '/login'} replace />} />
    </Routes>
  )
}
