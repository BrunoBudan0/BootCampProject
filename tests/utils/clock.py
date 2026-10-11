"""A data de hoje como as APIs a enxergam: em America/Sao_Paulo.

O fuso é fixo em UTC-3 (o Brasil não tem horário de verão desde 2019),
porque a máquina que roda os testes pode estar em qualquer fuso e nem
sempre tem a base de fusos instalada. Com date.today(), um Linux em UTC
acharia que já é amanhã entre 21h e meia-noite de São Paulo.
"""

from datetime import date, datetime, timedelta, timezone

SAO_PAULO_OFFSET = timezone(timedelta(hours=-3))


def now_in_sao_paulo() -> datetime:
    return datetime.now(SAO_PAULO_OFFSET)


def today_in_sao_paulo() -> date:
    return now_in_sao_paulo().date()
