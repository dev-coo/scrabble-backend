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
import os

import psycopg

# ⭐ 접속 정보는 **환경변수**에서 읽습니다.
#
# 예전에는 비밀번호까지 이 파일에 적혀 있었습니다. 내 컴퓨터에서만
# 돌 때는 편했지만, 저장소는 공개되어 있어서 **비밀번호가 인터넷에
# 그대로 올라가 있는 셈**이었습니다.
#
# 아래 기본값은 각자 컴퓨터에서 개발할 때 쓰던 그 값입니다. 그래서
# 환경변수를 하나도 안 넣어도 지금까지처럼 그냥 돌아갑니다.
# 서버에서는 진짜 비밀번호를 환경변수로 넣어 주고, 그 값은 서버 안에만
# 있습니다(저장소에는 없습니다).
DB_CONFIG = {
    "host": os.environ.get("SCRABBLE_DB_HOST", "localhost"),
    "port": int(os.environ.get("SCRABBLE_DB_PORT", "5432")),
    "dbname": os.environ.get("SCRABBLE_DB_NAME", "scrabble"),
    "user": os.environ.get("SCRABBLE_DB_USER", "scrabble"),
    "password": os.environ.get("SCRABBLE_DB_PASSWORD", "scrabble"),
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
