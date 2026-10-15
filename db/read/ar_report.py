from db.connection import get_connection

# (label shown in the combo box, key)
SEARCH_COLUMNS = [
    ("All Columns", "all"),
    ("AR No.", "ar_no"),
    ("AR Date", "ar_date"),
    ("Customer", "customer"),
    ("Product Code", "prod_code"),
    ("Product Color", "prod_color"),
]

# SQL expression per key. These are fixed strings, never built from user input.
_SEARCH = {
    "ar_no": "CAST(h.ar_no AS TEXT)",
    "ar_date": "TO_CHAR(h.ar_date, 'MM/DD/YYYY')",   # same format the table shows
    "customer": "h.customer",
    "prod_code": "d.prod_code",
    "prod_color": "d.prod_color",
}


def _fetch(sql, params=None):
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(sql, params or ())
            return cur.fetchall()
    finally:
        conn.close()


def _like(text):
    """Escape LIKE wildcards so '%' and '_' in the search box are matched literally."""
    escaped = text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


def get_records(search="", column="all"):
    """One row per item, no row limit:
    (ar_no, ar_date, customer, prod_code, prod_color, quantity, qty_unit, is_canceled, item_count)"""
    where, params = "", []
    search = (search or "").strip()
    if search:
        exprs = [_SEARCH[column]] if column in _SEARCH else list(_SEARCH.values())
        where = "WHERE (" + " OR ".join(f"{e} ILIKE %s" for e in exprs) + ")"
        params = [_like(search)] * len(exprs)

    return _fetch(f"""
        SELECT h.ar_no, h.ar_date, h.customer, d.prod_code, d.prod_color,
               d.quantity, d.qty_unit, h.is_canceled, COALESCE(c.item_count, 0)
        FROM tbl_ar01 h
        LEFT JOIN tbl_ar02 d ON d.ar_no = h.ar_no
        LEFT JOIN (SELECT ar_no, COUNT(*) AS item_count
                   FROM tbl_ar02 GROUP BY ar_no) c ON c.ar_no = h.ar_no
        {where}
        ORDER BY h.ar_no DESC, d.sequence
    """, params)


def get_receipt(ar_no):
    """(ar_no, ar_date, customer, encoded_by) or None"""
    rows = _fetch(
        "SELECT ar_no, ar_date, customer, encoded_by FROM tbl_ar01 WHERE ar_no = %s", (ar_no,))
    return rows[0] if rows else None


def get_receipt_items(ar_no):
    """[(quantity, qty_unit, prod_code, prod_color, lot_no, notes), ...]"""
    return _fetch("""
        SELECT quantity, qty_unit, prod_code, prod_color, lot_no, notes
        FROM tbl_ar02 WHERE ar_no = %s ORDER BY sequence
    """, (ar_no,))


def get_next_ar_no():
    return _fetch("SELECT COALESCE(MAX(ar_no), 0) + 1 FROM tbl_ar01")[0][0]


def get_customers():
    return [r[0] for r in _fetch(
        "SELECT DISTINCT customer FROM tbl_ar01 WHERE customer <> '' ORDER BY customer")]


def get_user_hostname(username):
    """The hostname saved for this user in tbl_user (filled in at the user's first login), or None."""
    rows = _fetch("SELECT hostname FROM tbl_user WHERE LOWER(username) = LOWER(%s)", (username,))
    return rows[0][0] if rows and rows[0][0] else None


def get_user_fullname(hostname, username):
    """'First Last' of the user with this hostname AND username in tbl_user, or None.

    Records saved before the hostname was added only hold the username. For those
    (hostname is empty) the username alone is matched, since usernames are unique.
    """
    rows = _fetch("""
        SELECT first_name, last_name
        FROM tbl_user
        WHERE LOWER(username) = LOWER(%s)
          AND (%s = '' OR LOWER(hostname) = LOWER(%s))
    """, (username, hostname, hostname))
    return f"{rows[0][0]} {rows[0][1]}" if rows else None