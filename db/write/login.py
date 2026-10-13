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


def _clip(value, length):
    return value[:length] if value else None


def register_workstation(user_id, hostname, ip_address, mac_address):
    """First login: store hostname/IP on the user and the MAC in tbl_mac_address."""
    statements = [(
        "UPDATE tbl_user SET hostname = %s, ip_address = %s WHERE user_id = %s",
        (_clip(hostname, 36), _clip(ip_address, 32), user_id))]

    if mac_address:
        statements.append((
            "INSERT INTO tbl_mac_address (mac_address, user_id) VALUES (%s, %s) "
            "ON CONFLICT (user_id) DO UPDATE SET mac_address = EXCLUDED.mac_address",
            (_clip(mac_address, 32), user_id)))
    _execute(statements)
