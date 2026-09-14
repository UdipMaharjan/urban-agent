from typing import Literal

from sqlalchemy import select
from sqlalchemy.dialects.sqlite import insert
from sqlalchemy.orm import Session

from ..models import Feedback
from ..schemas import FeedbackCreate


def store_feedback(
    session: Session, payload: FeedbackCreate
) -> tuple[Feedback, Literal["created", "duplicate", "conflict"]]:
    """Shared ingestion boundary. Caller owns the transaction; never overwrite raw input."""
    values = payload.storage_values()
    statement = (
        insert(Feedback)
        .values(**values)
        .on_conflict_do_nothing(index_elements=["source", "feedback_id"])
        .returning(Feedback.id)
    )
    inserted_id = session.scalar(statement)
    if inserted_id is not None:
        return session.get(Feedback, inserted_id), "created"
    existing = session.scalar(
        select(Feedback).where(
            Feedback.source == payload.source, Feedback.feedback_id == payload.feedback_id
        )
    )
    identical = all(getattr(existing, key) == value for key, value in values.items())
    return existing, "duplicate" if identical else "conflict"
