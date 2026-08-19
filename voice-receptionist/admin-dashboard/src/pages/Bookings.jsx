import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import api from '../services/api'

const statusOptions = [
    { value: '', label: 'All Statuses' },
    { value: 'pending_approval', label: 'Pending' },
    { value: 'confirmed', label: 'Confirmed' },
    { value: 'completed', label: 'Completed' },
    { value: 'cancelled', label: 'Cancelled' },
]

function BookingRow({ booking, onApprove, onReject, onView }) {
    const statusColors = {
        pending_approval: 'badge-pending',
        confirmed: 'badge-confirmed',
        completed: 'badge-completed',
        cancelled: 'badge-cancelled',
    }

    return (
        <tr className="border-b border-slate-700/50 hover:bg-slate-800/30 transition-colors">
            <td className="px-4 py-4">
                <div>
                    <p className="font-medium text-white">{booking.customer_name || 'Customer'}</p>
                    <p className="text-sm text-slate-400">{booking.customer_phone}</p>
                </div>
            </td>
            <td className="px-4 py-4">
                <p className="text-white">{booking.service_name}</p>
            </td>
            <td className="px-4 py-4">
                <p className="text-white">{booking.formatted_time || new Date(booking.start_time).toLocaleString()}</p>
            </td>
            <td className="px-4 py-4">
                <span className={`badge ${statusColors[booking.status] || 'badge-pending'}`}>
                    {booking.status?.replace('_', ' ')}
                </span>
            </td>
            <td className="px-4 py-4">
                <div className="flex gap-2">
                    {booking.status === 'pending_approval' && (
                        <>
                            <button
                                onClick={() => onApprove(booking.id)}
                                className="px-3 py-1 rounded-lg bg-green-600/20 text-green-400 hover:bg-green-600/40 text-sm transition-colors"
                            >
                                Approve
                            </button>
                            <button
                                onClick={() => onReject(booking.id)}
                                className="px-3 py-1 rounded-lg bg-red-600/20 text-red-400 hover:bg-red-600/40 text-sm transition-colors"
                            >
                                Reject
                            </button>
                        </>
                    )}
                    <button
                        onClick={() => onView(booking)}
                        className="px-3 py-1 rounded-lg bg-slate-600/30 text-slate-300 hover:bg-slate-600/50 text-sm transition-colors"
                    >
                        View
                    </button>
                </div>
            </td>
        </tr>
    )
}

function BookingModal({ booking, onClose }) {
    if (!booking) return null

    return (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
            <div className="absolute inset-0 bg-black/60 backdrop-blur-sm" onClick={onClose}></div>
            <div className="relative bg-slate-800 rounded-2xl border border-slate-700 p-6 max-w-lg w-full animate-fadeIn shadow-2xl">
                <button
                    onClick={onClose}
                    className="absolute top-4 right-4 text-slate-400 hover:text-white"
                >
                    ✕
                </button>

                <h2 className="text-xl font-bold text-white mb-4">Booking Details</h2>

                <div className="space-y-4">
                    <div className="grid grid-cols-2 gap-4">
                        <div>
                            <label className="text-sm text-slate-400">Customer</label>
                            <p className="text-white font-medium">{booking.customer_name || 'N/A'}</p>
                        </div>
                        <div>
                            <label className="text-sm text-slate-400">Phone</label>
                            <p className="text-white">{booking.customer_phone}</p>
                        </div>
                        <div>
                            <label className="text-sm text-slate-400">Service</label>
                            <p className="text-white">{booking.service_name}</p>
                        </div>
                        <div>
                            <label className="text-sm text-slate-400">Status</label>
                            <p className="text-white capitalize">{booking.status?.replace('_', ' ')}</p>
                        </div>
                        <div>
                            <label className="text-sm text-slate-400">Start Time</label>
                            <p className="text-white">{new Date(booking.start_time).toLocaleString()}</p>
                        </div>
                        <div>
                            <label className="text-sm text-slate-400">End Time</label>
                            <p className="text-white">{new Date(booking.end_time).toLocaleString()}</p>
                        </div>
                    </div>

                    {booking.customer_notes && (
                        <div>
                            <label className="text-sm text-slate-400">Customer Notes</label>
                            <p className="text-white bg-slate-700/50 rounded-lg p-3 mt-1">{booking.customer_notes}</p>
                        </div>
                    )}

                    {booking.admin_notes && (
                        <div>
                            <label className="text-sm text-slate-400">Admin Notes</label>
                            <p className="text-white bg-slate-700/50 rounded-lg p-3 mt-1">{booking.admin_notes}</p>
                        </div>
                    )}

                    <div className="text-xs text-slate-500">
                        ID: {booking.id}<br />
                        Created: {new Date(booking.created_at).toLocaleString()}
                    </div>
                </div>
            </div>
        </div>
    )
}

export default function Bookings() {
    const [statusFilter, setStatusFilter] = useState('')
    const [selectedBooking, setSelectedBooking] = useState(null)
    const queryClient = useQueryClient()

    const { data, isLoading, refetch } = useQuery({
        queryKey: ['bookings', statusFilter],
        queryFn: async () => {
            const params = new URLSearchParams()
            if (statusFilter) params.append('status', statusFilter)
            const res = await api.get(`/api/v1/admin/bookings?${params}`)
            return res.data
        },
    })

    const approveMutation = useMutation({
        mutationFn: (id) => api.patch(`/api/v1/admin/bookings/${id}/approve`),
        onSuccess: () => {
            queryClient.invalidateQueries(['bookings'])
            queryClient.invalidateQueries(['pending-bookings'])
            queryClient.invalidateQueries(['dashboard-stats'])
        },
    })

    const rejectMutation = useMutation({
        mutationFn: (id) => api.patch(`/api/v1/admin/bookings/${id}/reject`),
        onSuccess: () => {
            queryClient.invalidateQueries(['bookings'])
            queryClient.invalidateQueries(['pending-bookings'])
            queryClient.invalidateQueries(['dashboard-stats'])
        },
    })

    return (
        <div className="space-y-6 animate-fadeIn">
            {/* Header */}
            <div className="flex items-center justify-between">
                <div>
                    <h1 className="text-3xl font-bold text-white">Bookings</h1>
                    <p className="text-slate-400 mt-1">Manage all appointments</p>
                </div>
                <select
                    value={statusFilter}
                    onChange={(e) => setStatusFilter(e.target.value)}
                    className="input w-48"
                >
                    {statusOptions.map((opt) => (
                        <option key={opt.value} value={opt.value}>{opt.label}</option>
                    ))}
                </select>
            </div>

            {/* Table */}
            <div className="card overflow-hidden p-0">
                <div className="overflow-x-auto">
                    <table className="w-full">
                        <thead>
                            <tr className="border-b border-slate-700/50 bg-slate-800/30">
                                <th className="px-4 py-3 text-left text-sm font-medium text-slate-400">Customer</th>
                                <th className="px-4 py-3 text-left text-sm font-medium text-slate-400">Service</th>
                                <th className="px-4 py-3 text-left text-sm font-medium text-slate-400">Date & Time</th>
                                <th className="px-4 py-3 text-left text-sm font-medium text-slate-400">Status</th>
                                <th className="px-4 py-3 text-left text-sm font-medium text-slate-400">Actions</th>
                            </tr>
                        </thead>
                        <tbody>
                            {isLoading ? (
                                <tr>
                                    <td colSpan="5" className="px-4 py-12 text-center text-slate-400">
                                        <div className="animate-spin w-8 h-8 border-2 border-primary-500 border-t-transparent rounded-full mx-auto"></div>
                                    </td>
                                </tr>
                            ) : data?.bookings?.length > 0 ? (
                                data.bookings.map((booking) => (
                                    <BookingRow
                                        key={booking.id}
                                        booking={booking}
                                        onApprove={(id) => approveMutation.mutate(id)}
                                        onReject={(id) => rejectMutation.mutate(id)}
                                        onView={setSelectedBooking}
                                    />
                                ))
                            ) : (
                                <tr>
                                    <td colSpan="5" className="px-4 py-12 text-center text-slate-400">
                                        No bookings found
                                    </td>
                                </tr>
                            )}
                        </tbody>
                    </table>
                </div>
            </div>

            {/* Modal */}
            {selectedBooking && (
                <BookingModal
                    booking={selectedBooking}
                    onClose={() => setSelectedBooking(null)}
                />
            )}
        </div>
    )
}
