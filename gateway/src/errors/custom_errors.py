from errors.base_error import QIException


class InvalidCredentials(QIException):
    code = "QIT002001"

    def __init__(self) -> None:
        super().__init__(
            title="Invalid credentials",
            code=self.code,
            http_status=401,
            description="E-mail or password is wrong.",
            translation="E-mail ou senha incorretos.",
        )


class NotAuthenticated(QIException):
    code = "QIT002002"

    def __init__(self) -> None:
        super().__init__(
            title="Not authenticated",
            code=self.code,
            http_status=401,
            description="Missing, invalid or expired AUTH-TOKEN.",
            translation="AUTH-TOKEN ausente, inválido ou expirado.",
        )


class TooManyRequests(QIException):
    code = "QIT002003"

    def __init__(self) -> None:
        super().__init__(
            title="Too many requests",
            code=self.code,
            http_status=429,
            description="Too many attempts. Wait a moment and try again.",
            translation="Tentativas demais. Espere um pouco e tente de novo.",
        )


class UpstreamUnavailable(QIException):
    code = "QIT002031"

    def __init__(self) -> None:
        super().__init__(
            title="Bad gateway",
            code=self.code,
            http_status=502,
            description="A required service did not respond.",
            translation="O serviço chamado não respondeu.",
        )
