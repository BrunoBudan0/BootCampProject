"""O sistema está de pé, e cada porta só abre com a chave certa.

Estes testes não sabem nada de regra de negócio: eles provam o que a
Fase 0 montou. A classe inteira roda uma vez para cada serviço — é o
que o `parametrize` faz: a mesma função, quatro vezes, uma linha no
relatório para cada serviço (`test_...[payments-api]`).
"""

import pytest
import requests

from tests.utils.services import ALL_SERVICES, MOCKSERVER_URL

ROUTE_THAT_DOES_NOT_EXIST = "/route-that-does-not-exist"


def a_token_from_another_service(service):
    for other in ALL_SERVICES:
        if other is not service:
            return other.token


@pytest.mark.parametrize("service", ALL_SERVICES, ids=lambda service: service.name)
class TestEveryServiceIsUpAndLocked:
    def test_home_says_which_service_answered(self, service):
        response = service.send("GET", "/", token=None)

        assert response.status_code == 200
        assert response.json()["service"] == service.name

    def test_health_check_answers_without_token(self, service):
        response = service.send("GET", "/health_check", token=None)

        assert response.status_code == 204

    def test_request_without_token_is_refused(self, service):
        """A rota não existe em serviço nenhum: o token é conferido antes de
        o FastAPI procurar a rota, então a porta é testada sem depender de
        regra de negócio."""
        response = service.send("GET", ROUTE_THAT_DOES_NOT_EXIST, token=None)

        assert response.status_code == 403
        assert response.json()["code"] == "QIT000002"

    def test_token_of_another_service_does_not_open_this_one(self, service):
        response = service.send("GET", ROUTE_THAT_DOES_NOT_EXIST, token=a_token_from_another_service(service))

        assert response.status_code == 403
        assert response.json()["code"] == "QIT000002"

    def test_own_token_gets_past_the_door(self, service):
        """O 404 prova que a porta abriu: só depois dela a requisição
        descobre que a rota não existe."""
        response = service.send("GET", ROUTE_THAT_DOES_NOT_EXIST)

        assert response.status_code == 404
        assert response.json()["code"] == "QIT000404"


def test_mockserver_is_up_for_the_tests_to_program_it():
    response = requests.put(f"{MOCKSERVER_URL}/mockserver/status", timeout=15)

    assert response.status_code == 200
