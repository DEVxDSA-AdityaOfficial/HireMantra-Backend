"""
Add parser/screening columns to ``candidates`` if missing (MySQL / SQLite).

Run from Backend:  python -m scripts.ensure_candidates_screening_columns
"""

from sqlalchemy import inspect, text

from database.database import engine


def main() -> int:
    insp = inspect(engine)
    if not insp.has_table("candidates"):
        print("No candidates table; skip.")
        return 0
    cols = {c["name"] for c in insp.get_columns("candidates")}
    dialect = engine.dialect.name

    alters: list[str] = []
    add_email = False
    if "email" not in cols:
        add_email = True
        alters.append(
            "ALTER TABLE candidates ADD COLUMN email VARCHAR(255) NULL"
            if dialect == "mysql"
            else "ALTER TABLE candidates ADD COLUMN email VARCHAR(255)"
        )
    if "screening_status" not in cols:
        alters.append(
            "ALTER TABLE candidates ADD COLUMN screening_status VARCHAR(32) NOT NULL DEFAULT 'pending'"
        )
    if "ats_match_score" not in cols:
        alters.append(
            "ALTER TABLE candidates ADD COLUMN ats_match_score DOUBLE NULL"
            if dialect == "mysql"
            else "ALTER TABLE candidates ADD COLUMN ats_match_score REAL"
        )
    if "jd_match_analysis" not in cols:
        alters.append("ALTER TABLE candidates ADD COLUMN jd_match_analysis TEXT")
    if "screening_details_json" not in cols:
        alters.append("ALTER TABLE candidates ADD COLUMN screening_details_json TEXT")
    if "parsed_resume_summary" not in cols:
        alters.append("ALTER TABLE candidates ADD COLUMN parsed_resume_summary TEXT")
    if "parser_error_message" not in cols:
        alters.append("ALTER TABLE candidates ADD COLUMN parser_error_message TEXT")
    if "screening_updated_at" not in cols:
        alters.append("ALTER TABLE candidates ADD COLUMN screening_updated_at DATETIME")

    if not alters:
        print("candidates table already has screening + email columns.")
        return 0

    with engine.begin() as conn:
        for stmt in alters:
            print(stmt)
            conn.execute(text(stmt))
    if add_email and dialect == "mysql":
        idx = "CREATE INDEX ix_candidates_email ON candidates (email)"
        print(idx)
        try:
            with engine.begin() as conn:
                conn.execute(text(idx))
        except Exception as e:
            print(f"(index skip or exists: {e})")
    print("Done.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
