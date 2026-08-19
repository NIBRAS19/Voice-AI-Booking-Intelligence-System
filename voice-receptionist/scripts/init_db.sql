-- ============================================
-- Voice Receptionist Database Schema
-- Run this to initialize the database
-- ============================================

-- Enable required extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS btree_gist;
CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- ============================================
-- BUSINESSES
-- ============================================
CREATE TABLE IF NOT EXISTS businesses (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name VARCHAR(255) NOT NULL,
    timezone VARCHAR(50) NOT NULL DEFAULT 'UTC',
    phone_number VARCHAR(20),
    email VARCHAR(255),
    settings JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_businesses_phone ON businesses(phone_number);

-- ============================================
-- USERS (CALLERS/CUSTOMERS)
-- ============================================
CREATE TABLE IF NOT EXISTS users (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    business_id UUID NOT NULL REFERENCES businesses(id) ON DELETE CASCADE,
    email VARCHAR(255),
    phone VARCHAR(20) NOT NULL,
    name VARCHAR(255),
    preferred_contact VARCHAR(20) DEFAULT 'sms',
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    
    CONSTRAINT unique_phone_per_business UNIQUE(business_id, phone)
);

CREATE INDEX IF NOT EXISTS idx_users_phone ON users(phone);
CREATE INDEX IF NOT EXISTS idx_users_business ON users(business_id);

-- ============================================
-- ADMIN USERS
-- ============================================
CREATE TABLE IF NOT EXISTS admin_users (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    business_id UUID NOT NULL REFERENCES businesses(id) ON DELETE CASCADE,
    email VARCHAR(255) NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    name VARCHAR(255),
    role VARCHAR(50) DEFAULT 'manager',
    notification_preferences JSONB DEFAULT '{"sms": true, "email": true, "push": true}',
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_admin_email ON admin_users(email);

-- ============================================
-- SERVICES
-- ============================================
CREATE TABLE IF NOT EXISTS services (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    business_id UUID NOT NULL REFERENCES businesses(id) ON DELETE CASCADE,
    name VARCHAR(100) NOT NULL,
    description TEXT,
    duration_minutes INT NOT NULL,
    buffer_minutes INT DEFAULT 0,
    price DECIMAL(10,2),
    is_active BOOLEAN DEFAULT true,
    requires_approval BOOLEAN DEFAULT false,
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_services_business ON services(business_id);

-- ============================================
-- RESOURCES
-- ============================================
CREATE TABLE IF NOT EXISTS resources (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    business_id UUID NOT NULL REFERENCES businesses(id) ON DELETE CASCADE,
    name VARCHAR(255) NOT NULL,
    type VARCHAR(50) NOT NULL,
    is_active BOOLEAN DEFAULT true,
    metadata JSONB DEFAULT '{}'
);

-- ============================================
-- WORKING HOURS
-- ============================================
CREATE TABLE IF NOT EXISTS working_hours (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    business_id UUID NOT NULL REFERENCES businesses(id) ON DELETE CASCADE,
    resource_id UUID REFERENCES resources(id) ON DELETE CASCADE,
    day_of_week INT NOT NULL CHECK (day_of_week >= 0 AND day_of_week <= 6),
    start_time TIME NOT NULL,
    end_time TIME NOT NULL,
    is_active BOOLEAN DEFAULT true,
    
    CONSTRAINT valid_time_range CHECK (end_time > start_time)
);

CREATE INDEX IF NOT EXISTS idx_working_hours_business ON working_hours(business_id, day_of_week);

-- ============================================
-- BOOKINGS
-- ============================================
CREATE TABLE IF NOT EXISTS bookings (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    business_id UUID NOT NULL REFERENCES businesses(id) ON DELETE CASCADE,
    user_id UUID REFERENCES users(id) ON DELETE SET NULL,
    service_id UUID REFERENCES services(id) ON DELETE SET NULL,
    resource_id UUID REFERENCES resources(id) ON DELETE SET NULL,
    
    start_time TIMESTAMPTZ NOT NULL,
    end_time TIMESTAMPTZ NOT NULL,
    
    status VARCHAR(20) DEFAULT 'pending_approval',
    source VARCHAR(50) DEFAULT 'voice_ai',
    
    conversation_id UUID,
    approval_admin_id UUID REFERENCES admin_users(id),
    approved_at TIMESTAMPTZ,
    
    customer_notes TEXT,
    admin_notes TEXT,
    metadata JSONB DEFAULT '{}',
    
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    
    CONSTRAINT valid_booking_time CHECK (end_time > start_time)
);

-- CRITICAL: Prevent overlapping bookings per resource
ALTER TABLE bookings DROP CONSTRAINT IF EXISTS no_overlapping_bookings;
ALTER TABLE bookings 
ADD CONSTRAINT no_overlapping_bookings 
EXCLUDE USING gist (
    business_id WITH =,
    resource_id WITH =,
    tstzrange(start_time, end_time) WITH &&
) WHERE (status NOT IN ('cancelled', 'no_show'));

CREATE INDEX IF NOT EXISTS idx_bookings_business_time ON bookings(business_id, start_time);
CREATE INDEX IF NOT EXISTS idx_bookings_user ON bookings(user_id);
CREATE INDEX IF NOT EXISTS idx_bookings_status ON bookings(status);
CREATE INDEX IF NOT EXISTS idx_bookings_pending ON bookings(business_id) WHERE status = 'pending_approval';

-- ============================================
-- ORDERS
-- ============================================
CREATE TABLE IF NOT EXISTS orders (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    business_id UUID NOT NULL REFERENCES businesses(id) ON DELETE CASCADE,
    user_id UUID REFERENCES users(id),
    
    status VARCHAR(20) DEFAULT 'pending_approval',
    total_amount DECIMAL(10,2),
    
    items JSONB NOT NULL,
    
    conversation_id UUID,
    approval_admin_id UUID REFERENCES admin_users(id),
    approved_at TIMESTAMPTZ,
    
    customer_notes TEXT,
    admin_notes TEXT,
    metadata JSONB DEFAULT '{}',
    
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_orders_business ON orders(business_id);

-- ============================================
-- SERVICE REQUESTS
-- ============================================
CREATE TABLE IF NOT EXISTS service_requests (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    business_id UUID NOT NULL REFERENCES businesses(id) ON DELETE CASCADE,
    user_id UUID REFERENCES users(id),
    
    request_type VARCHAR(100) NOT NULL,
    description TEXT,
    priority VARCHAR(20) DEFAULT 'normal',
    status VARCHAR(20) DEFAULT 'pending',
    
    conversation_id UUID,
    assigned_to UUID REFERENCES admin_users(id),
    
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- ============================================
-- CONVERSATION SESSIONS
-- ============================================
CREATE TABLE IF NOT EXISTS conversation_sessions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    business_id UUID NOT NULL REFERENCES businesses(id) ON DELETE CASCADE,
    user_id UUID REFERENCES users(id),
    
    channel VARCHAR(20) NOT NULL,
    phone_number VARCHAR(20),
    
    started_at TIMESTAMPTZ DEFAULT NOW(),
    ended_at TIMESTAMPTZ,
    duration_seconds INT,
    
    status VARCHAR(20) DEFAULT 'active',
    
    current_intent VARCHAR(50),
    intent_confidence DECIMAL(3,2),
    final_outcome VARCHAR(100),
    
    transferred_to_human BOOLEAN DEFAULT false,
    transfer_reason VARCHAR(255),
    
    slots_collected JSONB DEFAULT '{}',
    
    booking_id UUID REFERENCES bookings(id),
    order_id UUID REFERENCES orders(id),
    request_id UUID REFERENCES service_requests(id),
    
    metadata JSONB DEFAULT '{}',
    recording_path VARCHAR(500)
);

CREATE INDEX IF NOT EXISTS idx_sessions_business ON conversation_sessions(business_id);
CREATE INDEX IF NOT EXISTS idx_sessions_user ON conversation_sessions(user_id);
CREATE INDEX IF NOT EXISTS idx_sessions_date ON conversation_sessions(started_at);

-- ============================================
-- CONVERSATION TURNS
-- ============================================
CREATE TABLE IF NOT EXISTS conversation_turns (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    session_id UUID NOT NULL REFERENCES conversation_sessions(id) ON DELETE CASCADE,
    
    turn_number INT NOT NULL,
    role VARCHAR(20) NOT NULL,
    content TEXT NOT NULL,
    
    intent VARCHAR(50),
    entities JSONB DEFAULT '{}',
    confidence DECIMAL(3,2),
    
    audio_duration_ms INT,
    processing_time_ms INT,
    
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_turns_session ON conversation_turns(session_id, turn_number);

-- ============================================
-- ADMIN ACTION LOGS (AUDIT)
-- ============================================
CREATE TABLE IF NOT EXISTS admin_action_logs (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    admin_id UUID NOT NULL REFERENCES admin_users(id),
    business_id UUID NOT NULL REFERENCES businesses(id),
    
    action_type VARCHAR(50) NOT NULL,
    entity_type VARCHAR(50) NOT NULL,
    entity_id UUID NOT NULL,
    
    previous_state JSONB,
    new_state JSONB,
    
    notes TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_action_logs_entity ON admin_action_logs(entity_type, entity_id);

-- ============================================
-- NOTIFICATION LOGS
-- ============================================
CREATE TABLE IF NOT EXISTS notification_logs (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    business_id UUID NOT NULL REFERENCES businesses(id),
    user_id UUID REFERENCES users(id),
    
    channel VARCHAR(20) NOT NULL,
    recipient VARCHAR(255) NOT NULL,
    template VARCHAR(100),
    content TEXT,
    
    status VARCHAR(20) DEFAULT 'pending',
    external_id VARCHAR(255),
    
    error_message TEXT,
    sent_at TIMESTAMPTZ,
    delivered_at TIMESTAMPTZ,
    
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_notification_logs_user ON notification_logs(user_id);

-- ============================================
-- SEED DATA (Demo Business)
-- ============================================
INSERT INTO businesses (id, name, timezone, phone_number, settings) VALUES
    ('11111111-1111-1111-1111-111111111111', 'Demo Business', 'UTC', '+15551234567', 
     '{"greeting": "Thank you for calling Demo Business! How can I help you today?", "ai_disclosure": true}')
ON CONFLICT DO NOTHING;

-- Demo admin user (password: admin123)
-- Using pgcrypto to generate bcrypt hash
INSERT INTO admin_users (id, business_id, email, password_hash, name, role) VALUES
    ('22222222-2222-2222-2222-222222222222', '11111111-1111-1111-1111-111111111111',
     'admin@demo.com', crypt('admin123', gen_salt('bf')), 
     'Admin User', 'owner')
ON CONFLICT DO NOTHING;

-- Demo services
INSERT INTO services (id, business_id, name, duration_minutes, price, requires_approval) VALUES
    ('22222222-2222-2222-2222-222222222222', '11111111-1111-1111-1111-111111111111', 'Consultation', 30, 50.00, true),
    ('33333333-3333-3333-3333-333333333333', '11111111-1111-1111-1111-111111111111', 'Standard Service', 60, 100.00, false),
    ('44444444-4444-4444-4444-444444444444', '11111111-1111-1111-1111-111111111111', 'Premium Service', 90, 150.00, true)
ON CONFLICT DO NOTHING;

-- Demo working hours (Mon-Fri 9-5)
INSERT INTO working_hours (business_id, day_of_week, start_time, end_time) VALUES
    ('11111111-1111-1111-1111-111111111111', 1, '09:00', '17:00'),
    ('11111111-1111-1111-1111-111111111111', 2, '09:00', '17:00'),
    ('11111111-1111-1111-1111-111111111111', 3, '09:00', '17:00'),
    ('11111111-1111-1111-1111-111111111111', 4, '09:00', '17:00'),
    ('11111111-1111-1111-1111-111111111111', 5, '09:00', '17:00')
ON CONFLICT DO NOTHING;

COMMIT;
