# ─────────────────────────────────────────────────────────────
# 데이터베이스 연결 (PostgreSQL)
#
# 3티어 중 백엔드는 "로직 + 데이터" 티어입니다.
# 프론트엔드는 DB에 직접 접근하지 않습니다. 항상 백엔드 API를
# 거쳐서만 데이터를 주고받습니다. 그래서 이 파일은 백엔드
# 저장소에만 있습니다.
#
# DB는 Docker 컨테이너로 떠 있습니다 (컨테이너명: scrabble-db).
# DBeaver로 접속하면 같은 데이터를 눈으로 볼 수 있습니다.
#
# 연결 확인:  .venv/bin/python db.py
# ─────────────────────────────────────────────────────────────
import psycopg

# 교육용 로컬 DB라 접속 정보를 코드에 그대로 둡니다.
# 실무에서는 환경변수(.env)로 빼서 저장소에 올리지 않습니다.
DB_CONFIG = {
    "host": "localhost",
    "port": 5432,
    "dbname": "scrabble",
    "user": "scrabble",
    "password": "scrabble",
}


def get_connection():
    """DB 연결을 하나 열어서 돌려줍니다.

    사용 예:
        from db import get_connection

        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT id, nickname FROM players")
                rows = cur.fetchall()
    """
    return psycopg.connect(**DB_CONFIG)


if __name__ == "__main__":
    # 직접 실행하면 지금 DB가 어떤 상태인지 보여줍니다.
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT table_name
                FROM information_schema.tables
                WHERE table_schema = 'public'
                ORDER BY table_name
            """)
            tables = [r[0] for r in cur.fetchall()]

            print(f"연결 성공 → {DB_CONFIG['host']}:{DB_CONFIG['port']}/{DB_CONFIG['dbname']}")
            print(f"테이블 {len(tables)}개: {', '.join(tables) if tables else '(없음)'}")

            for t in tables:
                cur.execute(f'SELECT count(*) FROM "{t}"')
                print(f"  - {t}: {cur.fetchone()[0]}행")
