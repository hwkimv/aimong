#!/usr/bin/env python3
"""Load the generated seed SQL into a real PostgreSQL database and verify it.

Generating a .sql file only proves the file was written. This script proves the
file actually applies to the backend's schema and that the resulting rows match
the source JSON.

It applies the Flyway migrations from backend/src/main/resources/db/migration in
version order, runs the seed SQL, and then checks row counts, uniqueness,
foreign keys, the question-to-set binding the backend serves on, and a sample of
rows read back and compared against the JSON payload.

Connection comes from AIMONG_TEST_DB_URL, e.g.
    postgresql://postgres:postgres@localhost:5432/aimong_test
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

PIPELINE_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PIPELINE_ROOT / "src"))

from aimong_qbank.paths import BACKEND_MIGRATIONS, DEFAULT_OUT_DIR  # noqa: E402

MIGRATION_RE = re.compile(r"^V(\d+)__")


class Failure(Exception):
    pass


def migration_files() -> list[Path]:
    if not BACKEND_MIGRATIONS.is_dir():
        raise Failure(f"backend migrations not found at {BACKEND_MIGRATIONS}")

    def version(path: Path) -> int:
        match = MIGRATION_RE.match(path.name)
        if not match:
            raise Failure(f"unexpected migration filename: {path.name}")
        return int(match.group(1))

    return sorted(BACKEND_MIGRATIONS.glob("V*.sql"), key=version)


def check(label: str, actual, expected) -> str:
    if actual != expected:
        raise Failure(f"{label}: expected {expected!r}, got {actual!r}")
    return f"  OK  {label}: {actual}"


def main() -> int:
    try:
        import psycopg
    except ImportError:
        print("psycopg is required: pip install 'psycopg[binary]'", file=sys.stderr)
        return 2

    url = os.environ.get("AIMONG_TEST_DB_URL")
    if not url:
        print("AIMONG_TEST_DB_URL is not set", file=sys.stderr)
        return 2

    out_dir = Path(os.environ.get("AIMONG_OUT_DIR") or DEFAULT_OUT_DIR)
    seed_path = out_dir / "question-bank-seed.sql"
    payload_path = out_dir / "backend-compatible-question-bank.json"
    if not seed_path.exists() or not payload_path.exists():
        print(f"run `make export` first; missing artifacts in {out_dir}", file=sys.stderr)
        return 2

    payload = json.loads(payload_path.read_text(encoding="utf-8"))
    expected_questions = len(payload["questions"])
    expected_missions = len(payload["missions"])
    expected_sets = len(payload["missionSets"])

    lines: list[str] = []
    try:
        with psycopg.connect(url, autocommit=True) as conn:
            print("==> applying backend migrations")
            with conn.cursor() as cur:
                cur.execute("DROP SCHEMA IF EXISTS public CASCADE")
                cur.execute("DROP SCHEMA IF EXISTS private CASCADE")
                cur.execute("CREATE SCHEMA public")
                for path in migration_files():
                    cur.execute(path.read_text(encoding="utf-8"))
                    print(f"  applied {path.name}")

            print("==> applying seed SQL")
            with conn.cursor() as cur:
                cur.execute(seed_path.read_text(encoding="utf-8"))

            print("==> verifying loaded data")
            with conn.cursor() as cur:
                lines.append(check("missions rows", _scalar(cur, "SELECT count(*) FROM public.missions"), expected_missions))
                lines.append(check("mission_sets rows", _scalar(cur, "SELECT count(*) FROM public.mission_sets"), expected_sets))
                lines.append(
                    check("question_bank rows", _scalar(cur, "SELECT count(*) FROM public.question_bank"), expected_questions)
                )
                lines.append(
                    check(
                        "question_answer_keys rows",
                        _scalar(cur, "SELECT count(*) FROM private.question_answer_keys"),
                        expected_questions,
                    )
                )

                # Derived UUIDs must not have collapsed two questions into one row.
                lines.append(
                    check(
                        "distinct question ids",
                        _scalar(cur, "SELECT count(DISTINCT id) FROM public.question_bank"),
                        expected_questions,
                    )
                )

                # Every question must be reachable through the set the backend serves on.
                lines.append(
                    check("questions with NULL set_id", _scalar(cur, "SELECT count(*) FROM public.question_bank WHERE set_id IS NULL"), 0)
                )
                lines.append(
                    check(
                        "orphan set_id references",
                        _scalar(
                            cur,
                            """
                            SELECT count(*) FROM public.question_bank q
                            LEFT JOIN public.mission_sets s ON s.set_id = q.set_id
                            WHERE q.set_id IS NOT NULL AND s.set_id IS NULL
                            """,
                        ),
                        0,
                    )
                )
                lines.append(
                    check(
                        "sets with fewer active questions than question_count",
                        _scalar(
                            cur,
                            """
                            SELECT count(*) FROM public.mission_sets s
                            WHERE (
                                SELECT count(*) FROM public.question_bank q
                                WHERE q.set_id = s.set_id AND q.is_active
                                  AND q.question_pool_status = 'ACTIVE'
                            ) < s.question_count
                            """,
                        ),
                        0,
                    )
                )

                # Foreign keys and per-mission quota.
                lines.append(
                    check(
                        "questions whose mission is missing",
                        _scalar(
                            cur,
                            """
                            SELECT count(*) FROM public.question_bank q
                            LEFT JOIN public.missions m ON m.id = q.mission_id
                            WHERE m.id IS NULL
                            """,
                        ),
                        0,
                    )
                )
                lines.append(
                    check(
                        "answer keys without a question",
                        _scalar(
                            cur,
                            """
                            SELECT count(*) FROM private.question_answer_keys k
                            LEFT JOIN public.question_bank q ON q.id = k.question_id
                            WHERE q.id IS NULL
                            """,
                        ),
                        0,
                    )
                )
                lines.append(
                    check(
                        "missions not holding 66 questions",
                        _scalar(
                            cur,
                            """
                            SELECT count(*) FROM (
                                SELECT mission_id FROM public.question_bank
                                GROUP BY mission_id HAVING count(*) <> 66
                            ) t
                            """,
                        ),
                        0,
                    )
                )

                lines.extend(_verify_constraints(cur, conn))
                lines.extend(_verify_sample_rows(cur, payload))

            print("==> re-running seed SQL (must be idempotent)")
            with conn.cursor() as cur:
                cur.execute(seed_path.read_text(encoding="utf-8"))
                lines.append(
                    check(
                        "question_bank rows after reseed",
                        _scalar(cur, "SELECT count(*) FROM public.question_bank"),
                        expected_questions,
                    )
                )

    except Failure as error:
        print("\n".join(lines))
        print(f"\nFAIL: {error}", file=sys.stderr)
        return 1

    print()
    print("\n".join(lines))
    print("\nPostgreSQL verification PASS")
    return 0


def _scalar(cur, sql: str):
    cur.execute(sql)
    row = cur.fetchone()
    return row[0] if row else None


def _verify_constraints(cur, conn) -> list[str]:
    """The database must reject what the contract forbids, not just hold it."""
    import psycopg

    results: list[str] = []

    # Duplicate primary key must be rejected.
    cur.execute("SELECT id, mission_id, set_id, question_type, difficulty, prompt, curriculum_ref FROM public.question_bank LIMIT 1")
    row = cur.fetchone()
    try:
        with conn.transaction():
            cur.execute(
                """
                INSERT INTO public.question_bank
                    (id, mission_id, set_id, question_type, difficulty, prompt, curriculum_ref)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                """,
                row,
            )
        raise Failure("duplicate question_bank id was accepted")
    except psycopg.errors.UniqueViolation:
        results.append("  OK  duplicate question id rejected by primary key")

    # mission_sets star/variant uniqueness.
    cur.execute("SELECT mission_id, star_level, variant_no, mission_code, stage, title, display_order FROM public.mission_sets LIMIT 1")
    mission_id, star, variant, code, stage, title, order_ = cur.fetchone()
    try:
        with conn.transaction():
            cur.execute(
                """
                INSERT INTO public.mission_sets
                    (set_id, mission_id, mission_code, star_level, variant_no, stage, title, display_order)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """,
                ("DUPLICATE-SET", mission_id, code, star, variant, stage, title, order_),
            )
        raise Failure("duplicate (mission, star_level, variant_no) was accepted")
    except psycopg.errors.UniqueViolation:
        results.append("  OK  duplicate mission set star/variant rejected by unique constraint")

    # question_count CHECK.
    try:
        with conn.transaction():
            cur.execute(
                """
                INSERT INTO public.mission_sets
                    (set_id, mission_id, mission_code, star_level, variant_no, stage, title, question_count, display_order)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                ("CHECK-SET", mission_id, code, star, 99, stage, title, 7, order_),
            )
        raise Failure("mission_sets.question_count = 7 was accepted")
    except psycopg.errors.CheckViolation:
        results.append("  OK  mission_sets.question_count CHECK rejected a non-10 set")

    # Foreign key from question_bank to missions.
    try:
        with conn.transaction():
            cur.execute(
                """
                INSERT INTO public.question_bank
                    (mission_id, question_type, difficulty, prompt, curriculum_ref)
                VALUES ('00000000-0000-0000-0000-000000000000', 'OX', 'LOW', 'x', 'y')
                """
            )
        raise Failure("question_bank row with unknown mission_id was accepted")
    except psycopg.errors.ForeignKeyViolation:
        results.append("  OK  question_bank.mission_id foreign key rejected an unknown mission")

    return results


def _verify_sample_rows(cur, payload: dict) -> list[str]:
    """Read rows back and compare them against the source JSON."""
    questions = payload["questions"]
    sample = [questions[0], questions[len(questions) // 2], questions[-1]]
    sample += [next(q for q in questions if q["type"] == t) for t in ("OX", "MULTIPLE", "FILL", "SITUATION")]

    for question in sample:
        cur.execute(
            """
            SELECT q.prompt, q.options, q.content_tags, q.pack_no, q.set_id,
                   CAST(q.question_type AS TEXT), CAST(q.difficulty AS TEXT),
                   k.answer_payload, k.explanation
            FROM public.question_bank q
            JOIN private.question_answer_keys k ON k.question_id = q.id
            WHERE q.id = %s
            """,
            (question["id"],),
        )
        row = cur.fetchone()
        if row is None:
            raise Failure(f"{question['externalId']}: row not found in database")
        prompt, options, tags, pack_no, set_id, qtype, difficulty, answer_payload, explanation = row

        for label, actual, expected in (
            ("prompt", prompt, question["question"]),
            ("options", options, question["options"]),
            ("content_tags", tags, question["contentTags"]),
            ("pack_no", pack_no, question["packNo"]),
            ("set_id", set_id, question["setId"]),
            ("question_type", qtype, question["type"]),
            ("difficulty", difficulty, question["difficulty"]),
            ("answer_payload", answer_payload, question["answerPayload"]),
            ("explanation", explanation, question["explanation"]),
        ):
            if actual != expected:
                raise Failure(f"{question['externalId']}.{label}: database has {actual!r}, JSON has {expected!r}")

    return [f"  OK  {len(sample)} sample rows read back match the source JSON"]


if __name__ == "__main__":
    raise SystemExit(main())
