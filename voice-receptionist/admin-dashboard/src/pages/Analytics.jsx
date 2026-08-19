import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useAuth } from '../context/AuthContext'
import api from '../services/api'

function MetricCard({ label, value, subtext, color = 'primary' }) {
    const colorClasses = {
        primary: 'from-primary-500/20 to-primary-600/10 border-primary-500/30',
        green: 'from-green-500/20 to-green-600/10 border-green-500/30',
        yellow: 'from-yellow-500/20 to-yellow-600/10 border-yellow-500/30',
        red: 'from-red-500/20 to-red-600/10 border-red-500/30',
    }

    return (
        <div className={`p-6 rounded-xl bg-gradient-to-br ${colorClasses[color]} border backdrop-blur-sm`}>
            <p className="text-slate-400 text-sm mb-1">{label}</p>
            <p className="text-3xl font-bold text-white">{value}</p>
            {subtext && <p className="text-sm text-slate-400 mt-1">{subtext}</p>}
        </div>
    )
}

function BarChart({ data, title }) {
    if (!data || data.length === 0) {
        return (
            <div className="h-48 flex items-center justify-center text-slate-400">
                No data available
            </div>
        )
    }

    const maxValue = Math.max(...data.map(d => d.calls || 0))

    return (
        <div>
            <h3 className="text-sm font-medium text-slate-400 mb-4">{title}</h3>
            <div className="flex items-end gap-1 h-48">
                {data.slice(-14).map((day, i) => {
                    const height = maxValue > 0 ? (day.calls / maxValue) * 100 : 0
                    return (
                        <div
                            key={i}
                            className="flex-1 flex flex-col items-center group"
                        >
                            <div
                                className="w-full bg-primary-500/70 rounded-t transition-all hover:bg-primary-400"
                                style={{ height: `${Math.max(height, 2)}%` }}
                                title={`${day.date}: ${day.calls} calls`}
                            />
                            <span className="text-[10px] text-slate-500 mt-1 group-hover:text-slate-300">
                                {new Date(day.date).getDate()}
                            </span>
                        </div>
                    )
                })}
            </div>
        </div>
    )
}

function ServiceBreakdown({ data }) {
    if (!data || data.length === 0) {
        return <p className="text-slate-400 text-center py-4">No bookings yet</p>
    }

    const total = data.reduce((sum, s) => sum + s.bookings, 0)

    return (
        <div className="space-y-3">
            {data.map((service, i) => {
                const percentage = total > 0 ? (service.bookings / total) * 100 : 0
                return (
                    <div key={i}>
                        <div className="flex justify-between text-sm mb-1">
                            <span className="text-white">{service.service}</span>
                            <span className="text-slate-400">{service.bookings} ({percentage.toFixed(0)}%)</span>
                        </div>
                        <div className="w-full h-2 bg-slate-700 rounded-full overflow-hidden">
                            <div
                                className="h-full bg-primary-500 rounded-full transition-all"
                                style={{ width: `${percentage}%` }}
                            />
                        </div>
                    </div>
                )
            })}
        </div>
    )
}

function AIPerformance({ data }) {
    if (!data) return null

    return (
        <div className="space-y-4">
            <div>
                <span className="text-sm text-slate-400">Avg. Conversation Length</span>
                <p className="text-2xl font-bold text-white">{data.avg_conversation_turns} turns</p>
            </div>

            {data.intents?.length > 0 && (
                <div>
                    <h4 className="text-sm text-slate-400 mb-2">Top Intents</h4>
                    <div className="flex flex-wrap gap-2">
                        {data.intents.slice(0, 5).map((intent, i) => (
                            <span
                                key={i}
                                className="px-2 py-1 rounded-full bg-slate-700 text-xs text-slate-300"
                            >
                                {intent.intent}: {intent.count}
                            </span>
                        ))}
                    </div>
                </div>
            )}

            {data.handoff_reasons?.length > 0 && (
                <div>
                    <h4 className="text-sm text-slate-400 mb-2">Handoff Reasons</h4>
                    <div className="space-y-1">
                        {data.handoff_reasons.map((reason, i) => (
                            <div key={i} className="flex justify-between text-sm">
                                <span className="text-yellow-400">{reason.reason}</span>
                                <span className="text-slate-400">{reason.count}</span>
                            </div>
                        ))}
                    </div>
                </div>
            )}
        </div>
    )
}

export default function Analytics() {
    const { user } = useAuth()
    const [days, setDays] = useState(30)

    const businessId = user?.businessId

    const { data: overview, isLoading: overviewLoading } = useQuery({
        queryKey: ['analytics-overview', businessId, days],
        queryFn: async () => {
            const res = await api.get(`/api/v1/analytics/stats/overview?business_id=${businessId}&days=${days}`)
            return res.data
        },
        enabled: !!businessId,
    })

    const { data: callsByDay } = useQuery({
        queryKey: ['analytics-calls-day', businessId, days],
        queryFn: async () => {
            const res = await api.get(`/api/v1/analytics/stats/calls/by-day?business_id=${businessId}&days=${days}`)
            return res.data
        },
        enabled: !!businessId,
    })

    const { data: byService } = useQuery({
        queryKey: ['analytics-by-service', businessId, days],
        queryFn: async () => {
            const res = await api.get(`/api/v1/analytics/stats/bookings/by-service?business_id=${businessId}&days=${days}`)
            return res.data
        },
        enabled: !!businessId,
    })

    const { data: aiPerf } = useQuery({
        queryKey: ['analytics-ai-perf', businessId, days],
        queryFn: async () => {
            const res = await api.get(`/api/v1/analytics/stats/ai/performance?business_id=${businessId}&days=${days}`)
            return res.data
        },
        enabled: !!businessId,
    })

    return (
        <div className="space-y-8 animate-fadeIn">
            {/* Header */}
            <div className="flex items-center justify-between">
                <div>
                    <h1 className="text-3xl font-bold text-white">Analytics</h1>
                    <p className="text-slate-400 mt-1">Call volume, booking rates, and AI performance</p>
                </div>
                <select
                    value={days}
                    onChange={(e) => setDays(Number(e.target.value))}
                    className="bg-slate-800 border border-slate-700 text-white rounded-lg px-4 py-2"
                >
                    <option value={7}>Last 7 days</option>
                    <option value={30}>Last 30 days</option>
                    <option value={90}>Last 90 days</option>
                </select>
            </div>

            {/* Overview Cards */}
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
                <MetricCard
                    label="Total Calls"
                    value={overview?.calls?.total || 0}
                    subtext={`${overview?.calls?.completed || 0} completed`}
                    color="primary"
                />
                <MetricCard
                    label="Total Bookings"
                    value={overview?.bookings?.total || 0}
                    subtext={`${overview?.bookings?.confirmed || 0} confirmed`}
                    color="green"
                />
                <MetricCard
                    label="Conversion Rate"
                    value={`${overview?.rates?.conversion_rate || 0}%`}
                    subtext="Calls → Bookings"
                    color="yellow"
                />
                <MetricCard
                    label="AI Success Rate"
                    value={`${overview?.rates?.ai_success_rate || 0}%`}
                    subtext="Without handoff"
                    color={overview?.rates?.ai_success_rate >= 80 ? 'green' : 'yellow'}
                />
            </div>

            {/* Charts Row */}
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                {/* Call Volume */}
                <div className="card">
                    <h2 className="text-lg font-semibold text-white mb-4">Call Volume</h2>
                    <BarChart data={callsByDay} title="Daily calls" />
                </div>

                {/* Bookings by Service */}
                <div className="card">
                    <h2 className="text-lg font-semibold text-white mb-4">Bookings by Service</h2>
                    <ServiceBreakdown data={byService} />
                </div>
            </div>

            {/* AI Performance */}
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                <div className="card">
                    <h2 className="text-lg font-semibold text-white mb-4">AI Performance</h2>
                    <AIPerformance data={aiPerf} />
                </div>

                {/* Quick Stats */}
                <div className="card">
                    <h2 className="text-lg font-semibold text-white mb-4">Quick Stats</h2>
                    <div className="grid grid-cols-2 gap-4">
                        <div className="p-4 rounded-lg bg-slate-800/50">
                            <p className="text-sm text-slate-400">Pending Bookings</p>
                            <p className="text-2xl font-bold text-yellow-400">
                                {overview?.bookings?.pending || 0}
                            </p>
                        </div>
                        <div className="p-4 rounded-lg bg-slate-800/50">
                            <p className="text-sm text-slate-400">Cancelled</p>
                            <p className="text-2xl font-bold text-red-400">
                                {overview?.bookings?.cancelled || 0}
                            </p>
                        </div>
                        <div className="p-4 rounded-lg bg-slate-800/50">
                            <p className="text-sm text-slate-400">Transferred Calls</p>
                            <p className="text-2xl font-bold text-orange-400">
                                {overview?.calls?.transferred || 0}
                            </p>
                        </div>
                        <div className="p-4 rounded-lg bg-slate-800/50">
                            <p className="text-sm text-slate-400">Period</p>
                            <p className="text-2xl font-bold text-slate-300">
                                {days}d
                            </p>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    )
}
