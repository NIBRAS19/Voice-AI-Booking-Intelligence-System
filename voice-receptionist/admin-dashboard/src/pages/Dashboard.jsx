import { useQuery } from '@tanstack/react-query'
import api from '../services/api'

function StatCard({ icon, label, value, trend, color }) {
    return (
        <div className="card group hover:border-primary-500/30 transition-all duration-300">
            <div className="flex items-start justify-between">
                <div>
                    <p className="text-slate-400 text-sm mb-1">{label}</p>
                    <p className="text-3xl font-bold text-white">{value}</p>
                    {trend && (
                        <p className={`text-sm mt-2 ${trend > 0 ? 'text-green-400' : 'text-red-400'}`}>
                            {trend > 0 ? '↑' : '↓'} {Math.abs(trend)}% from last week
                        </p>
                    )}
                </div>
                <div className={`w-12 h-12 rounded-xl ${color} flex items-center justify-center text-2xl transform group-hover:scale-110 transition-transform`}>
                    {icon}
                </div>
            </div>
        </div>
    )
}

function PendingBookingCard({ booking, onApprove, onReject }) {
    return (
        <div className="p-4 rounded-xl bg-slate-800/30 border border-slate-700/50 hover:border-primary-500/30 transition-all animate-fadeIn">
            <div className="flex items-start justify-between">
                <div>
                    <h4 className="font-medium text-white">{booking.customer_name || 'Customer'}</h4>
                    <p className="text-sm text-slate-400 mt-1">{booking.service_name}</p>
                    <p className="text-sm text-primary-400 mt-1">{booking.formatted_time}</p>
                </div>
                <div className="flex gap-2">
                    <button
                        onClick={() => onApprove(booking.id)}
                        className="p-2 rounded-lg bg-green-600/20 text-green-400 hover:bg-green-600/40 transition-colors"
                        title="Approve"
                    >
                        ✓
                    </button>
                    <button
                        onClick={() => onReject(booking.id)}
                        className="p-2 rounded-lg bg-red-600/20 text-red-400 hover:bg-red-600/40 transition-colors"
                        title="Reject"
                    >
                        ✕
                    </button>
                </div>
            </div>
        </div>
    )
}

function RecentConversation({ conversation }) {
    const statusColors = {
        completed: 'text-green-400',
        active: 'text-blue-400',
        transferred: 'text-yellow-400',
        failed: 'text-red-400',
    }

    return (
        <div className="p-4 rounded-xl bg-slate-800/30 border border-slate-700/50 hover:border-slate-600/50 transition-all">
            <div className="flex items-center justify-between">
                <div className="flex items-center gap-3">
                    <div className="w-10 h-10 rounded-full bg-slate-700 flex items-center justify-center">
                        📞
                    </div>
                    <div>
                        <p className="font-medium text-white">{conversation.phone_number || 'Unknown'}</p>
                        <p className="text-xs text-slate-400">{conversation.duration_seconds || 0}s</p>
                    </div>
                </div>
                <span className={`text-xs font-medium ${statusColors[conversation.status] || 'text-slate-400'}`}>
                    {conversation.status}
                </span>
            </div>
            {conversation.final_outcome && (
                <p className="text-sm text-slate-400 mt-2 truncate">{conversation.final_outcome}</p>
            )}
        </div>
    )
}

export default function Dashboard() {
    const { data: stats, isLoading: statsLoading } = useQuery({
        queryKey: ['dashboard-stats'],
        queryFn: async () => {
            const res = await api.get('/api/v1/admin/dashboard')
            return res.data
        },
    })

    const { data: pending, refetch: refetchPending } = useQuery({
        queryKey: ['pending-bookings'],
        queryFn: async () => {
            const res = await api.get('/api/v1/admin/pending')
            return res.data
        },
    })

    const { data: conversations } = useQuery({
        queryKey: ['recent-conversations'],
        queryFn: async () => {
            const res = await api.get('/api/v1/admin/conversations?limit=5')
            return res.data
        },
    })

    const handleApprove = async (bookingId) => {
        await api.patch(`/api/v1/admin/bookings/${bookingId}/approve`)
        refetchPending()
    }

    const handleReject = async (bookingId) => {
        await api.patch(`/api/v1/admin/bookings/${bookingId}/reject`)
        refetchPending()
    }

    return (
        <div className="space-y-8 animate-fadeIn">
            {/* Header */}
            <div>
                <h1 className="text-3xl font-bold text-white">Dashboard</h1>
                <p className="text-slate-400 mt-1">Overview of your voice receptionist activity</p>
            </div>

            {/* Stats Grid */}
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
                <StatCard
                    icon="⏳"
                    label="Pending Approvals"
                    value={stats?.pending_approvals || 0}
                    color="bg-yellow-500/20"
                />
                <StatCard
                    icon="📅"
                    label="Today's Bookings"
                    value={stats?.today_bookings || 0}
                    color="bg-blue-500/20"
                />
                <StatCard
                    icon="📊"
                    label="This Week"
                    value={stats?.this_week_bookings || 0}
                    color="bg-green-500/20"
                />
                <StatCard
                    icon="📈"
                    label="Total Bookings"
                    value={stats?.total_bookings || 0}
                    color="bg-purple-500/20"
                />
            </div>

            {/* Two columns */}
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                {/* Pending Approvals */}
                <div className="card">
                    <div className="flex items-center justify-between mb-4">
                        <h2 className="text-lg font-semibold text-white">Pending Approvals</h2>
                        {pending?.count > 0 && (
                            <span className="badge badge-pending">{pending.count}</span>
                        )}
                    </div>
                    <div className="space-y-3 max-h-80 overflow-y-auto">
                        {pending?.bookings?.length > 0 ? (
                            pending.bookings.map((booking) => (
                                <PendingBookingCard
                                    key={booking.id}
                                    booking={booking}
                                    onApprove={handleApprove}
                                    onReject={handleReject}
                                />
                            ))
                        ) : (
                            <p className="text-slate-400 text-center py-8">
                                No pending approvals 🎉
                            </p>
                        )}
                    </div>
                </div>

                {/* Recent Conversations */}
                <div className="card">
                    <h2 className="text-lg font-semibold text-white mb-4">Recent Calls</h2>
                    <div className="space-y-3 max-h-80 overflow-y-auto">
                        {conversations?.conversations?.length > 0 ? (
                            conversations.conversations.map((conv) => (
                                <RecentConversation key={conv.id} conversation={conv} />
                            ))
                        ) : (
                            <p className="text-slate-400 text-center py-8">
                                No recent calls
                            </p>
                        )}
                    </div>
                </div>
            </div>
        </div>
    )
}
