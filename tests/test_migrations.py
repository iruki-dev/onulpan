import psycopg
import pytest


def _post(conn, title="t"):
    conn.execute("INSERT INTO slugs (slug, display_name) VALUES ('x','x') ON CONFLICT DO NOTHING")
    return conn.execute(
        """INSERT INTO posts (kind, section, slug, title, summary, body_md, char_count, model, prompt_version,
                              verify_report, cost_usd)
           VALUES ('fact','economy','x',%s,'s','b',1,'m','v','{}',0) RETURNING seq""", (title,)
    ).fetchone()["seq"]


@pytest.mark.parametrize("stmt", [
    "UPDATE posts SET title = 'changed'",
    "DELETE FROM posts",
    "TRUNCATE posts CASCADE",
])
def test_posts_are_append_only(conn, stmt):
    _post(conn)
    conn.commit()
    with pytest.raises(psycopg.errors.RaiseException, match="append-only"):
        conn.execute(stmt)
    conn.rollback()


def test_links_point_only_backwards(conn):
    a = _post(conn, "a")
    b = _post(conn, "b")
    conn.execute("INSERT INTO post_links (from_seq, to_seq, rel) VALUES (%s, %s, 'refers')", (b, a))
    with pytest.raises(psycopg.errors.CheckViolation):
        conn.execute("INSERT INTO post_links (from_seq, to_seq, rel) VALUES (%s, %s, 'refers')", (a, b))
    conn.rollback()


def test_records_are_append_only(conn):
    uid = conn.execute("INSERT INTO users (email, provider) VALUES ('a@b.c','email') RETURNING id").fetchone()["id"]
    conn.execute("INSERT INTO editions (user_id, edition_date, as_of_seq, preset, slots, editor_version) "
                 "VALUES (%s, '2026-10-06', 0, 'standard', '[]', 'e1')", (uid,))
    conn.execute("INSERT INTO decision_log (kind, ref, payload) VALUES ('assign','raw:1','{}')")
    conn.execute("INSERT INTO front_pages (edition_date, seqs) VALUES ('2026-10-06', '{}')")
    conn.commit()
    for stmt in ["UPDATE editions SET preset = 'long'", "DELETE FROM editions",
                 "UPDATE decision_log SET ref = 'x'", "DELETE FROM decision_log",
                 "UPDATE front_pages SET fallback = true"]:
        with pytest.raises(psycopg.errors.RaiseException, match="append-only"):
            conn.execute(stmt)
        conn.rollback()


def test_roles_cannot_update_posts(conn):
    rows = conn.execute(
        """SELECT grantee, privilege_type FROM information_schema.role_table_grants
           WHERE table_name = 'posts' AND grantee IN ('app_writer','app_reader')"""
    ).fetchall()
    privs = {(r["grantee"], r["privilege_type"]) for r in rows}
    assert ("app_writer", "INSERT") in privs
    assert ("app_writer", "UPDATE") not in privs and ("app_writer", "DELETE") not in privs
    assert ("app_reader", "UPDATE") not in privs and ("app_reader", "INSERT") not in privs


def test_views_query(conn):
    for v in ["v_verify_rule_daily", "v_quality_daily", "v_llm_cost_daily", "v_outlet_collection_24h",
              "v_review_weekly", "v_correction_monthly", "v_reader_daily", "v_signups_daily",
              "v_front_section_monthly", "v_front_group_monthly", "v_cost_per_post_month"]:
        conn.execute(f"SELECT * FROM {v} LIMIT 1").fetchall()
