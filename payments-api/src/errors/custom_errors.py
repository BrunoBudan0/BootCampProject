from errors import QIException


# Os erros de regra de negócio DESTE serviço moram aqui: uma classe por
# recusa, cada uma com o código da tabela de rotas da RFC (QIT002xxx).
# Os erros que toda API tem (QIT000xxx) já estão em base_error.py.
#
# O formato de cada classe é o do template: code, title, http_status,
# description (inglês) e translation (português). Código repetido
# derruba a API na subida, de propósito (error_verification).
