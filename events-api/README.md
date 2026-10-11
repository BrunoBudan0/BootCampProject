# API de Eventos

Guarda a regra de negócio da feira: eventos, stands, credenciais, produtos,
compras, tarifa e cashback. O dinheiro mora na API de Pagamentos; esta API
decide **quanto** e **por quê**, e pede a Pagamentos que mova.

Porta `3002`. Toda rota exige `INTERNAL-TOKEN` (só o Gateway chama) e recebe
quem está chamando em `X-User-Id` e `X-User-Type` (`attendee`, `organizer`, `company`).

## Rotas

| Rota | Quem | O que faz |
|---|---|---|
| `POST /events` | organizador | Cria o evento com tarifa e cashback iniciais e abre as contas fee e external |
| `GET /events` · `GET /events/{id}` | todos | Lista paginada e detalhe com as taxas vigentes |
| `POST /events/{id}/companies` | organizador do evento | Monta o stand e abre a conta dele |
| `POST /events/{id}/attendees` | público | Emite a credencial e abre a conta dela |
| `PUT /events/{id}/fee-rate` · `PUT /events/{id}/cashback-rate` | organizador do evento | Nova versão da taxa, com justificativa |
| `GET /events/{id}/cashback-rates` | quem participa | Histórico do cashback |
| `POST /events/{id}/cash-recharges` | organizador do evento | Recarga em espécie na credencial · idempotente |
| `GET /events/{id}/fee-charges` | organizador do evento | Auditoria da tarifa: cada cobrança e devolução |
| `GET /events/{id}/reconciliation` | organizador do evento | Fechamento do caixa do evento |
| `PUT /event-attendees/{id}/block` | organizador do evento | Bloqueia ou libera credencial e conta juntas |
| `POST /products` · `PUT /products/{id}` | empresa do stand | Cadastro e edição |
| `GET /products` · `GET /products/{id}` | todos | Vitrine (`name`) e scanner (`barcode`) |
| `POST /purchases` | público | Compra pelo app · idempotente |
| `GET /purchases/{id}` | comprador, stand, organizador | Comprovante |
| `POST /purchases/{id}/refund` | comprador, stand, organizador | Estorno |

## As garantias da compra

- **Nunca vende o que não tem.** O estoque baixa num único `UPDATE ... WHERE stock >= quantidade`.
  Com 20 pessoas comprando as 5 últimas unidades ao mesmo tempo, exatamente 5 compras passam.
- **Nunca cobra duas vezes.** A compra é gravada `pending` **antes** de chamar Pagamentos, com a chave
  `purchase:{id}`. Reenvio, clique duplo ou resposta perdida devolvem a mesma compra.
- **Nenhuma transação de banco fica aberta durante uma chamada HTTP.**
- **Sem deadlock.** O carrinho é ordenado pelo id do produto, e todas as compras travam as linhas na mesma ordem.
- **Teto de R$ 100 mil por perna.** Preço de produto e recarga em espécie até `10000000` centavos; compra com
  total acima disso é recusada antes de chamar Pagamentos (`422 QIT002039`), com o estoque devolvido.
- **Contrato com Pagamentos.** Conta de usuário leva `holder_type` (`company` no stand, `attendee` na credencial);
  as chaves são `acct:{evento}:{fee|external|dono}` (até 80 caracteres), `purchase:{id}`, `refund:{id}` e `cash:{...}`;
  as transferências vão sem `type`; o `X-Request-ID` da requisição segue em toda chamada a outro serviço.
- **Dinheiro só em inteiros.** Tarifa e cashback são `total × bps // 10000`, sempre para baixo, o que
  garante `cashback ≤ tarifa ≤ total`.

Resposta de Pagamentos | O que acontece
---|---
andou (200/201) | `paid`, e a tarifa vai para `fee_charge`
recusou (4xx) | `canceled`, e o estoque volta
não respondeu (timeout/5xx) | segue `pending`; o reenvio ou a rotina resolve

## Rotina de compras pendentes

Roda junto com a API (`workers/pending_purchases.py`). A cada `PENDING_RETRY_SECONDS` (padrão 30, `0`
desliga) pede de novo a Pagamentos, com a mesma chave, as compras `pending`. Se continuar sem resposta
depois de `PENDING_ALERT_SECONDS` (padrão 300), grava `PURCHASE_OUTCOME_UNKNOWN`.

## Logs críticos

Gravados em `critical_log_event`, numa sessão própria, para não sumirem com o rollback da requisição:
`INTERNAL_CALL_REJECTED`, `UNEXPECTED_ERROR`, `ORPHAN_ACCOUNT`, `CREDENTIAL_BLOCK_CHANGED`,
`STOCK_CHECK_TRIGGERED`, `PURCHASE_OUTCOME_UNKNOWN` e `RECONCILIATION_MISMATCH`.

## Camadas

```
schemas/       formato do JSON aceito
resources/     a porta HTTP: lê a requisição e escolhe o status
controllers/   a regra de negócio e o commit
repositories/  o único lugar com SQL
connectors/    Usuários e Pagamentos
utils/purchase_math.py   o cálculo da compra e as pernas, com o type de cada uma
workers/       a rotina de compras pendentes
```

## Testes

```powershell
pytest tests/events -v          # pela API, com o docker compose de pé
```

Os testes são caixa-preta: falam só por HTTP e não importam nada de `src/`.

Os testes de compra dependem das rotas internas de Usuários e Pagamentos.
