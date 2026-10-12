"""Preparação que vale para a suíte inteira.

O pytest lê este arquivo sozinho, antes de importar qualquer teste. Aqui
ele só carrega o .env da raiz, se existir: assim, quem trocou uma porta
ou um token no .env roda os testes contra os mesmos valores que o
docker compose usou. Sem .env, valem os padrões, que são os mesmos do compose.
"""

from pathlib import Path

import pytest

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]

load_dotenv(ROOT / ".env")


def pytest_collection_modifyitems(items):
    # com -n, os testes rodam em paralelo; os que programam o Mockserver
    # dividem o mesmo servidor e por isso ficam juntos, um depois do outro
    for item in items:
        if "mockserver" in vars(item.module):
            item.add_marker(pytest.mark.xdist_group("mockserver"))
