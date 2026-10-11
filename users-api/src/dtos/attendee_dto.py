class AttendeeDTO:
    @staticmethod
    def obj_to_dict(attendee) -> dict:
        return {
            "id": str(attendee.attendee_key),
            "user_type": attendee.USER_TYPE,
            "name": attendee.name,
            "email": attendee.email,
            "birth_date": attendee.birth_date.isoformat(),
            "phone": attendee.phone,
            "postal_code": attendee.postal_code,
            "created_at": attendee.created_at.isoformat(),
        }
