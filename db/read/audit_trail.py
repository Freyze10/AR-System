from datetime import timedelta

from db.connection import get_connection

# (label shown in the combo box, key)
SEARCH_COLUMNS = [
    ("All Columns", "all"),
    ("Workstation", "workstation"),
    ("Action", "action"),
    ("Details", "details"),
    ("IP Address", "ip"),
    ("User MAC", "user_mac"),
    ("Workstation MAC", "ws_mac"),
]

# "hostname\username" (just the username when the hostname is not set yet)
_WORKSTATION = ("CASE WHEN COALESCE(u.hostname, '') = '' THEN u.username "
                "ELSE u.hostname || '\\' || u.username END")

# SQL expression per key. These are fixed strings, never built from user input.
_EXPRESSIONS = {
    "workstation": _WORKSTATION,
    "action": "a.action_type",
    "details": "a.details",
    "ip": "u.ip_address",
    "user_mac": "um.mac_address",
    "ws_mac": "wm.mac_address",
}

# u  = the user who did the action (tbl_user, via user_id)
# um = that user's registered MAC (tbl_mac_address, via user_id)
# wm = the MAC of the workstation the action came from (tbl_mac_address, via mac_id)
_BASE = f"""
    SELECT a.timestamp, {_WORKSTATION} AS workstation, a.action_type, a.details,
           u.ip_address, um.mac_address AS user_mac, wm.mac_address AS ws_mac
      FROM tbl_audit_trail a
      LEFT JOIN tbl_user u         ON u.user_id = a.user_id
      LEFT JOIN tbl_mac_address um ON um.user_id = a.user_id
      LEFT JOIN tbl_mac_address wm ON wm.id = a.mac_id
"""


def _like(text):
    """Escape LIKE wildcards so '%' and '_' in the search box are matched literally."""
    escaped = text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


def get_date_range():
    """(first_date, last_date) found in the audit trail, or (None, None) when it is empty."""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute('SELECT MIN("timestamp")::date, MAX("timestamp")::date FROM tbl_audit_trail')
            return cur.fetchone()
    finally:
        conn.close()


def get_records(search="", column="all", date_from=None, date_to=None):
    """Newest first, no row limit. date_from / date_to are datetime.date and both inclusive."""
    where, params = [], []

    if date_from:
        where.append("a.timestamp >= %s")
        params.append(date_from)
    if date_to:
        where.append("a.timestamp < %s")
        params.append(date_to + timedelta(days=1))

    search = (search or "").strip()
    if search:
        exprs = [_EXPRESSIONS[column]] if column in _EXPRESSIONS else list(_EXPRESSIONS.values())
        where.append("(" + " OR ".join(f"{e} ILIKE %s" for e in exprs) + ")")
        params.extend([_like(search)] * len(exprs))

    sql = _BASE
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY a.timestamp DESC, a.id DESC"

    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            return cur.fetchall()
    finally:
        conn.close()