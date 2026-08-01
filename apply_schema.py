# ─────────────────────────────────────────────────────────────
# schema.sql 을 DB에 적용합니다.
#
# 실행:  .venv/bin/python apply_schema.py
#
# schema.sql 은 "설계도"일 뿐 그 자체로는 아무 일도 하지 않습니다.
# 이 파일이 설계도를 읽어서 실제 DB에 반영해 줍니다.
#
# 여러 번 실행해도 안전합니다. (schema.sql 의 모든 문장에
# IF NOT EXISTS 가 붙어 있어서 이미 있는 테이블은 건너뜁니다)
# ─────────────────────────────────────────────────────────────
from pathlib import Path

from db import get_connection

SCHEMA_FILE = Path(__file__).parent / "schema.sql"


def main():
    sql = SCHEMA_FILE.read_text(encoding="utf-8")

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql)

            # 적용 후 지금 DB에 무엇이 있는지 보여줍니다.
            cur.execute("""
                SELECT table_name
                FROM information_schema.tables
                WHERE table_schema = 'public'
                ORDER BY table_name
            """)
            tables = [r[0] for r in cur.fetchall()]

            print(f"schema.sql 적용 완료 → 테이블 {len(tables)}개")
            for t in tables:
                cur.execute(f'SELECT count(*) FROM "{t}"')
                print(f"  - {t}: {cur.fetchone()[0]}행")


if __name__ == "__main__":
    main()
