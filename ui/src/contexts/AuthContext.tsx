import { createContext, useContext, useEffect, useState, type ReactNode } from 'react'
import { login as apiLogin } from '@/api/client'

interface AuthState {
  idToken: string | null
  accessToken: string | null
  sub: string | null
  isAuthenticated: boolean
  login: (email: string, password: string) => Promise<void>
  logout: () => void
}

function decodeSub(idToken: string): string | null {
  try {
    const payload = JSON.parse(atob(idToken.split('.')[1]))
    return payload.sub ?? null
  } catch {
    return null
  }
}

const AuthContext = createContext<AuthState | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [idToken, setIdToken] = useState<string | null>(() => localStorage.getItem('id_token'))
  const [accessToken, setAccessToken] = useState<string | null>(() => localStorage.getItem('access_token'))

  const sub = idToken ? decodeSub(idToken) : null

  useEffect(() => {
    if (idToken) localStorage.setItem('id_token', idToken)
    else localStorage.removeItem('id_token')
  }, [idToken])

  useEffect(() => {
    if (accessToken) localStorage.setItem('access_token', accessToken)
    else localStorage.removeItem('access_token')
  }, [accessToken])

  async function login(email: string, password: string) {
    const res = await apiLogin(email, password)
    setIdToken(res.idToken)
    setAccessToken(res.accessToken)
    localStorage.setItem('refresh_token', res.refreshToken)
  }

  function logout() {
    setIdToken(null)
    setAccessToken(null)
    localStorage.removeItem('id_token')
    localStorage.removeItem('access_token')
    localStorage.removeItem('refresh_token')
  }

  return (
    <AuthContext.Provider value={{ idToken, accessToken, sub, isAuthenticated: !!idToken, login, logout }}>
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth() {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used within AuthProvider')
  return ctx
}
