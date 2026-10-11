from errors import QIException


class IdempotencyKeyConflict(QIException):
    code = "QIT002025"

    def __init__(self, idempotency_key) -> None:
        title = "Idempotency key conflict"
        http_status = 409
        description = f"The Key {idempotency_key} was already used with different content."
        translation = "Esta chave já foi usada com outro conteúdo."
        super().__init__(title, self.code, http_status, description, translation)


class NotFoundAccount(QIException):
    code = "QIT002020"

    def __init__(self, account_id) -> None:
        title = "Account not found"
        http_status = 404
        description = f"Account {account_id} was not found."
        translation = "Conta não encontrada."
        super().__init__(title, self.code, http_status, description, translation)


class InsufficientBalance(QIException):
    code = "QIT002021"

    def __init__(self, amount_cents) -> None:
        title = "Insufficient balance"
        http_status = 409
        description = f"The account does not have enough balance for {amount_cents} cents."
        translation = "Saldo insuficiente para esta operação."
        super().__init__(title, self.code, http_status, description, translation)


class BlockedAccount(QIException):
    code = "QIT002022"

    def __init__(self, account_id) -> None:
        title = "Account blocked"
        http_status = 409
        description = f"Account {account_id} is blocked."
        translation = "A conta está bloqueada."
        super().__init__(title, self.code, http_status, description, translation)


class NotFoundTransaction(QIException):
    code = "QIT002023"

    def __init__(self, transaction_id) -> None:
        title = "Transaction not found"
        http_status = 404
        description = f"Transaction {transaction_id} was not found."
        translation = "Transação não encontrada."
        super().__init__(title, self.code, http_status, description, translation)


class InvalidStatusTransition(QIException):
    code = "QIT002024"

    def __init__(self, current_status, new_status) -> None:
        title = "Invalid status transition"
        http_status = 409
        description = f"A transaction in status {current_status} cannot become {new_status}."
        translation = "A transação não pode mudar para este status."
        super().__init__(title, self.code, http_status, description, translation)


class AlreadyReversed(QIException):
    code = "QIT002026"

    def __init__(self, idempotency_key) -> None:
        title = "Already reversed"
        http_status = 409
        description = f"The transactions of key {idempotency_key} were already reversed or are not settled."
        translation = "Estas transações já foram estornadas."
        super().__init__(title, self.code, http_status, description, translation)


class InvalidAmount(QIException):
    code = "QIT002028"

    def __init__(self, amount_cents) -> None:
        title = "Invalid amount"
        http_status = 422
        description = f"Amount must be greater than zero, got {amount_cents}."
        translation = "O valor precisa ser maior que zero."
        super().__init__(title, self.code, http_status, description, translation)


class SameAccount(QIException):
    code = "QIT002029"

    def __init__(self) -> None:
        title = "Same account"
        http_status = 422
        description = "Source and destination must be different accounts."
        translation = "A origem e o destino precisam ser contas diferentes."
        super().__init__(title, self.code, http_status, description, translation)


class DifferentEvents(QIException):
    code = "QIT002030"

    def __init__(self) -> None:
        title = "Accounts of different events"
        http_status = 422
        description = "Source and destination accounts belong to different events."
        translation = "As contas são de eventos diferentes."
        super().__init__(title, self.code, http_status, description, translation)


class ProviderUnavailable(QIException):
    code = "QIT002031"

    def __init__(self, provider) -> None:
        title = "Provider unavailable"
        http_status = 502
        description = f"The {provider} provider did not answer as expected."
        translation = "O provedor de pagamento não respondeu. Tente de novo."
        super().__init__(title, self.code, http_status, description, translation)


class CardDeclined(QIException):
    code = "QIT002033"

    def __init__(self) -> None:
        title = "Card declined"
        http_status = 422
        description = "The card provider declined the authorization."
        translation = "O cartão foi recusado."
        super().__init__(title, self.code, http_status, description, translation)


class InvalidPixSignature(QIException):
    code = "QIT002034"

    def __init__(self) -> None:
        title = "Invalid signature"
        http_status = 401
        description = "The webhook signature does not match its body."
        translation = "A assinatura do aviso de pagamento não confere."
        super().__init__(title, self.code, http_status, description, translation)


class PixAmountMismatch(QIException):
    code = "QIT002035"

    def __init__(self, charged_cents, paid_cents) -> None:
        title = "Pix amount mismatch"
        http_status = 422
        description = f"Charged {charged_cents} cents but {paid_cents} cents were paid."
        translation = "O valor pago é diferente do valor cobrado."
        super().__init__(title, self.code, http_status, description, translation)


class SourceIsNotAnAttendee(QIException):
    code = "QIT002004"

    def __init__(self) -> None:
        title = "Source is not an attendee"
        http_status = 403
        description = "Only an attendee account can transfer balance."
        translation = "Só a credencial do público pode transferir saldo."
        super().__init__(title, self.code, http_status, description, translation)


class DestinationRefusesTransfers(QIException):
    code = "QIT002027"

    def __init__(self) -> None:
        title = "Destination does not accept transfers"
        http_status = 422
        description = "This destination does not accept transfers."
        translation = "Este destino não aceita transferência."
        super().__init__(title, self.code, http_status, description, translation)


class AccountAlreadyExistsInEvent(QIException):
    code = "QIT002036"

    def __init__(self, event_id) -> None:
        title = "Account already exists in event"
        http_status = 409
        description = f"Event {event_id} already has this account under another idempotency key."
        translation = "O evento já tem esta conta, criada com outra chave."
        super().__init__(title, self.code, http_status, description, translation)


class EventWithoutExternalAccount(QIException):
    code = "QIT002037"

    def __init__(self, event_id) -> None:
        title = "Event without external account"
        http_status = 409
        description = f"Event {event_id} has no external account to receive money from outside."
        translation = "O evento não tem a conta que recebe dinheiro de fora."
        super().__init__(title, self.code, http_status, description, translation)
