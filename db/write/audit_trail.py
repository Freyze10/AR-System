import sys

from db.connection import get_connection


def _clip(value, length):
    return value[:length] if value else None


def log_action(action_type, details="", user_id=None, username=None, mac_address=None):
    """Add one audit row. Returns True on success.

    action_type : short label (max 32 chars), e.g. "SAVED", "UPDATED", "LOGIN"
    details     : free text, can be several lines
    user_id     : tbl_user.user_id, or pass username and it is looked up
    mac_address : the MAC of this PC, the same value login registers. It is matched
                  in tbl_mac_address and the matching id is stored in mac_id
                  (NULL when there is no match).

    A logging failure never blocks the user's real work: it is printed and False is returned.
    """
    conn = get_connection()
    try:
        conn.autocommit = False
        with conn.cursor() as cur:
            if user_id is None and username:
                cur.execute("SELECT user_id FROM tbl_user WHERE LOWER(username) = LOWER(%s)",
                            (username,))
                row = cur.fetchone()
                user_id = row[0] if row else None

            mac_id = None
            if mac_address:
                cur.execute("SELECT id FROM tbl_mac_address WHERE mac_address = %s",
                            (mac_address,))
                row = cur.fetchone()
                mac_id = row[0] if row else None

            cur.execute(
                'INSERT INTO tbl_audit_trail ("timestamp", user_id, action_type, details, mac_id) '
                "VALUES (NOW(), %s, %s, %s, %s)",
                (user_id, _clip(action_type, 32), details or None, mac_id))
        conn.commit()
        return True
    except Exception as e:
        conn.rollback()
        print(f"Audit log failed: {e}", file=sys.stderr)
        return False
    finally:
        conn.close()