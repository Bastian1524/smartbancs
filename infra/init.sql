CREATE EXTENSION IF NOT EXISTS "pgcrypto";

CREATE TABLE IF NOT EXISTS accounts (
    id VARCHAR(20) PRIMARY KEY, 
    balance NUMERIC(19,4) NOT NULL CHECK (balance >= 0)
);

CREATE TABLE IF NOT EXISTS transactions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(), 
    from_account VARCHAR(20) NOT NULL, 
    to_account VARCHAR(20) NOT NULL, 
    amount NUMERIC(19,4) NOT NULL, 
    status VARCHAR(20) NOT NULL, 
    idempotency_key VARCHAR(64) UNIQUE NOT NULL, 
    trace_id VARCHAR(36) NOT NULL, 
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Tabla OUTBOX anti-saturación Bancs Legacy (punto 3.2)
CREATE TABLE IF NOT EXISTS outbox_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(), 
    payload JSONB NOT NULL, 
    status VARCHAR(20) DEFAULT 'PENDING',
    processed BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

INSERT INTO accounts (id, balance) VALUES ('ACC001', 10000), ('ACC002', 10000) ON CONFLICT (id) DO NOTHING;