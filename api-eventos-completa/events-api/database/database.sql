-- Banco da API de Eventos
-- mudou algo aqui? docker compose down -v e sobe de novo

-- Gatilho reaproveitado
CREATE OR REPLACE FUNCTION reject_change() RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'Tabela % só aceita INSERT', TG_TABLE_NAME;
END;
$$ LANGUAGE plpgsql;

-- event
CREATE TABLE event (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organizer_id        UUID         NOT NULL,          -- REF usuários
    name                VARCHAR(255) NOT NULL,
    location            VARCHAR(255) NOT NULL,
    description         TEXT,
    active              BOOLEAN      NOT NULL DEFAULT TRUE,
    fee_account_id      UUID         NOT NULL,          -- REF pagamentos
    external_account_id UUID         NOT NULL,          -- REF pagamentos
    created_at          TIMESTAMP    NOT NULL DEFAULT now()
);
CREATE INDEX ix_event_organizer ON event (organizer_id);

-- fee_rate / cashback_rate
CREATE TABLE fee_rate (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    event_id     UUID         NOT NULL REFERENCES event (id),
    rate_bps     INTEGER      NOT NULL CHECK (rate_bps BETWEEN 0 AND 10000),
    reason       VARCHAR(500) NOT NULL CHECK (length(trim(reason)) > 0),
    organizer_id UUID         NOT NULL,                 -- quem decidiu
    created_at   TIMESTAMP    NOT NULL DEFAULT clock_timestamp()
);
CREATE INDEX ix_fee_rate_vigente ON fee_rate (event_id, created_at DESC);
CREATE TRIGGER trg_fee_rate_insert_only
    BEFORE UPDATE OR DELETE ON fee_rate
    FOR EACH ROW EXECUTE FUNCTION reject_change();

CREATE TABLE cashback_rate (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    event_id     UUID         NOT NULL REFERENCES event (id),
    rate_bps     INTEGER      NOT NULL CHECK (rate_bps BETWEEN 0 AND 10000),
    reason       VARCHAR(500) NOT NULL CHECK (length(trim(reason)) > 0),
    organizer_id UUID         NOT NULL,
    created_at   TIMESTAMP    NOT NULL DEFAULT clock_timestamp()
);
CREATE INDEX ix_cashback_rate_vigente ON cashback_rate (event_id, created_at DESC);
CREATE TRIGGER trg_cashback_rate_insert_only
    BEFORE UPDATE OR DELETE ON cashback_rate
    FOR EACH ROW EXECUTE FUNCTION reject_change();

-- event_company
CREATE TABLE event_company (
    id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    event_id   UUID         NOT NULL REFERENCES event (id),
    company_id UUID         NOT NULL,                   -- REF usuários
    stand_name VARCHAR(255) NOT NULL,
    account_id UUID         NOT NULL,                   -- REF pagamentos
    created_at TIMESTAMP    NOT NULL DEFAULT now(),
    CONSTRAINT uq_event_company UNIQUE (event_id, company_id)   -- 409 QIT002012
);

-- event_attendee
CREATE TABLE event_attendee (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    event_id    UUID      NOT NULL REFERENCES event (id),
    attendee_id UUID      NOT NULL,                     -- REF usuários
    account_id  UUID      NOT NULL,                     -- REF pagamentos
    blocked     BOOLEAN   NOT NULL DEFAULT FALSE,
    created_at  TIMESTAMP NOT NULL DEFAULT now(),
    CONSTRAINT uq_event_attendee UNIQUE (event_id, attendee_id) -- 409 QIT002013
);

-- product
CREATE TABLE product (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    event_company_id UUID         NOT NULL REFERENCES event_company (id),
    name             VARCHAR(255) NOT NULL,
    barcode          VARCHAR(64)  NOT NULL,
    price_cents      BIGINT       NOT NULL CHECK (price_cents > 0),   -- 422 QIT002028
    stock            INTEGER,                                          -- NULL = sem controle
    active           BOOLEAN      NOT NULL DEFAULT TRUE,
    created_at       TIMESTAMP    NOT NULL DEFAULT now(),
    CONSTRAINT uq_product_barcode UNIQUE (event_company_id, barcode),  -- 409 QIT002018
    -- se esse CHECK barrar, é bug (STOCK_CHECK_TRIGGERED)
    CONSTRAINT ck_product_stock CHECK (stock IS NULL OR stock >= 0)
);

-- purchase
CREATE TABLE purchase (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    event_attendee_id UUID        NOT NULL REFERENCES event_attendee (id),
    event_company_id  UUID        NOT NULL REFERENCES event_company (id),
    status            VARCHAR(20) NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'paid', 'canceled', 'refunded')),
    total_cents       BIGINT      NOT NULL CHECK (total_cents > 0),
    fee_rate_id       UUID        NOT NULL REFERENCES fee_rate (id),
    fee_cents         BIGINT      NOT NULL CHECK (fee_cents >= 0),
    cashback_rate_id  UUID        NOT NULL REFERENCES cashback_rate (id),
    cashback_cents    BIGINT      NOT NULL CHECK (cashback_cents >= 0),
    idempotency_key   VARCHAR(80) NOT NULL,
    refund_reason     VARCHAR(500),
    refunded_by       UUID,                                -- REF usuários
    refunded_at       TIMESTAMP,
    created_at        TIMESTAMP   NOT NULL DEFAULT now(),
    updated_at        TIMESTAMP   NOT NULL DEFAULT now(),
    CONSTRAINT uq_purchase_idempotency UNIQUE (idempotency_key),     -- 409 QIT002025 / replay
    CONSTRAINT ck_purchase_amounts CHECK (cashback_cents <= fee_cents AND fee_cents <= total_cents),
    -- estorno sempre com motivo, autor e data
    CONSTRAINT ck_purchase_refund CHECK (
        status <> 'refunded' OR
        (refund_reason IS NOT NULL AND refunded_by IS NOT NULL AND refunded_at IS NOT NULL)
    )
);
CREATE INDEX ix_purchase_pending ON purchase (status) WHERE status = 'pending';

-- purchase_product
CREATE TABLE purchase_product (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    purchase_id      UUID         NOT NULL REFERENCES purchase (id),
    product_id       UUID         NOT NULL REFERENCES product (id),
    product_name     VARCHAR(255) NOT NULL,
    unit_price_cents BIGINT       NOT NULL CHECK (unit_price_cents > 0),
    quantity         INTEGER      NOT NULL CHECK (quantity > 0)
);
CREATE INDEX ix_purchase_product_purchase ON purchase_product (purchase_id);

-- fee_charge
CREATE TABLE fee_charge (
    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    purchase_id    UUID        NOT NULL REFERENCES purchase (id),
    fee_rate_id    UUID        NOT NULL REFERENCES fee_rate (id),
    kind           VARCHAR(10) NOT NULL CHECK (kind IN ('charge', 'refund')),
    base_cents     BIGINT      NOT NULL,
    amount_cents   BIGINT      NOT NULL,
    transaction_id UUID,                                 -- REF pagamentos
    created_at     TIMESTAMP   NOT NULL DEFAULT now(),
    CONSTRAINT ck_fee_charge_sign CHECK (
        (kind = 'charge' AND amount_cents > 0) OR
        (kind = 'refund' AND amount_cents < 0)
    ),
    CONSTRAINT uq_fee_charge_purchase_kind UNIQUE (purchase_id, kind)
);
CREATE TRIGGER trg_fee_charge_insert_only
    BEFORE UPDATE OR DELETE ON fee_charge
    FOR EACH ROW EXECUTE FUNCTION reject_change();

-- critical_log_event
CREATE TABLE critical_log_event (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    request_id        VARCHAR(64),
    type              VARCHAR(40)  NOT NULL,
    route             VARCHAR(120),
    http_status       SMALLINT,
    error_code        CHAR(9) CHECK (error_code IS NULL OR error_code ~ '^QIT[0-9]{6}$'),
    user_id           UUID,                                -- REF usuários
    event_id          UUID REFERENCES event (id),
    event_attendee_id UUID REFERENCES event_attendee (id),
    product_id        UUID REFERENCES product (id),
    purchase_id       UUID REFERENCES purchase (id),
    account_id        UUID,                                -- REF pagamentos
    amount_cents      BIGINT,
    description       VARCHAR(500),
    created_at        TIMESTAMP NOT NULL DEFAULT now(),

    CONSTRAINT ck_log_type CHECK (type IN (
        'INTERNAL_CALL_REJECTED', 'UNEXPECTED_ERROR', 'ORPHAN_ACCOUNT',
        'CREDENTIAL_BLOCK_CHANGED', 'STOCK_CHECK_TRIGGERED',
        'PURCHASE_OUTCOME_UNKNOWN', 'RECONCILIATION_MISMATCH'
    )),
    CONSTRAINT ck_log_fields CHECK (
        (type = 'INTERNAL_CALL_REJECTED'   AND http_status = 403) OR
        (type = 'UNEXPECTED_ERROR'         AND http_status = 500) OR
        (type = 'ORPHAN_ACCOUNT'           AND account_id IS NOT NULL) OR
        (type = 'CREDENTIAL_BLOCK_CHANGED' AND event_attendee_id IS NOT NULL AND user_id IS NOT NULL) OR
        (type = 'STOCK_CHECK_TRIGGERED'    AND product_id IS NOT NULL) OR
        (type = 'PURCHASE_OUTCOME_UNKNOWN' AND purchase_id IS NOT NULL) OR
        (type = 'RECONCILIATION_MISMATCH'  AND event_id IS NOT NULL AND amount_cents IS NOT NULL)
    )
);
CREATE TRIGGER trg_critical_log_event_insert_only
    BEFORE UPDATE OR DELETE ON critical_log_event
    FOR EACH ROW EXECUTE FUNCTION reject_change();
CREATE TRIGGER trg_critical_log_event_no_truncate
    BEFORE TRUNCATE ON critical_log_event
    FOR EACH STATEMENT EXECUTE FUNCTION reject_change();
