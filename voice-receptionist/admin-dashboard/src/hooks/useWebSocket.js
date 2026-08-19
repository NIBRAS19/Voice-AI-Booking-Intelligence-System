import { useEffect, useRef, useCallback, useState } from 'react'
import { useAuth } from '../context/AuthContext'

/**
 * WebSocket hook for real-time admin notifications.
 * 
 * Connects to the backend WebSocket endpoint and handles:
 * - Connection management (connect/disconnect/reconnect)
 * - Event handling for new bookings and updates
 * - Toast notifications for important events
 */
export function useWebSocket(onEvent) {
    const { user, isAuthenticated } = useAuth()
    const wsRef = useRef(null)
    const reconnectTimeoutRef = useRef(null)
    const [isConnected, setIsConnected] = useState(false)

    const connect = useCallback(() => {
        if (!isAuthenticated || !user?.businessId) return

        const token = localStorage.getItem('access_token')
        const wsUrl = `${window.location.protocol === 'https:' ? 'wss:' : 'ws:'}//${window.location.host}/api/v1/ws/admin/${user.businessId}?token=${token}`

        // For development with different ports
        const devWsUrl = `ws://localhost:8000/api/v1/ws/admin/${user.businessId}?token=${token}`
        const url = import.meta.env.DEV ? devWsUrl : wsUrl

        try {
            wsRef.current = new WebSocket(url)

            wsRef.current.onopen = () => {
                console.log('WebSocket connected')
                setIsConnected(true)
            }

            wsRef.current.onmessage = (event) => {
                try {
                    const message = JSON.parse(event.data)
                    console.log('WebSocket message:', message)

                    if (onEvent) {
                        onEvent(message)
                    }
                } catch (e) {
                    console.error('Failed to parse WebSocket message:', e)
                }
            }

            wsRef.current.onclose = () => {
                console.log('WebSocket disconnected')
                setIsConnected(false)

                // Attempt reconnect after 5 seconds
                reconnectTimeoutRef.current = setTimeout(() => {
                    if (isAuthenticated) {
                        connect()
                    }
                }, 5000)
            }

            wsRef.current.onerror = (error) => {
                console.error('WebSocket error:', error)
            }
        } catch (e) {
            console.error('Failed to create WebSocket:', e)
        }
    }, [isAuthenticated, user?.businessId, onEvent])

    const disconnect = useCallback(() => {
        if (reconnectTimeoutRef.current) {
            clearTimeout(reconnectTimeoutRef.current)
        }
        if (wsRef.current) {
            wsRef.current.close()
            wsRef.current = null
        }
        setIsConnected(false)
    }, [])

    useEffect(() => {
        if (isAuthenticated && user?.businessId) {
            connect()
        }

        return () => {
            disconnect()
        }
    }, [isAuthenticated, user?.businessId, connect, disconnect])

    return { isConnected, reconnect: connect }
}

/**
 * Simple toast notification manager.
 * Creates toast notifications that auto-dismiss.
 */
export function showToast(message, type = 'info') {
    // Create toast container if it doesn't exist
    let container = document.getElementById('toast-container')
    if (!container) {
        container = document.createElement('div')
        container.id = 'toast-container'
        container.style.cssText = `
            position: fixed;
            top: 20px;
            right: 20px;
            z-index: 9999;
            display: flex;
            flex-direction: column;
            gap: 10px;
        `
        document.body.appendChild(container)
    }

    // Create toast element
    const toast = document.createElement('div')
    const colors = {
        info: 'background: #3b82f6;',
        success: 'background: #22c55e;',
        warning: 'background: #f59e0b;',
        error: 'background: #ef4444;',
    }

    toast.style.cssText = `
        ${colors[type] || colors.info}
        color: white;
        padding: 12px 20px;
        border-radius: 8px;
        box-shadow: 0 4px 12px rgba(0,0,0,0.3);
        font-size: 14px;
        max-width: 350px;
        animation: slideIn 0.3s ease;
    `
    toast.textContent = message

    // Add animation styles if not present
    if (!document.getElementById('toast-styles')) {
        const style = document.createElement('style')
        style.id = 'toast-styles'
        style.textContent = `
            @keyframes slideIn {
                from { transform: translateX(100%); opacity: 0; }
                to { transform: translateX(0); opacity: 1; }
            }
            @keyframes slideOut {
                from { transform: translateX(0); opacity: 1; }
                to { transform: translateX(100%); opacity: 0; }
            }
        `
        document.head.appendChild(style)
    }

    container.appendChild(toast)

    // Auto-dismiss after 5 seconds
    setTimeout(() => {
        toast.style.animation = 'slideOut 0.3s ease'
        setTimeout(() => {
            toast.remove()
        }, 300)
    }, 5000)
}
