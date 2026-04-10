"""
Ensure communication-related schema: ``candidates.email``, ``candidate_notifications``,
``voice_interview_sessions``.

Run from Backend:  python -m scripts.ensure_communication_schema
"""

from sqlalchemy import inspect, text

from database.database import engine
from database.models import CandidateNotification, VoiceInterviewSession


def main() -> int:
    insp = inspect(engine)
    dialect = engine.dialect.name

    if insp.has_table("candidates"):
        cols = {c["name"] for c in insp.get_columns("candidates")}
        if "email" not in cols:
            stmt = (
                "ALTER TABLE candidates ADD COLUMN email VARCHAR(255) NULL"
                if dialect == "mysql"
                else "ALTER TABLE candidates ADD COLUMN email VARCHAR(255)"
            )
            print(stmt)
            with engine.begin() as conn:
                conn.execute(text(stmt))
            if dialect == "mysql":
                idx = "CREATE INDEX ix_candidates_email ON candidates (email)"
                print(idx)
                try:
                    with engine.begin() as conn:
                        conn.execute(text(idx))
                except Exception as e:
                    print(f"(index skip or exists: {e})")
        else:
            print("candidates.email already present.")
    else:
        print("No candidates table; skip email column.")

    CandidateNotification.__table__.create(bind=engine, checkfirst=True)
    VoiceInterviewSession.__table__.create(bind=engine, checkfirst=True)
    print("Tables candidate_notifications / voice_interview_sessions ensured.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
