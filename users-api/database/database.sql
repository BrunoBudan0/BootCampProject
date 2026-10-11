-- ============================================================
-- Banco da API de Usuários
-- ============================================================
-- Tabelas deste banco: attendee, organizer, company. Uma por tipo
-- de usuário: o UNIQUE de email e de document vale DENTRO de cada
-- tabela, não entre elas. A mesma casa de eventos pode ser organizadora
-- e empresa, com o mesmo CNPJ e o mesmo e-mail.
--
-- Combinado do time sobre chaves:
--   - `id` interno (BIGSERIAL), nunca sai na resposta (R5);
--   - `<tabela>_key` UUID é o que a API devolve, e é ele que o Gateway
--     repassa em X-User-Id e que os outros serviços guardam.
--
-- O e-mail é guardado em minúsculas (o CHECK garante), para que
-- "Ana@X.com" e "ana@x.com" sejam o mesmo e-mail no UNIQUE.
-- A senha é guardada só como hash.
--
-- Este arquivo roda UMA vez, quando o volume do banco nasce. Mudou o
-- arquivo? `docker compose down -v` e `docker compose up -d --build --wait`.


CREATE TABLE attendee(
    id                      BIGSERIAL PRIMARY KEY,
    attendee_key            UUID NOT NULL,
    name                    VARCHAR(255) NOT NULL,
    email                   VARCHAR(255) NOT NULL,
    document                VARCHAR(14) NOT NULL,
    password_hash           VARCHAR(255) NOT NULL,
    birth_date              DATE NOT NULL,
    phone                   VARCHAR(20),
    postal_code             CHAR(9),
    created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT uq_attendee_key UNIQUE (attendee_key),
    CONSTRAINT uq_attendee_email UNIQUE (email),
    CONSTRAINT uq_attendee_document UNIQUE (document),
    CONSTRAINT ck_attendee_email_lowercase CHECK (email = LOWER(email))
);


CREATE TABLE organizer(
    id                      BIGSERIAL PRIMARY KEY,
    organizer_key           UUID NOT NULL,
    name                    VARCHAR(255) NOT NULL,
    email                   VARCHAR(255) NOT NULL,
    document                VARCHAR(18) NOT NULL,
    password_hash           VARCHAR(255) NOT NULL,
    phone                   VARCHAR(20),
    created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT uq_organizer_key UNIQUE (organizer_key),
    CONSTRAINT uq_organizer_email UNIQUE (email),
    CONSTRAINT uq_organizer_document UNIQUE (document),
    CONSTRAINT ck_organizer_email_lowercase CHECK (email = LOWER(email))
);


CREATE TABLE company(
    id                      BIGSERIAL PRIMARY KEY,
    company_key             UUID NOT NULL,
    legal_name              VARCHAR(255) NOT NULL,
    trade_name              VARCHAR(255) NOT NULL,
    email                   VARCHAR(255) NOT NULL,
    document                VARCHAR(18) NOT NULL,
    password_hash           VARCHAR(255) NOT NULL,
    phone                   VARCHAR(20),
    created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT uq_company_key UNIQUE (company_key),
    CONSTRAINT uq_company_email UNIQUE (email),
    CONSTRAINT uq_company_document UNIQUE (document),
    CONSTRAINT ck_company_email_lowercase CHECK (email = LOWER(email))
);
