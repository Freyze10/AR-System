from db.connection import get_connection


def _fetch(sql, params=None):
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(sql, params or ())
            return cur.fetchall()
    finally:
        conn.close()

# ── Login ─────────────────────────────────────────────────────────────────
def authenticate_user(username, password):
    """(user_id, username, department, role) when the credentials match, else None"""
    rows = _fetch("""
        SELECT u.user_id, u.username, r.department, r.role
        FROM tbl_user u
        JOIN tbl_role r ON r.role_id = u.role_id
        WHERE LOWER(u.username) = LOWER(%s) AND u.password = %s
    """, (username, password))
    return rows[0] if rows else None


def has_mac_address(user_id):
    return bool(_fetch("SELECT 1 FROM tbl_mac_address WHERE user_id = %s", (user_id,)))