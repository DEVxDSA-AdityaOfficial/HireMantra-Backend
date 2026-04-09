"""Resolve organization (tenant) for the authenticated owner user."""

from sqlalchemy.orm import Session

from database.models import Organization


def get_organization_for_owner(db: Session, user_id: str) -> Organization | None:
    """Return the organization owned by this user (one org per owner in current model)."""
    return (
        db.query(Organization)
        .filter(Organization.owner_user_id == user_id)
        .first()
    )
