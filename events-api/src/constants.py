import os


SERVICE_ROOT = os.path.abspath(os.path.dirname(__file__))

# Onde moram os arquivos de schema — os .json que descrevem o formato
# que cada requisicao precisa ter. Quem le essa pasta e o
# src/utils/schema_handler.py.
SCHEMA_PATH = os.path.join(SERVICE_ROOT, "schemas")

APP_ENV = os.environ.get("APP_ENV", "local")
SERVICE_NAME = os.environ.get("SERVICE_NAME", "events-api")

DATABASE_URL = os.environ.get("DATABASE_URL", "")

# Token desta API. Quem chama: so o Gateway.
INTERNAL_TOKEN = os.environ.get("INTERNAL_TOKEN", "")

# APIs que Eventos chama, cada uma com o proprio token. O prazo e menor que
# o do Gateway e maior que o de Pagamentos com os provedores.
USERS_API_URL = os.environ.get("USERS_API_URL", "")
USERS_API_TOKEN = os.environ.get("USERS_API_TOKEN", "")
USERS_API_TIMEOUT = int(os.environ.get("USERS_API_TIMEOUT", "5"))

PAYMENTS_API_URL = os.environ.get("PAYMENTS_API_URL", "")
PAYMENTS_API_TOKEN = os.environ.get("PAYMENTS_API_TOKEN", "")
PAYMENTS_API_TIMEOUT = int(os.environ.get("PAYMENTS_API_TIMEOUT", "5"))

# teto de cada perna em Pagamentos (R$ 100 mil): Eventos recusa antes de chamar
MAX_TRANSFER_CENTS = 10_000_000

# rotina que resolve compras pending (0 desliga)
PENDING_RETRY_SECONDS = int(os.environ.get("PENDING_RETRY_SECONDS", "30"))
# compra pending há mais que isso, sem resposta de Pagamentos, vira log crítico
PENDING_ALERT_SECONDS = int(os.environ.get("PENDING_ALERT_SECONDS", "300"))

# Rotas públicas: não exigem o header INTERNAL-TOKEN. São as duas que
# precisam responder pra quem ainda não tem token nenhum: a raiz, que
# diz quem é este serviço, e o health check, que o Docker consulta pra
# saber se a API já está de pé.
BYPASS_ENDPOINTS = [
    "/",
    "/health_check",
]

REQUIRED_VARIABLES = [
    "DATABASE_URL",
    "INTERNAL_TOKEN",
    "USERS_API_URL",
    "USERS_API_TOKEN",
    "PAYMENTS_API_URL",
    "PAYMENTS_API_TOKEN",
]


def check_variables():
    missing = []
    for name in REQUIRED_VARIABLES:
        if not globals().get(name):
            missing.append(name)

    if missing:
        raise EnvironmentError(
            f"Faltam variáveis de ambiente: {', '.join(missing)}. "
            "Rodando com 'docker compose up' elas já vêm preenchidas. "
            "Fora do Docker, copie o .env.example para .env."
        )
