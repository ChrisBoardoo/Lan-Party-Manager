import { createContext, useContext, useState, useEffect, ReactNode } from 'react'
import { User } from '../types'
import { authApi } from '../lib/api'
import { notifyDesktopLogin, notifyDesktopLogout } from '../lib/desktopBridge'

interface AuthContextType {
  user: User | null
  isLoading: boolean
  login: (identifier: string, password: string) => Promise<void>
  register: (username: string, email: string, password: string) => Promise<User>
  logout: () => void
  refreshUser: () => Promise<void>
  isTreasurer: boolean
  isAdmin: boolean
}

const AuthContext = createContext<AuthContextType | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null)
  const [isLoading, setIsLoading] = useState(true)

  useEffect(() => {
    const token = localStorage.getItem('token')
    if (!token) {
      setIsLoading(false)
      return
    }
    // Trade the stored token for a fresh one on every load, not just verify
    // it with /me — this is the sliding-session behavior desktopplan_windows.md
    // calls for ("call /refresh once per launch"), so a tray app opened at
    // least once every 30 days never re-prompts for a password. Harmless for
    // a normal browser tab too: it just quietly extends that session as well.
    authApi
      .refresh()
      .then((data) => {
        localStorage.setItem('token', data.access_token)
        setUser(data.user)
        // Rust's polling state is in-memory and starts fresh on every app
        // launch — resend the token even for an already-logged-in session.
        notifyDesktopLogin(data.access_token)
      })
      .catch(() => localStorage.removeItem('token'))
      .finally(() => setIsLoading(false))
  }, [])

  const login = async (identifier: string, password: string) => {
    const data = await authApi.login({ identifier, password })
    localStorage.setItem('token', data.access_token)
    notifyDesktopLogin(data.access_token)
    setUser(data.user)
  }

  const register = async (username: string, email: string, password: string) => {
    const newUser = await authApi.register({ username, email, password })
    return newUser
  }

  const logout = () => {
    localStorage.removeItem('token')
    notifyDesktopLogout()
    setUser(null)
  }

  const refreshUser = async () => {
    const fresh = await authApi.me()
    setUser(fresh)
  }

  return (
    <AuthContext.Provider
      value={{
        user,
        isLoading,
        login,
        register,
        logout,
        refreshUser,
        isTreasurer: user?.role === 'treasurer' || user?.role === 'admin',
        isAdmin: user?.role === 'admin',
      }}
    >
      {children}
    </AuthContext.Provider>
  )
}

export const useAuth = () => {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be inside AuthProvider')
  return ctx
}
