"""Load the seed SQL into a real PostgreSQL database.

Skipped unless AIMONG_TEST_DB_URL points at a throwaway database, so the default
test run stays offline. CI provides one through a postgres service container.

These behaviours are PostgreSQL-specific — enum types, JSONB round-tripping,
partial constraint checks and the dollar-quoted seed — so H2 would not prove them.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

PIPELINE_ROOT = Path(__file__).resolve().parents[1]
DB_URL = os.environ.get("AIMONG_TEST_DB_URL")

pytestmark = pytest.mark.skipif(not DB_URL, reason="AIMONG_TEST_DB_URL is not set")

psycopg = pytest.importorskip("psycopg") if DB_URL else None


@pytest.fixture(scope="module")
def seeded(tmp_path_factory):
    """Export artifacts, then apply migrations and the seed to the test database."""
    out_dir = tmp_path_factory.mktemp("out")
    env = {
        **os.environ,
        "PYTHONPATH": str(PIPELINE_ROOT / "src"),
        "AIMONG_OUT_DIR": str(out_dir),
    }
    export = subprocess.run(
        [sys.executable, "-m", "aimong_qbank.cli", "verify", "--out-dir", str(out_dir)],
        env=env,
        capture_output=True,
        text=True,
    )
    assert export.returncode == 0, export.stdout + export.stderr

    verify = subprocess.run(
        [sys.executable, str(PIPELINE_ROOT / "tools" / "verify_postgres.py")],
        env=env,
        capture_output=True,
        text=True,
    )
    assert verify.returncode == 0, verify.stdout + verify.stderr

    with psycopg.connect(DB_URL, autocommit=True) as conn:
        yield conn


def scalar(conn, sql, params=None):
    with conn.cursor() as cur:
        cur.execute(sql, params)
        return cur.fetchone()[0]


def test_row_counts(seeded):
    assert scalar(seeded, "SELECT count(*) FROM public.question_bank") == 1056
    assert scalar(seeded, "SELECT count(*) FROM private.question_answer_keys") == 1056
    assert scalar(seeded, "SELECT count(*) FROM public.missions") == 16
    assert scalar(seeded, "SELECT count(*) FROM public.mission_sets") == 96


def test_every_question_is_reachable_through_its_set(seeded):
    """The regression this seed exists to prevent: set-based serving finding nothing."""
    assert scalar(seeded, "SELECT count(*) FROM public.question_bank WHERE set_id IS NULL") == 0
    unreachable = scalar(
        seeded,
        """
        SELECT count(*) FROM public.mission_sets s
        WHERE (
            SELECT count(*) FROM public.question_bank q
            WHERE q.set_id = s.set_id AND q.is_active
              AND q.question_pool_status = 'ACTIVE'
        ) < s.question_count
        """,
    )
    assert unreachable == 0


def test_sets_do_not_share_questions(seeded):
    overlapping = scalar(
        seeded,
        """
        SELECT count(*) FROM (
            SELECT id FROM public.question_bank GROUP BY id HAVING count(DISTINCT set_id) > 1
        ) t
        """,
    )
    assert overlapping == 0


def test_jsonb_round_trips_korean_options(seeded):
    options = scalar(
        seeded,
        "SELECT options FROM public.question_bank WHERE question_type = 'MULTIPLE' AND options IS NOT NULL LIMIT 1",
    )
    assert isinstance(options, list) and len(options) == 4
    assert any(any("가" <= ch <= "힣" for ch in str(option)) for option in options)


def test_answer_payload_is_one_based(seeded):
    """Indexes are 0-based in the dataset and 1-based in the answer key."""
    off_range = scalar(
        seeded,
        """
        SELECT count(*) FROM public.question_bank q
        JOIN private.question_answer_keys k ON k.question_id = q.id
        WHERE q.question_type IN ('MULTIPLE', 'SITUATION')
          AND (k.answer_payload #>> '{}')::int NOT BETWEEN 1 AND 4
        """,
    )
    assert off_range == 0

    fill_off_range = scalar(
        seeded,
        """
        SELECT count(*) FROM public.question_bank q
        JOIN private.question_answer_keys k ON k.question_id = q.id
        CROSS JOIN LATERAL jsonb_array_elements(k.answer_payload) AS entry
        WHERE q.question_type = 'FILL'
          AND (entry #>> '{}')::int NOT BETWEEN 1 AND 4
        """,
    )
    assert fill_off_range == 0

    ox_non_boolean = scalar(
        seeded,
        """
        SELECT count(*) FROM public.question_bank q
        JOIN private.question_answer_keys k ON k.question_id = q.id
        WHERE q.question_type = 'OX' AND jsonb_typeof(k.answer_payload) <> 'boolean'
        """,
    )
    assert ox_non_boolean == 0


def test_per_mission_quota_holds_in_the_database(seeded):
    off_quota = scalar(
        seeded,
        "SELECT count(*) FROM (SELECT mission_id FROM public.question_bank GROUP BY mission_id HAVING count(*) <> 66) t",
    )
    assert off_quota == 0


def test_duplicate_external_id_cannot_produce_two_rows(seeded):
    """Derived UUIDs are the uniqueness mechanism, since there is no external_id column."""
    assert scalar(seeded, "SELECT count(DISTINCT id) FROM public.question_bank") == 1056
