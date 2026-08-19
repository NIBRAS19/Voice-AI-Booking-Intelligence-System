import { useState } from 'react'
import { useAuth } from '../context/AuthContext'

function Section({ title, children }) {
    return (
        <div className="card">
            <h2 className="text-lg font-semibold text-white mb-4">{title}</h2>
            {children}
        </div>
    )
}

function Toggle({ label, description, checked, onChange }) {
    return (
        <div className="flex items-center justify-between py-3">
            <div>
                <p className="text-white font-medium">{label}</p>
                {description && <p className="text-sm text-slate-400">{description}</p>}
            </div>
            <button
                onClick={() => onChange(!checked)}
                className={`relative w-12 h-6 rounded-full transition-colors ${checked ? 'bg-primary-600' : 'bg-slate-600'
                    }`}
            >
                <span
                    className={`absolute top-1 w-4 h-4 rounded-full bg-white transition-transform ${checked ? 'translate-x-7' : 'translate-x-1'
                        }`}
                />
            </button>
        </div>
    )
}

export default function Settings() {
    const { user } = useAuth()
    const [settings, setSettings] = useState({
        emailNotifications: true,
        smsNotifications: true,
        autoApprove: false,
        aiDisclosure: true,
        callRecording: true,
    })
    const [saved, setSaved] = useState(false)

    const handleToggle = (key) => {
        setSettings(prev => ({ ...prev, [key]: !prev[key] }))
        setSaved(false)
    }

    const handleSave = () => {
        // In production, save to API
        setSaved(true)
        setTimeout(() => setSaved(false), 3000)
    }

    return (
        <div className="space-y-6 animate-fadeIn max-w-3xl">
            {/* Header */}
            <div>
                <h1 className="text-3xl font-bold text-white">Settings</h1>
                <p className="text-slate-400 mt-1">Configure your voice receptionist</p>
            </div>

            {/* Account Info */}
            <Section title="Account Information">
                <div className="grid grid-cols-2 gap-4">
                    <div>
                        <label className="text-sm text-slate-400">Role</label>
                        <p className="text-white font-medium capitalize">{user?.role || 'Admin'}</p>
                    </div>
                    <div>
                        <label className="text-sm text-slate-400">Business ID</label>
                        <p className="text-white font-mono text-sm">{user?.businessId?.slice(0, 8) || 'N/A'}...</p>
                    </div>
                </div>
            </Section>

            {/* Notifications */}
            <Section title="Notifications">
                <div className="divide-y divide-slate-700/50">
                    <Toggle
                        label="Email Notifications"
                        description="Receive booking alerts via email"
                        checked={settings.emailNotifications}
                        onChange={() => handleToggle('emailNotifications')}
                    />
                    <Toggle
                        label="SMS Notifications"
                        description="Receive booking alerts via SMS"
                        checked={settings.smsNotifications}
                        onChange={() => handleToggle('smsNotifications')}
                    />
                </div>
            </Section>

            {/* Booking Settings */}
            <Section title="Booking Settings">
                <div className="divide-y divide-slate-700/50">
                    <Toggle
                        label="Auto-Approve Bookings"
                        description="Automatically confirm new bookings"
                        checked={settings.autoApprove}
                        onChange={() => handleToggle('autoApprove')}
                    />
                </div>
            </Section>

            {/* AI Settings */}
            <Section title="AI Voice Settings">
                <div className="divide-y divide-slate-700/50">
                    <Toggle
                        label="AI Disclosure"
                        description="Inform callers they're speaking with an AI"
                        checked={settings.aiDisclosure}
                        onChange={() => handleToggle('aiDisclosure')}
                    />
                    <Toggle
                        label="Call Recording"
                        description="Record calls for quality and training"
                        checked={settings.callRecording}
                        onChange={() => handleToggle('callRecording')}
                    />
                </div>

                <div className="mt-4">
                    <label className="text-sm text-slate-400 block mb-2">Greeting Message</label>
                    <textarea
                        className="input min-h-[100px] resize-none"
                        placeholder="Thank you for calling! How can I help you today?"
                        defaultValue="Thank you for calling! This is an AI assistant. How can I help you today?"
                    />
                </div>
            </Section>

            {/* Working Hours */}
            <Section title="Working Hours">
                <div className="space-y-3">
                    {['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday'].map((day) => (
                        <div key={day} className="flex items-center gap-4">
                            <span className="w-24 text-white">{day}</span>
                            <input
                                type="time"
                                className="input w-32"
                                defaultValue="09:00"
                            />
                            <span className="text-slate-400">to</span>
                            <input
                                type="time"
                                className="input w-32"
                                defaultValue="17:00"
                            />
                        </div>
                    ))}
                </div>
            </Section>

            {/* Save Button */}
            <div className="flex items-center gap-4">
                <button
                    onClick={handleSave}
                    className="btn btn-primary"
                >
                    Save Changes
                </button>
                {saved && (
                    <span className="text-green-400 animate-fadeIn">
                        ✓ Settings saved
                    </span>
                )}
            </div>
        </div>
    )
}
