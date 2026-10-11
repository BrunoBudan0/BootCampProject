class CompanyDTO:
    @staticmethod
    def obj_to_dict(company) -> dict:
        return {
            "id": str(company.company_key),
            "user_type": company.USER_TYPE,
            "legal_name": company.legal_name,
            "trade_name": company.trade_name,
            "email": company.email,
            "phone": company.phone,
            "created_at": company.created_at.isoformat(),
        }

    @staticmethod
    def names_to_dict(company) -> dict:
        return {
            "id": str(company.company_key),
            "legal_name": company.legal_name,
            "trade_name": company.trade_name,
        }
