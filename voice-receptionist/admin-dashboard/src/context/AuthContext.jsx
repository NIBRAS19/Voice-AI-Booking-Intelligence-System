import { createContext, useContext, useState, useEffect } from 'react'
import api from '../services/api'

const AuthContext = createContext(null)

export function AuthProvider({ children }) {
    const [user, setUser] = useState(null)
    const [isLoading, setIsLoading] = useState(true)

    useEffect(() => {
        // Check for stored token on mount
        const token = localStorage.getItem('access_token')
        if (token) {
            // Validate token (simplified - in production verify with API)
            try {
                const payload = JSON.parse(atob(token.split('.')[1]))
                if (payload.exp * 1000 > Date.now()) {
                    setUser({
                        id: payload.sub,
                        businessId: payload.business_id,
                        role: payload.role,
                    })
                } else {
                    localStorage.removeItem('access_token')
                    localStorage.removeItem('refresh_token')
                }
            } catch {
                localStorage.removeItem('access_token')
            }
        }
        setIsLoading(false)
    }, [])

    const login = async (email, password) => {
        try {
            const response = await api.post('/api/v1/auth/login', { email, password })
            const { access_token, refresh_token } = response.data

            localStorage.setItem('access_token', access_token)
            localStorage.setItem('refresh_token', refresh_token)

            const payload = JSON.parse(atob(access_token.split('.')[1]))
            setUser({
                id: payload.sub,
                businessId: payload.business_id,
                role: payload.role,
            })

            return { success: true }
        } catch (error) {
            return {
                success: false,
                error: error.response?.data?.detail || 'Login failed',
            }
        }
    }

    const logout = () => {
        localStorage.removeItem('access_token')
        localStorage.removeItem('refresh_token')
        setUser(null)
    }

    const value = {
        user,
        isAuthenticated: !!user,
        isLoading,
        login,
        logout,
    }

    return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth() {
    const context = useContext(AuthContext)
    if (!context) {
        throw new Error('useAuth must be used within AuthProvider')
    }
    return context
}
