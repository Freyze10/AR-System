import sys

from db.connection import get_connection


def _clip(value, length):
    return value[:length] if value else None


def log_action(user_id, action_type, details="", mac_address=None):
    """Add one audit row. Returns True on success.

    user_id     : tbl_user.user_id of the person doing the action
    action_type : short label, e.g. "LOGIN", "LOGOUT", "AR CREATE", "AR UPDATE"
    mac_address : the MAC of the PC doing the action. It is matched against
                  tbl_mac_address and the matching id is stored in mac_id
                  (NULL when that MAC is not in the table).

    A logging failure never blocks the user's real work: it is printed and False is returned.
    """
    conn = get_connection()
    try:
        conn.autocommit = False
        with conn.cursor() as cur:
            mac_id = None
            if mac_address:
                cur.execute(
                    "SELECT id FROM tbl_mac_address WHERE mac_address = %s",
                    (_clip(mac_address, 32),))
                row = cur.fetchone()
                mac_id = row[0] if row else None

            cur.execute(
                "INSERT INTO tbl_audit_trail (user_id, action_type, details, mac_id) "
                "VALUES (%s, %s, %s, %s)",
                (user_id, _clip(action_type, 32), details or None, mac_id))
        conn.commit()
        return True
    except Exception as e:
        conn.rollback()
        print(f"Audit log failed: {e}", file=sys.stderr)
        return False
    finally:
        conn.close()