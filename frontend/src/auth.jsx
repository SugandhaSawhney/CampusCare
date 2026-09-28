import { createContext, useContext, useEffect, useState } from 'react'
import { api, getToken, setToken } from './api'

const Ctx = createContext(null)
export const useAuth = () => useContext(Ctx)

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null)
  const [ready, setReady] = useState(false)
  useEffect(() => {
    if (!getToken()) return setReady(true)
    api('/auth/me').then(setUser).catch(() => setToken(null)).finally(() => setReady(true))
  }, [])
  const login = async (username, password) => {
    const r = await api('/auth/login', { method: 'POST', body: { username, password } })
    setToken(r.access_token); setUser(r.user); return r.user
  }
  const register = async (body) => {
    const r = await api('/auth/register', { method: 'POST', body })
    setToken(r.access_token); setUser(r.user); return r.user
  }
  const logout = () => { setToken(null); setUser(null) }
  return <Ctx.Provider value={{ user, ready, login, register, logout }}>{children}</Ctx.Provider>
}

export const homeFor = (role) =>
  ({ STUDENT: '/student/dashboard', DEAN: '/dean/dashboard', ADMIN: '/staff/dashboard' }[role] || '/staff/dashboard')
