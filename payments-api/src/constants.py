import os


SERVICE_ROOT = os.path.abspath(os.path.dirname(__file__))

# Onde moram os arquivos de schema — os .json que descrevem o formato
# que cada requisicao precisa ter. Quem le essa pasta e o
# src/utils/schema_handler.py.
SCHEMA_PATH = os.path.join(SERVICE_ROOT, "schemas")

APP_ENV = os.environ.get("APP_ENV", "local")
SERVICE_NAME = os.environ.get("SERVICE_NAME", "payments-api")

DATABASE_URL = os.environ.get("DATABASE_URL")

# Token desta API. Quem chama: o Gateway (recargas, transferencias e
# extrato) e a API de Eventos (rotas /internal/*).
INTERNAL_TOKEN = os.environ.get("INTERNAL_TOKEN")

# Provedores de cartao e Pix (o Mockserver, no ambiente local). O prazo e o
# menor da cadeia: Pagamentos desiste do provedor antes de quem espera por ela.
CARD_PROVIDER_URL = os.environ.get("CARD_PROVIDER_URL")
PIX_PROVIDER_URL = os.environ.get("PIX_PROVIDER_URL")
PROVIDERS_TIMEOUT = int(os.environ.get("PROVIDERS_TIMEOUT", "3"))

# Segredo do HMAC que autentica o webhook do Pix.
PIX_WEBHOOK_SECRET = os.environ.get("PIX_WEBHOOK_SECRET")

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
    "CARD_PROVIDER_URL",
    "PIX_PROVIDER_URL",
    "PIX_WEBHOOK_SECRET",
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
