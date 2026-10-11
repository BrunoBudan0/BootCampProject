from sqlalchemy.exc import IntegrityError


def violated_constraint_name(integrity_error: IntegrityError) -> str:
    return integrity_error.orig.diag.constraint_name
