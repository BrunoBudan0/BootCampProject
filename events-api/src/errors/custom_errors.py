from errors.base_error import QIException


class NotAllowedForUserType(QIException):
    code = "QIT002004"

    def __init__(self) -> None:
        super().__init__(
            title="Forbidden for this user type",
            code=self.code,
            http_status=403,
            description="This user type cannot perform this action.",
            translation="Este tipo de usuário não pode fazer isso.",
        )


class CompanyNotFound(QIException):
    code = "QIT002009"

    def __init__(self) -> None:
        super().__init__(
            title="Company not found",
            code=self.code,
            http_status=404,
            description="The company does not exist.",
            translation="A empresa não existe.",
        )


class EventNotFound(QIException):
    code = "QIT002010"

    def __init__(self) -> None:
        super().__init__(
            title="Event not found",
            code=self.code,
            http_status=404,
            description="Event does not exist or does not belong to the caller.",
            translation="O evento não existe ou não é de quem chama.",
        )


class EventClosed(QIException):
    code = "QIT002011"

    def __init__(self) -> None:
        super().__init__(
            title="Event closed",
            code=self.code,
            http_status=409,
            description="The event is closed.",
            translation="O evento está encerrado.",
        )


class CompanyAlreadyInEvent(QIException):
    code = "QIT002012"

    def __init__(self) -> None:
        super().__init__(
            title="Company already in event",
            code=self.code,
            http_status=409,
            description="The company already has a stand in this event.",
            translation="A empresa já participa do evento.",
        )


class AttendeeAlreadyInEvent(QIException):
    code = "QIT002013"

    def __init__(self) -> None:
        super().__init__(
            title="Credential already issued",
            code=self.code,
            http_status=409,
            description="The person already has a credential in this event.",
            translation="A pessoa já tem credencial no evento.",
        )


class CredentialNotFound(QIException):
    code = "QIT002014"

    def __init__(self) -> None:
        super().__init__(
            title="Credential not found",
            code=self.code,
            http_status=404,
            description="Credential does not exist or does not belong to the caller.",
            translation="A credencial não existe ou não é de quem chama.",
        )


class CredentialBlocked(QIException):
    code = "QIT002015"

    def __init__(self) -> None:
        super().__init__(
            title="Credential blocked",
            code=self.code,
            http_status=409,
            description="The credential is blocked.",
            translation="A credencial está bloqueada.",
        )


class ProductNotFound(QIException):
    code = "QIT002016"

    def __init__(self) -> None:
        super().__init__(
            title="Product not found",
            code=self.code,
            http_status=404,
            description="Product does not exist or belongs to another stand.",
            translation="O produto não existe ou é de outro stand.",
        )


class ProductInactive(QIException):
    code = "QIT002017"

    def __init__(self) -> None:
        super().__init__(
            title="Product inactive",
            code=self.code,
            http_status=409,
            description="The product is inactive.",
            translation="O produto está inativo.",
        )


class DuplicatedBarcode(QIException):
    code = "QIT002018"

    def __init__(self) -> None:
        super().__init__(
            title="Duplicated barcode",
            code=self.code,
            http_status=409,
            description="The barcode already exists in this stand.",
            translation="O código de barras já existe no stand.",
        )


class InsufficientStock(QIException):
    code = "QIT002019"

    def __init__(self) -> None:
        super().__init__(
            title="Insufficient stock",
            code=self.code,
            http_status=409,
            description="Not enough stock for this purchase.",
            translation="Estoque insuficiente.",
        )


class StockChanged(QIException):
    code = "QIT002027"

    def __init__(self) -> None:
        super().__init__(
            title="Stock changed",
            code=self.code,
            http_status=409,
            description="The stock changed since it was read. Read the product again.",
            translation="O estoque mudou desde a leitura. Consulte o produto de novo.",
        )


class InsufficientBalance(QIException):
    code = "QIT002021"

    def __init__(self) -> None:
        super().__init__(
            title="Insufficient balance",
            code=self.code,
            http_status=409,
            description="The account does not have enough balance.",
            translation="Saldo insuficiente.",
        )


class PurchaseNotFound(QIException):
    code = "QIT002023"

    def __init__(self) -> None:
        super().__init__(
            title="Purchase not found",
            code=self.code,
            http_status=404,
            description="Purchase does not exist or does not involve the caller.",
            translation="A compra não existe ou não envolve quem chama.",
        )


class IdempotencyKeyReused(QIException):
    code = "QIT002025"

    def __init__(self) -> None:
        super().__init__(
            title="Idempotency key reused",
            code=self.code,
            http_status=409,
            description="The idempotency key was already used with a different content.",
            translation="A chave de idempotência já foi usada com outro conteúdo.",
        )


class PurchaseNotRefundable(QIException):
    code = "QIT002026"

    def __init__(self) -> None:
        super().__init__(
            title="Purchase not refundable",
            code=self.code,
            http_status=409,
            description="The purchase is not paid or was already refunded.",
            translation="A compra não está paga ou já foi estornada.",
        )


class NonPositiveAmount(QIException):
    code = "QIT002028"

    def __init__(self) -> None:
        super().__init__(
            title="Non positive amount",
            code=self.code,
            http_status=422,
            description="The amount must be greater than zero.",
            translation="O valor precisa ser maior que zero.",
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


class CashbackAboveFee(QIException):
    code = "QIT002032"

    def __init__(self) -> None:
        super().__init__(
            title="Cashback above fee",
            code=self.code,
            http_status=422,
            description="Cashback cannot be above the current fee, nor the fee below the current cashback.",
            translation="O cashback não pode passar da tarifa vigente, nem a tarifa ficar abaixo do cashback.",
        )
