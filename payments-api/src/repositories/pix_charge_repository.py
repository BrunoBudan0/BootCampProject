from database import Context
from models import PixCharge


class PixChargeRepository:
    def __init__(self, context: Context) -> None:
        self.session = context.db_session

    def create_pix_charge(self, transaction, provider_charge_id, copy_paste, expires_at):
        pix_charge = PixCharge(
            transaction_id=transaction.id,
            provider_charge_id=provider_charge_id,
            copy_paste=copy_paste,
            expires_at=expires_at,
        )

        self.session.add(pix_charge)
        self.session.flush()

        return pix_charge

    def get_pix_charge_of_transaction(self, transaction):
        return self.session.query(PixCharge).filter_by(transaction_id=transaction.id).first()
