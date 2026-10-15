from db.connection import get_connection


def _fetch(sql, params=None):
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(sql, params or ())
            return cur.fetchall()
    finally:
        conn.close()


# ── Roles ─────────────────────────────────────────────────────────────────
def get_roles():
    """[(role_id, department, role), ...]"""
    return _fetch("SELECT role_id, department, role FROM tbl_role ORDER BY department, role")


def get_role_usage():
    """[(role_id, department, role, user_count), ...]"""
    return _fetch("""
        SELECT r.role_id, r.department, r.role, COUNT(u.user_id)
        FROM tbl_role r
        LEFT JOIN tbl_user u ON u.role_id = r.role_id
        GROUP BY r.role_id, r.department, r.role
        ORDER BY r.department, r.role
    """)


def role_exists(department, role):
    return bool(_fetch(
        "SELECT 1 FROM tbl_role WHERE LOWER(department) = LOWER(%s) AND LOWER(role) = LOWER(%s)",
        (department, role)))


# ── Users ─────────────────────────────────────────────────────────────────
def get_users():
    """[(user_id, first_name, last_name, username, department, role, hostname, ip_address, mac_address), ...]"""
    return _fetch("""
        SELECT u.user_id, u.first_name, u.last_name, u.username, r.department, r.role,
               u.hostname, u.ip_address, m.mac_address
        FROM tbl_user u
        JOIN tbl_role r ON r.role_id = u.role_id
        LEFT JOIN tbl_mac_address m ON m.user_id = u.user_id
        ORDER BY r.department, u.username
    """)


def get_user(user_id):
    """(username, role_id, password, first_name, last_name) or None"""
    rows = _fetch(
        "SELECT username, role_id, password, first_name, last_name FROM tbl_user WHERE user_id = %s",
        (user_id,))
    return rows[0] if rows else None


def username_exists(username, exclude_user_id=None):
    return bool(_fetch(
        "SELECT 1 FROM tbl_user WHERE LOWER(username) = LOWER(%s) "
        "AND (%s IS NULL OR user_id <> %s)",
        (username, exclude_user_id, exclude_user_id)))