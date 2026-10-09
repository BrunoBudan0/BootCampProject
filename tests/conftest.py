"""Preparação que vale para a suíte inteira.

O pytest lê este arquivo sozinho, antes de importar qualquer teste. Aqui
ele só carrega o .env da raiz, se existir: assim, quem trocou uma porta
ou um token no .env roda os testes contra os mesmos valores que o
docker compose usou. Sem .env, valem os padrões — os mesmos do compose.
"""

from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]

load_dotenv(ROOT / ".env")
