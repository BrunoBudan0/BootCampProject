import os


SERVICE_ROOT = os.path.abspath(os.path.dirname(__file__))

# Onde moram os arquivos de schema — os .json que descrevem o formato
# que cada requisicao precisa ter. Quem le essa pasta e o
# src/utils/schema_handler.py.
SCHEMA_PATH = os.path.join(SERVICE_ROOT, "schemas")

APP_ENV = os.environ.get("APP_ENV", "local")
SERVICE_NAME = os.environ.get("SERVICE_NAME", "gateway")

DATABASE_URL = os.environ.get("DATABASE_URL", "")

# Token do sistema cliente (app do publico e painel). Nao entra na rede interna.
INTERNAL_TOKEN = os.environ.get("INTERNAL_TOKEN", "")

# APIs da rede interna, cada uma com o proprio token. O prazo e o maior da
# cadeia: quem esta no meio desiste antes e devolve um erro com nome.
USERS_API_URL = os.environ.get("USERS_API_URL", "")
USERS_API_TOKEN = os.environ.get("USERS_API_TOKEN", "")
USERS_API_TIMEOUT = int(os.environ.get("USERS_API_TIMEOUT", "10"))

EVENTS_API_URL = os.environ.get("EVENTS_API_URL", "")
EVENTS_API_TOKEN = os.environ.get("EVENTS_API_TOKEN", "")
EVENTS_API_TIMEOUT = int(os.environ.get("EVENTS_API_TIMEOUT", "10"))

PAYMENTS_API_URL = os.environ.get("PAYMENTS_API_URL", "")
PAYMENTS_API_TOKEN = os.environ.get("PAYMENTS_API_TOKEN", "")
PAYMENTS_API_TIMEOUT = int(os.environ.get("PAYMENTS_API_TIMEOUT", "10"))

# Rotas públicas: não exigem o header INTERNAL-TOKEN. São as duas que
# precisam responder pra quem ainda não tem token nenhum: a raiz, que
# diz quem é este serviço, e o health check, que o Docker consulta pra
# saber se a API já está de pé.
BYPASS_ENDPOINTS = [
    "/",
    "/health_check",
]

# o provedor Pix não tem o token do app: o webhook se autentica pela assinatura
BYPASS_PREFIXES = ("/webhooks/pix/",)

SESSION_TTL_HOURS = int(os.environ.get("SESSION_TTL_HOURS", "12"))

# tentativas por janela, em segundos (o scrypt de Usuários custa memória e CPU)
LOGIN_PER_EMAIL = (int(os.environ.get("LOGIN_PER_EMAIL_LIMIT", "10")), 300)
LOGIN_PER_IP = (int(os.environ.get("LOGIN_PER_IP_LIMIT", "120")), 60)
SIGNUP_PER_IP = (int(os.environ.get("SIGNUP_PER_IP_LIMIT", "60")), 60)
WEBHOOK_PER_IP = (int(os.environ.get("WEBHOOK_PER_IP_LIMIT", "120")), 60)

REQUIRED_VARIABLES = [
    "DATABASE_URL",
    "INTERNAL_TOKEN",
    "USERS_API_URL",
    "USERS_API_TOKEN",
    "EVENTS_API_URL",
    "EVENTS_API_TOKEN",
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
