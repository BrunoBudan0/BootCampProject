# Banco de Eventos

Banco de circuito fechado para feiras e eventos. O público carrega saldo numa credencial e compra nos stands pelo app; cada stand tem a própria conta. Toda movimentação passa por contas deste banco, e a soma dos saldos de um evento é sempre zero.

Projeto do Bootcamp QI Tech 2026, de Bruno Budano Mello e Pedro Henrique Mathias Santiago.

A RFC, com as decisões e as alternativas descartadas, está em [`docs/RFC-banco-evento.pdf`](docs/RFC-banco-evento.pdf).

## Arquitetura

Quatro serviços, cada um com o próprio banco Postgres. Nenhum lê o banco do outro: quando um precisa de algo que não é dele, pede por HTTP a uma rota da API dona.

| Serviço | Responsabilidade | Banco | Porta na sua máquina |
|---|---|---|---|
| `gateway` | A única porta de fora: confere o token do app, troca o AUTH-TOKEN pela sessão e repassa a requisição | `gateway-db` (session) | `3000` |
| `users-api` | Público, organizadores e empresas: cadastro e conferência de senha | `users-db` | `127.0.0.1:3001` |
| `events-api` | Regras do evento: stands, credenciais, produtos, compras, tarifa e cashback | `events-db` | `127.0.0.1:3002` |
| `payments-api` | Contas e transações: move dinheiro e não sabe o que foi comprado | `payments-db` | `127.0.0.1:3003` |
| `mockserver` | Faz o papel dos provedores de cartão e Pix | não tem | `127.0.0.1:1080` |

As APIs internas ficam presas a `127.0.0.1` para que os testes de cada uma cheguem direto nela; em produção, só o Gateway publicaria porta. Os detalhes de redes, tokens e timeouts estão comentados no [`docker-compose.yml`](docker-compose.yml).

## Subindo

Precisa só de **Docker** (com o Docker Compose v2). Na raiz do repositório:

```bash
docker compose up -d --build --wait
```

O `--wait` só devolve o terminal quando os 9 containers estão de pé. Para conferir:

```bash
docker compose ps
```

```bash
curl http://localhost:3000/
```

Para desligar, `docker compose down`. Para desligar **e apagar os bancos** (necessário depois de mudar um `database.sql`), `docker compose down -v`.

## Rodando os testes

Os testes rodam na sua máquina, contra o sistema que o compose subiu. Precisa de **Python 3.11+**.

```bash
python -m venv .venv
```

Ative o ambiente virtual (`source .venv/bin/activate` no Linux/Mac, `.venv\Scripts\activate` no Windows) e instale as dependências:

```bash
pip install -r requirements-dev.txt
```

```bash
pytest
```

Os testes são black-box: falam com as APIs só por HTTP e não importam nada de `src/`.

| Pasta | O que testa |
|---|---|
| `tests/test_stack.py` | O ambiente: cada serviço de pé e cada porta só abrindo com o token certo |
| `tests/payments/`, `tests/users/`, `tests/events/` | Cada API sozinha, chamada direto na porta dela |
| `tests/gateway/` | O Gateway: login, sessão, limite de tentativas e roteamento para as APIs |
| `tests/e2e/` | O sistema inteiro, entrando pelo Gateway |

## Se algo falhar

- **Banco desatualizado:** os bancos só são criados quando o volume nasce. Depois de mudar um `database.sql`, ou se aparecer `relation ... does not exist` no log, rode `docker compose down -v` e `docker compose up -d --build --wait`.
- **Máquina lenta:** as APIs esperam até 5 s umas pelas outras. Com a máquina sem memória livre, uma resposta pode passar disso e virar `502 QIT002031`. Rode de novo com menos programas abertos.
- **Tempo esperado:** a suíte inteira tem 375 testes e leva cerca de 2 minutos.

## Estrutura

```
docker-compose.yml     o sistema inteiro: 4 APIs, 4 bancos e o Mockserver
gateway/               cada serviço tem a mesma forma:
users-api/               Dockerfile, requirements.txt,
events-api/              database/ (o database.sql daquele banco)
payments-api/            src/ (as camadas do bootcamp-base-api)
tests/                 a suíte, uma pasta por API e uma para o sistema inteiro
docs/                  a RFC em PDF
```

## Configuração

Nada precisa ser configurado para subir: cada valor tem um padrão no `docker-compose.yml`. Para trocar uma porta ocupada ou um token, copie `.env.example` para `.env` e edite: o compose e os testes leem o mesmo arquivo.
