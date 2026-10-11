# API Gateway

A única porta exposta (porta `3000`). App e painel mandam o `INTERNAL-TOKEN` do cliente
(`CLIENT_INTERNAL_TOKEN`) e, depois do login, o `AUTH-TOKEN`.

| Rota | Sessão | Vai para |
|---|---|---|
| `POST /auth/login` | não | Usuários (`/internal/login`); devolve `token`, `user_id`, `user_type`, `expires_at` |
| `POST /attendees` · `/organizers` · `/companies` | não | Usuários |
| `PUT /webhooks/pix/{id}` | não, e sem `INTERNAL-TOKEN` (a assinatura autentica) | Pagamentos |
| `GET /me` | sim | Usuários |
| `/events…` · `/event-attendees…` · `/products…` · `/purchases…` | sim | Eventos |
| `/accounts…` · `/transactions/{id}` · `/transfers` · `/recharges` | sim | Pagamentos |

- **Sessão:** o token é aleatório (`secrets.token_urlsafe`) e só aparece na resposta do login; o banco guarda o
  SHA-256 dele. Vale `SESSION_TTL_HOURS` (padrão 12). Sem token, token inventado ou vencido: `401 QIT002002`.
- **Quem é quem vem da sessão:** o `X-User-Id` e o `X-User-Type` que o app mandar são descartados.
- **`/internal/*` não tem rota aqui:** de fora, responde `404`.
- **`X-Request-ID`** segue para a API chamada e volta na resposta.
- **Limite de tentativas** (`429 QIT002003`), em memória, por janela deslizante: login 10 por e-mail a cada 5 min e
  120 por IP por minuto; cadastro 60 por IP por minuto; webhook 120 por IP por minuto. Todos ajustáveis por
  variável de ambiente (`LOGIN_PER_EMAIL_LIMIT`, `LOGIN_PER_IP_LIMIT`, `SIGNUP_PER_IP_LIMIT`, `WEBHOOK_PER_IP_LIMIT`).
- **API chamada fora do ar:** `502 QIT002031`.

O corpo é repassado em bytes, sem reinterpretar o JSON: é isso que mantém válida a assinatura do webhook Pix.
