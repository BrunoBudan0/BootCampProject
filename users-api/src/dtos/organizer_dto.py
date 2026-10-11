class OrganizerDTO:
    @staticmethod
    def obj_to_dict(organizer) -> dict:
        return {
            "id": str(organizer.organizer_key),
            "user_type": organizer.USER_TYPE,
            "name": organizer.name,
            "email": organizer.email,
            "phone": organizer.phone,
            "created_at": organizer.created_at.isoformat(),
        }
