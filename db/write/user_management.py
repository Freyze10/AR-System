from db.connection import get_connection


def _execute(statements):
    """Run [(sql, params), ...] in a single transaction."""
    conn = get_connection()
    try:
        conn.autocommit = False
        with conn.cursor() as cur:
            for sql, params in statements:
                cur.execute(sql, params)
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


# ── Users ─────────────────────────────────────────────────────────────────
def add_user(role_id, username, password, first_name, last_name):
    _execute([(
        "INSERT INTO tbl_user (role_id, first_name, last_name, hostname, ip_address, username, password) "
        "VALUES (%s, %s, %s, NULL, NULL, %s, %s)",
        (role_id, first_name, last_name, username, password))])


def update_user(user_id, role_id, username, password, first_name, last_name):
    _execute([(
        "UPDATE tbl_user SET role_id = %s, username = %s, password = %s, "
        "first_name = %s, last_name = %s WHERE user_id = %s",
        (role_id, username, password, first_name, last_name, user_id))])

def delete_user(user_id):
    _execute([
        ("DELETE FROM tbl_mac_address WHERE user_id = %s", (user_id,)),
        ("DELETE FROM tbl_user WHERE user_id = %s", (user_id,)),
    ])


# ── Roles ─────────────────────────────────────────────────────────────────
def add_role(department, role):
    _execute([("INSERT INTO tbl_role (department, role) VALUES (%s, %s)", (department, role))])


def delete_role(role_id):
    _execute([("DELETE FROM tbl_role WHERE role_id = %s", (role_id,))])