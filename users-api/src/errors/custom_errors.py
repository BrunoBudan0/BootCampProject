from errors import QIException


class InvalidCredentials(QIException):
    code = "QIT002001"

    def __init__(self) -> None:
        title = "Invalid credentials"
        http_status = 401
        description = "Email or password is incorrect."
        translation = "E-mail ou senha incorretos."
        super().__init__(title, self.code, http_status, description, translation)


class NotAuthenticated(QIException):
    code = "QIT002002"

    def __init__(self) -> None:
        title = "Not authenticated"
        http_status = 401
        description = "There is no valid user behind this request."
        translation = "Não há um usuário autenticado nesta requisição."
        super().__init__(title, self.code, http_status, description, translation)


class InvalidDocument(QIException):
    code = "QIT002005"

    def __init__(self, document_type) -> None:
        title = "Invalid document"
        http_status = 422
        description = f"The {document_type} check digits do not match."
        translation = f"O {document_type} informado não é válido."
        super().__init__(title, self.code, http_status, description, translation)


class DocumentAlreadyRegistered(QIException):
    code = "QIT002006"

    def __init__(self, user_type) -> None:
        title = "Document already registered"
        http_status = 409
        description = f"This document is already registered as {user_type}."
        translation = "Este documento já está cadastrado neste tipo de usuário."
        super().__init__(title, self.code, http_status, description, translation)


class EmailAlreadyRegistered(QIException):
    code = "QIT002007"

    def __init__(self, user_type) -> None:
        title = "Email already registered"
        http_status = 409
        description = f"This email is already registered as {user_type}."
        translation = "Este e-mail já está cadastrado neste tipo de usuário."
        super().__init__(title, self.code, http_status, description, translation)


class InvalidBirthDate(QIException):
    code = "QIT002008"

    def __init__(self, reason) -> None:
        title = "Invalid birth date"
        http_status = 422
        description = f"Birth date refused: {reason}."
        translation = "A data de nascimento não existe ou está abaixo da idade mínima."
        super().__init__(title, self.code, http_status, description, translation)


class NotFoundCompany(QIException):
    code = "QIT002009"

    def __init__(self, company_id) -> None:
        title = "Company not found"
        http_status = 404
        description = f"Company {company_id} was not found."
        translation = "Empresa não encontrada."
        super().__init__(title, self.code, http_status, description, translation)
