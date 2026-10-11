-- ============================================================
-- Banco da API de Pagamentos
-- ============================================================
-- Tabelas deste banco:
--   account, transaction, pix_charge, critical_log_payment
--
-- Combinado do time sobre chaves:
--   - `id` interno (BIGSERIAL) para PK e FK DENTRO deste banco; ele
--     nunca sai na resposta (R5);
--   - uma coluna `<tabela>_key` UUID para tudo o que sai da API;
--   - event_id, holder_id e user_id chegam de outro serviço: são UUID,
--     sem FK. Quem garante que existem é a API que os mandou.
--
-- Dinheiro é BIGINT em centavos (R6). Nada é apagado (R4): os gatilhos
-- do fim do arquivo recusam DELETE e TRUNCATE.
--
-- Este arquivo roda UMA vez, quando o volume do banco nasce. Mudou o
-- arquivo? `docker compose down -v` e suba de novo.


-- ============================================================
-- account
-- ============================================================
-- kind:
--   user      tem dono (holder_id): a credencial do público ou o stand
--             da empresa. NUNCA fica negativa. holder_type diz qual dos
--             dois: attendee (credencial) ou company (stand). Só
--             credencial transfere, e só para outra credencial.
--   fee       uma por evento: recebe a tarifa e paga o cashback.
--   external  uma por evento: a contrapartida do dinheiro que entra de
--             fora. Fica negativa de propósito: o módulo dela é quanto
--             dinheiro entrou.
-- As contas do sistema (fee e external) não têm dono: nenhuma rota
-- pública de Pagamentos as alcança. O organizador as vê pela
-- conciliação, pedida pela API de Eventos.
--
-- balance_cents é o saldo atual, guardado para que o débito seja um
-- UPDATE condicional atômico. A verdade é o histórico de transações; a
-- conciliação confere que os dois batem.
CREATE TABLE account(
    id                      BIGSERIAL PRIMARY KEY,
    account_key             UUID NOT NULL,
    event_id                UUID NOT NULL,          -- REF: API de Eventos
    holder_id               UUID,                   -- REF: API de Usuários
    holder_type             VARCHAR(10),
    kind                    VARCHAR(10) NOT NULL,
    balance_cents           BIGINT NOT NULL DEFAULT 0,
    blocked                 BOOLEAN NOT NULL DEFAULT FALSE,
    idempotency_key         VARCHAR(80) NOT NULL,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT uq_account_key UNIQUE (account_key),
    -- A mesma credencial ou o mesmo stand não ganham duas contas: o
    -- reenvio com a mesma chave encontra a conta que já existe.
    CONSTRAINT uq_account_idempotency_key UNIQUE (idempotency_key),
    CONSTRAINT ck_account_kind CHECK (kind IN ('user', 'fee', 'external')),
    -- Conta de usuário tem dono, e o tipo dele; conta do sistema não tem.
    CONSTRAINT ck_account_holder CHECK ((kind = 'user') = (holder_id IS NOT NULL)),
    CONSTRAINT ck_account_holder_type_presence CHECK ((kind = 'user') = (holder_type IS NOT NULL)),
    CONSTRAINT ck_account_holder_type CHECK (holder_type IN ('attendee', 'company')),
    -- A última linha de defesa: mesmo que o UPDATE condicional falhe, o
    -- banco recusa saldo negativo em conta de usuário.
    CONSTRAINT ck_account_user_balance CHECK (kind <> 'user' OR balance_cents >= 0)
);

CREATE INDEX ix_account_event ON account (event_id);
CREATE INDEX ix_account_holder ON account (holder_id);

-- Uma conta fee e uma external por evento, e uma conta por dono em cada
-- evento. A chave de idempotência sozinha não garante isso: Eventos
-- reenviando com OUTRA chave abriria uma segunda conta.
CREATE UNIQUE INDEX uq_account_system_kind_per_event ON account (event_id, kind) WHERE kind <> 'user';
CREATE UNIQUE INDEX uq_account_holder_per_event ON account (event_id, holder_id) WHERE kind = 'user';


-- ============================================================
-- transaction
-- ============================================================
-- Tira de uma conta e põe em outra. Não existe tabela de lançamentos:
-- origem e destino na própria linha já são a partida dobrada.
--
-- Várias transações nascem juntas sob a mesma idempotency_key (a compra
-- são três: leg 1, 2 e 3). Por isso a chave é única JUNTO com a leg, e
-- não sozinha.
--
-- status:
--   pending   Pix esperando o webhook; nenhum saldo mexeu
--   settled   o dinheiro andou
--   reversed  foi estornada (o estorno é OUTRA transação, que aponta
--             para esta em reverses_transaction_id)
--   canceled  Pix expirado ou recarga recusada; nenhum saldo mexeu
-- As únicas mudanças permitidas estão no gatilho do fim do arquivo.
--
-- settled_at é o momento em que o dinheiro andou. Quem preenche é o
-- gatilho, com o relógio de quando a linha é escrita (depois da trava
-- das contas), e ninguém reescreve. O extrato ordena e soma por ele, e
-- não por created_at: um Pix pedido antes e pago depois de uma
-- transferência entra no extrato depois dela.
CREATE TABLE transaction(
    id                      BIGSERIAL PRIMARY KEY,
    transaction_key         UUID NOT NULL,
    idempotency_key         VARCHAR(80) NOT NULL,
    leg                     SMALLINT NOT NULL,
    source_account_id       BIGINT NOT NULL REFERENCES account (id),
    destination_account_id  BIGINT NOT NULL REFERENCES account (id),
    amount_cents            BIGINT NOT NULL,
    payment_method          VARCHAR(10) NOT NULL,
    status                  VARCHAR(10) NOT NULL,
    reverses_transaction_id BIGINT REFERENCES transaction (id),
    created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    settled_at              TIMESTAMPTZ,

    CONSTRAINT uq_transaction_key UNIQUE (transaction_key),
    -- Quem fecha a janela da idempotência: duas requisições com a mesma
    -- chave chegando juntas, só uma consegue gravar.
    CONSTRAINT uq_transaction_idempotency_leg UNIQUE (idempotency_key, leg),
    -- A mesma transação não é estornada duas vezes.
    CONSTRAINT uq_transaction_reversal UNIQUE (reverses_transaction_id),
    CONSTRAINT ck_transaction_leg CHECK (leg >= 1),
    CONSTRAINT ck_transaction_amount CHECK (amount_cents > 0),
    CONSTRAINT ck_transaction_accounts CHECK (source_account_id <> destination_account_id),
    CONSTRAINT ck_transaction_method CHECK (payment_method IN ('balance', 'card', 'pix', 'cash')),
    CONSTRAINT ck_transaction_status CHECK (status IN ('pending', 'settled', 'reversed', 'canceled')),
    CONSTRAINT ck_transaction_settled_at CHECK ((status IN ('settled', 'reversed')) = (settled_at IS NOT NULL))
);

-- O extrato e a conciliação procuram por conta, na ordem em que o
-- dinheiro andou.
CREATE INDEX ix_transaction_source ON transaction (source_account_id, settled_at);
CREATE INDEX ix_transaction_destination ON transaction (destination_account_id, settled_at);


-- ============================================================
-- pix_charge
-- ============================================================
-- O que o provedor de Pix devolveu ao criar a cobrança. Existe para o
-- reenvio da mesma recarga devolver o MESMO copia e cola (200 replay),
-- sem pedir uma segunda cobrança ao provedor. Fica fora de transaction
-- para que a transação continue só com origem, destino, valor e método.
CREATE TABLE pix_charge(
    id                      BIGSERIAL PRIMARY KEY,
    transaction_id          BIGINT NOT NULL REFERENCES transaction (id),
    provider_charge_id      VARCHAR(80) NOT NULL,
    copy_paste              TEXT NOT NULL,
    expires_at              TIMESTAMPTZ NOT NULL,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT uq_pix_charge_transaction UNIQUE (transaction_id)
);


-- ============================================================
-- critical_log_payment
-- ============================================================
-- Só o que é crítico: dinheiro possivelmente errado, fraude ou acesso
-- indevido. Todo o resto vai para o log comum (stdout).
--
-- O type é uma lista fechada: tipo novo exige mudar este arquivo. Cada
-- type exige os campos que o explicam — um PIX_AMOUNT_MISMATCH sem
-- transação e sem valor é recusado pelo próprio banco.
--
-- É gravado numa conexão própria, com COMMIT próprio: o rollback da
-- operação que falhou não apaga o registro de por que ela falhou. Por
-- isso as FKs só podem apontar para linhas que já existiam antes da
-- requisição.
--
-- Nenhum log guarda token, senha, token de cartão, documento ou e-mail.
CREATE TABLE critical_log_payment(
    id                      BIGSERIAL PRIMARY KEY,
    request_id              VARCHAR(64),
    type                    VARCHAR(40) NOT NULL,
    route                   VARCHAR(120),
    http_status             SMALLINT,
    error_code              CHAR(9),
    user_id                 UUID,                   -- REF: API de Usuários
    account_id              BIGINT REFERENCES account (id),
    transaction_id          BIGINT REFERENCES transaction (id),
    idempotency_key         VARCHAR(80),
    amount_cents            BIGINT,
    description             VARCHAR(500),
    created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT ck_critical_log_payment_type CHECK (type IN (
        'INTERNAL_CALL_REJECTED',
        'BALANCE_CHECK_TRIGGERED',
        'CARD_AUTHORIZED_NOT_CREDITED',
        'CARD_OUTCOME_UNKNOWN',
        'PIX_INVALID_SIGNATURE',
        'PIX_AMOUNT_MISMATCH',
        'UNEXPECTED_ERROR'
    )),
    CONSTRAINT ck_critical_log_payment_error_code CHECK (error_code IS NULL OR error_code ~ '^QIT[0-9]{6}$'),
    CONSTRAINT ck_critical_log_payment_request_id CHECK (request_id IS NULL OR request_id ~ '^[A-Za-z0-9_-]{1,64}$'),
    CONSTRAINT ck_critical_log_payment_fields CHECK (
        CASE type
            WHEN 'INTERNAL_CALL_REJECTED'       THEN http_status = 403
            WHEN 'BALANCE_CHECK_TRIGGERED'      THEN account_id IS NOT NULL
            WHEN 'CARD_AUTHORIZED_NOT_CREDITED' THEN idempotency_key IS NOT NULL AND user_id IS NOT NULL AND amount_cents > 0
            WHEN 'CARD_OUTCOME_UNKNOWN'         THEN idempotency_key IS NOT NULL AND user_id IS NOT NULL AND amount_cents > 0
            WHEN 'PIX_INVALID_SIGNATURE'        THEN http_status = 401
            WHEN 'PIX_AMOUNT_MISMATCH'          THEN transaction_id IS NOT NULL AND amount_cents IS NOT NULL
            WHEN 'UNEXPECTED_ERROR'             THEN http_status = 500
        END
    )
);

CREATE INDEX ix_critical_log_payment_request ON critical_log_payment (request_id);


-- ============================================================
-- Gatilhos: o banco protege o histórico mesmo de quem escreve SQL
-- por fora da API
-- ============================================================

-- Recusa a operação, dizendo em qual tabela.
CREATE FUNCTION reject_change() RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'a tabela % não aceita %', TG_TABLE_NAME, TG_OP;
END;
$$ LANGUAGE plpgsql;

-- Nada é apagado (R4): nem conta, nem transação, nem cobrança, nem log.
CREATE TRIGGER trg_account_no_delete BEFORE DELETE ON account
    FOR EACH ROW EXECUTE FUNCTION reject_change();
CREATE TRIGGER trg_account_no_truncate BEFORE TRUNCATE ON account
    FOR EACH STATEMENT EXECUTE FUNCTION reject_change();

CREATE TRIGGER trg_transaction_no_delete BEFORE DELETE ON transaction
    FOR EACH ROW EXECUTE FUNCTION reject_change();
CREATE TRIGGER trg_transaction_no_truncate BEFORE TRUNCATE ON transaction
    FOR EACH STATEMENT EXECUTE FUNCTION reject_change();

CREATE TRIGGER trg_pix_charge_no_change BEFORE UPDATE OR DELETE ON pix_charge
    FOR EACH ROW EXECUTE FUNCTION reject_change();
CREATE TRIGGER trg_pix_charge_no_truncate BEFORE TRUNCATE ON pix_charge
    FOR EACH STATEMENT EXECUTE FUNCTION reject_change();

-- O log crítico só aceita INSERT. Corrigir um registro é inserir outro.
CREATE TRIGGER trg_critical_log_payment_no_change BEFORE UPDATE OR DELETE ON critical_log_payment
    FOR EACH ROW EXECUTE FUNCTION reject_change();
CREATE TRIGGER trg_critical_log_payment_no_truncate BEFORE TRUNCATE ON critical_log_payment
    FOR EACH STATEMENT EXECUTE FUNCTION reject_change();

-- Numa transação, só o status (e o updated_at) muda, e só por um destes
-- caminhos:
--   pending -> settled | canceled      (pago, recusado ou expirado)
--   settled -> reversed                (foi estornada)
-- Valor, contas, chave e método de uma transação nunca são reescritos:
-- desfazer é uma transação nova no sentido contrário. O settled_at nasce
-- na passagem pending -> settled, e depois disso não muda mais.
CREATE FUNCTION transaction_status_only() RETURNS trigger AS $$
BEGIN
    IF (NEW.transaction_key, NEW.idempotency_key, NEW.leg, NEW.source_account_id,
        NEW.destination_account_id, NEW.amount_cents, NEW.payment_method,
        NEW.reverses_transaction_id, NEW.created_at, NEW.settled_at)
       IS DISTINCT FROM
       (OLD.transaction_key, OLD.idempotency_key, OLD.leg, OLD.source_account_id,
        OLD.destination_account_id, OLD.amount_cents, OLD.payment_method,
        OLD.reverses_transaction_id, OLD.created_at, OLD.settled_at) THEN
        RAISE EXCEPTION 'transaction % só pode mudar de status', OLD.id;
    END IF;

    IF NEW.status IS DISTINCT FROM OLD.status AND NOT (
        (OLD.status = 'pending' AND NEW.status IN ('settled', 'canceled'))
        OR (OLD.status = 'settled' AND NEW.status = 'reversed')
    ) THEN
        RAISE EXCEPTION 'transaction %: % -> % não é uma transição permitida', OLD.id, OLD.status, NEW.status;
    END IF;

    IF OLD.status = 'pending' AND NEW.status = 'settled' THEN
        NEW.settled_at = clock_timestamp();
    END IF;

    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_transaction_status_only BEFORE UPDATE ON transaction
    FOR EACH ROW EXECUTE FUNCTION transaction_status_only();

-- A transação que já nasce settled ganha o settled_at na hora; qualquer
-- valor mandado pela aplicação é descartado. clock_timestamp(), e não
-- NOW(): NOW() é o começo da transação de banco, que pode ter começado
-- antes de outra que pegou a trava das contas primeiro.
CREATE FUNCTION transaction_settled_at_on_insert() RETURNS trigger AS $$
BEGIN
    NEW.settled_at = CASE WHEN NEW.status = 'settled' THEN clock_timestamp() END;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_transaction_settled_at_on_insert BEFORE INSERT ON transaction
    FOR EACH ROW EXECUTE FUNCTION transaction_settled_at_on_insert();
