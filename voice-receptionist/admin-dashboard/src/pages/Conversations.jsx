import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import api from '../services/api'

function ConversationCard({ conversation, onView }) {
    const statusColors = {
        completed: 'border-green-500/30 bg-green-500/10',
        active: 'border-blue-500/30 bg-blue-500/10',
        transferred: 'border-yellow-500/30 bg-yellow-500/10',
        failed: 'border-red-500/30 bg-red-500/10',
    }

    const statusText = {
        completed: 'text-green-400',
        active: 'text-blue-400',
        transferred: 'text-yellow-400',
        failed: 'text-red-400',
    }

    const formatDuration = (seconds) => {
        if (!seconds) return '0s'
        const mins = Math.floor(seconds / 60)
        const secs = seconds % 60
        return mins > 0 ? `${mins}m ${secs}s` : `${secs}s`
    }

    return (
        <div
            className={`card cursor-pointer hover:shadow-lg transition-all ${statusColors[conversation.status] || ''}`}
            onClick={() => onView(conversation)}
        >
            <div className="flex items-start justify-between">
                <div className="flex items-center gap-3">
                    <div className="w-12 h-12 rounded-xl bg-slate-700/50 flex items-center justify-center text-2xl">
                        📞
                    </div>
                    <div>
                        <p className="font-medium text-white">{conversation.phone_number || 'Unknown Number'}</p>
                        <p className="text-sm text-slate-400">
                            {new Date(conversation.started_at).toLocaleString()}
                        </p>
                    </div>
                </div>
                <div className="text-right">
                    <span className={`text-sm font-medium capitalize ${statusText[conversation.status] || 'text-slate-400'}`}>
                        {conversation.status}
                    </span>
                    <p className="text-xs text-slate-500 mt-1">
                        {formatDuration(conversation.duration_seconds)}
                    </p>
                </div>
            </div>

            <div className="mt-4 pt-4 border-t border-slate-700/50">
                <div className="flex items-center gap-4 text-sm">
                    {conversation.current_intent && (
                        <span className="px-2 py-1 rounded bg-primary-500/20 text-primary-300">
                            {conversation.current_intent.replace('_', ' ')}
                        </span>
                    )}
                    {conversation.transferred_to_human && (
                        <span className="px-2 py-1 rounded bg-yellow-500/20 text-yellow-300">
                            Transferred
                        </span>
                    )}
                    {conversation.booking_id && (
                        <span className="px-2 py-1 rounded bg-green-500/20 text-green-300">
                            Booking Created
                        </span>
                    )}
                </div>
                {conversation.final_outcome && (
                    <p className="text-sm text-slate-400 mt-3 line-clamp-2">
                        {conversation.final_outcome}
                    </p>
                )}
            </div>
        </div>
    )
}

function TranscriptModal({ session, onClose }) {
    const { data, isLoading } = useQuery({
        queryKey: ['conversation-transcript', session?.id],
        queryFn: async () => {
            const res = await api.get(`/api/v1/admin/conversations/${session.id}/transcript`)
            return res.data
        },
        enabled: !!session?.id,
    })

    if (!session) return null

    return (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
            <div className="absolute inset-0 bg-black/60 backdrop-blur-sm" onClick={onClose}></div>
            <div className="relative bg-slate-800 rounded-2xl border border-slate-700 p-6 max-w-2xl w-full max-h-[80vh] flex flex-col animate-fadeIn shadow-2xl">
                <button
                    onClick={onClose}
                    className="absolute top-4 right-4 text-slate-400 hover:text-white z-10"
                >
                    ✕
                </button>

                <div className="mb-4">
                    <h2 className="text-xl font-bold text-white">Conversation Transcript</h2>
                    <p className="text-sm text-slate-400">
                        {session.phone_number || 'Unknown'} • {new Date(session.started_at).toLocaleString()}
                    </p>
                </div>

                <div className="flex-1 overflow-y-auto space-y-3">
                    {isLoading ? (
                        <div className="flex justify-center py-12">
                            <div className="animate-spin w-8 h-8 border-2 border-primary-500 border-t-transparent rounded-full"></div>
                        </div>
                    ) : data?.turns?.length > 0 ? (
                        data.turns.map((turn, idx) => (
                            <div
                                key={idx}
                                className={`p-3 rounded-xl max-w-[85%] ${turn.role === 'assistant'
                                        ? 'bg-primary-600/20 border border-primary-500/30 ml-auto'
                                        : 'bg-slate-700/50 border border-slate-600/30'
                                    }`}
                            >
                                <p className="text-xs text-slate-400 mb-1 capitalize">{turn.role}</p>
                                <p className="text-white">{turn.content}</p>
                                {turn.intent && (
                                    <p className="text-xs text-primary-400 mt-2">Intent: {turn.intent}</p>
                                )}
                            </div>
                        ))
                    ) : (
                        <p className="text-center text-slate-400 py-12">No transcript available</p>
                    )}
                </div>

                <div className="mt-4 pt-4 border-t border-slate-700/50 text-xs text-slate-500">
                    Session ID: {session.id}
                </div>
            </div>
        </div>
    )
}

export default function Conversations() {
    const [selectedSession, setSelectedSession] = useState(null)

    const { data, isLoading } = useQuery({
        queryKey: ['conversations'],
        queryFn: async () => {
            const res = await api.get('/api/v1/admin/conversations?limit=50')
            return res.data
        },
    })

    return (
        <div className="space-y-6 animate-fadeIn">
            {/* Header */}
            <div>
                <h1 className="text-3xl font-bold text-white">Conversations</h1>
                <p className="text-slate-400 mt-1">Review AI call sessions and transcripts</p>
            </div>

            {/* Stats */}
            <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
                {[
                    { label: 'Total Calls', value: data?.count || 0, color: 'bg-blue-500/20' },
                    { label: 'Completed', value: data?.conversations?.filter(c => c.status === 'completed').length || 0, color: 'bg-green-500/20' },
                    { label: 'Transferred', value: data?.conversations?.filter(c => c.transferred_to_human).length || 0, color: 'bg-yellow-500/20' },
                    { label: 'Bookings Made', value: data?.conversations?.filter(c => c.booking_id).length || 0, color: 'bg-purple-500/20' },
                ].map((stat) => (
                    <div key={stat.label} className={`card ${stat.color}`}>
                        <p className="text-sm text-slate-400">{stat.label}</p>
                        <p className="text-2xl font-bold text-white">{stat.value}</p>
                    </div>
                ))}
            </div>

            {/* Conversation Grid */}
            {isLoading ? (
                <div className="flex justify-center py-12">
                    <div className="animate-spin w-10 h-10 border-2 border-primary-500 border-t-transparent rounded-full"></div>
                </div>
            ) : (
                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                    {data?.conversations?.map((conv) => (
                        <ConversationCard
                            key={conv.id}
                            conversation={conv}
                            onView={setSelectedSession}
                        />
                    ))}
                </div>
            )}

            {!isLoading && (!data?.conversations?.length) && (
                <div className="text-center py-12 text-slate-400">
                    <p className="text-4xl mb-4">📞</p>
                    <p>No conversations yet</p>
                </div>
            )}

            {/* Transcript Modal */}
            {selectedSession && (
                <TranscriptModal
                    session={selectedSession}
                    onClose={() => setSelectedSession(null)}
                />
            )}
        </div>
    )
}
