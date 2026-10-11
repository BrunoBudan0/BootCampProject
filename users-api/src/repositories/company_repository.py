from uuid import uuid4

from database import Context
from models import Company


class CompanyRepository:
    def __init__(self, context: Context) -> None:
        self.session = context.db_session

    def create_company(self, legal_name, trade_name, email, document, password_hash, phone):
        company = Company(
            company_key=uuid4(),
            legal_name=legal_name,
            trade_name=trade_name,
            email=email,
            document=document,
            password_hash=password_hash,
            phone=phone,
        )

        self.session.add(company)
        self.session.flush()

        return company

    def get_company_by_email(self, email):
        return self.session.query(Company).filter_by(email=email).first()

    def get_company_by_key(self, company_key):
        return self.session.query(Company).filter_by(company_key=company_key).first()
