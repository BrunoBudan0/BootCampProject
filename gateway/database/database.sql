-- Banco do API Gateway
-- mudou algo aqui? docker compose down -v e sobe de novo

-- session: guarda o hash do token, nunca o token
CREATE TABLE session (
    id          BIGSERIAL PRIMARY KEY,
    token_hash  CHAR(64)    NOT NULL,
    user_id     UUID        NOT NULL,                    -- REF usuários
    user_type   VARCHAR(20) NOT NULL CHECK (user_type IN ('attendee', 'organizer', 'company')),
    expires_at  TIMESTAMPTZ NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_session_token_hash UNIQUE (token_hash),
    CONSTRAINT ck_session_token_hash CHECK (token_hash ~ '^[0-9a-f]{64}$'),
    CONSTRAINT ck_session_expires CHECK (expires_at > created_at)
);
CREATE INDEX ix_session_user ON session (user_id);
