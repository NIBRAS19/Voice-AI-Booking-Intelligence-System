import { Outlet, NavLink, useNavigate } from 'react-router-dom'
import { useCallback } from 'react'
import { useAuth } from '../context/AuthContext'
import { useWebSocket, showToast } from '../hooks/useWebSocket'

const navItems = [
    { path: '/', label: 'Dashboard', icon: '📊' },
    { path: '/bookings', label: 'Bookings', icon: '📅' },
    { path: '/conversations', label: 'Conversations', icon: '💬' },
    { path: '/analytics', label: 'Analytics', icon: '📈' },
    { path: '/settings', label: 'Settings', icon: '⚙️' },
]

export default function Layout() {
    const { user, logout } = useAuth()
    const navigate = useNavigate()

    // Handle WebSocket events
    const handleWebSocketEvent = useCallback((message) => {
        switch (message.type) {
            case 'new_booking':
                showToast(
                    `New booking from ${message.data?.customer_name || 'Customer'} - ${message.data?.service_name || 'Service'}`,
                    'info'
                )
                // Optionally trigger a refresh of pending counts
                break
            case 'booking_updated':
                showToast('Booking status updated', 'success')
                break
            case 'connected':
                console.log('WebSocket connected to server')
                break
            default:
                console.log('Unknown event type:', message.type)
        }
    }, [])

    // Connect WebSocket
    const { isConnected } = useWebSocket(handleWebSocketEvent)

    const handleLogout = () => {
        logout()
        navigate('/login')
    }

    return (
        <div className="min-h-screen flex bg-slate-900">
            {/* Sidebar */}
            <aside className="w-64 bg-slate-800/50 border-r border-slate-700/50 flex flex-col">
                {/* Logo */}
                <div className="p-6 border-b border-slate-700/50">
                    <h1 className="text-xl font-bold bg-gradient-to-r from-primary-400 to-primary-600 bg-clip-text text-transparent">
                        Voice Receptionist
                    </h1>
                    <div className="flex items-center gap-2 mt-1">
                        <p className="text-xs text-slate-400">Admin Dashboard</p>
                        {/* Connection indicator */}
                        <span className={`w-2 h-2 rounded-full ${isConnected ? 'bg-green-500' : 'bg-red-500'}`}
                            title={isConnected ? 'Connected' : 'Disconnected'} />
                    </div>
                </div>

                {/* Navigation */}
                <nav className="flex-1 p-4">
                    <ul className="space-y-2">
                        {navItems.map((item) => (
                            <li key={item.path}>
                                <NavLink
                                    to={item.path}
                                    end={item.path === '/'}
                                    className={({ isActive }) =>
                                        `flex items-center gap-3 px-4 py-3 rounded-lg transition-all duration-200 ${isActive
                                            ? 'bg-primary-600/20 text-primary-400 border border-primary-500/30'
                                            : 'text-slate-400 hover:bg-slate-700/50 hover:text-white'
                                        }`
                                    }
                                >
                                    <span>{item.icon}</span>
                                    <span>{item.label}</span>
                                </NavLink>
                            </li>
                        ))}
                    </ul>
                </nav>

                {/* User section */}
                <div className="p-4 border-t border-slate-700/50">
                    <div className="flex items-center gap-3 mb-4">
                        <div className="w-10 h-10 rounded-full bg-gradient-to-br from-primary-500 to-primary-700 flex items-center justify-center text-white font-medium">
                            {user?.role?.[0]?.toUpperCase() || 'A'}
                        </div>
                        <div>
                            <p className="text-sm font-medium text-white capitalize">{user?.role || 'Admin'}</p>
                            <p className="text-xs text-slate-400">Logged in</p>
                        </div>
                    </div>
                    <button
                        onClick={handleLogout}
                        className="w-full px-4 py-2 rounded-lg bg-slate-700/50 text-slate-300 hover:bg-red-600/20 hover:text-red-400 transition-colors text-sm"
                    >
                        Sign Out
                    </button>
                </div>
            </aside>

            {/* Main content */}
            <main className="flex-1 overflow-auto">
                <div className="p-8">
                    <Outlet />
                </div>
            </main>
        </div>
    )
}

