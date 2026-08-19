-- Audit Logs Table Migration

CREATE TABLE IF NOT EXISTS audit_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    action VARCHAR(100) NOT NULL,
    actor_id UUID,          -- Nullable (system actions)
    resource_type VARCHAR(50),
    resource_id UUID,
    details TEXT,           -- JSON string
    status VARCHAR(20) DEFAULT 'success',
    ip_address VARCHAR(45),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_audit_action ON audit_logs(action);
CREATE INDEX IF NOT EXISTS idx_audit_actor ON audit_logs(actor_id);
CREATE INDEX IF NOT EXISTS idx_audit_created_at ON audit_logs(created_at);

-- Comments
COMMENT ON TABLE audit_logs IS 'Tracks security and compliance events';
