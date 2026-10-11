class IdentityDTO:
    @staticmethod
    def from_profile(profile: dict) -> dict:
        return {"id": profile["id"], "user_type": profile["user_type"]}
