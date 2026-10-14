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

# One SQL condition per key, each with a single %s for the search text.
# These are fixed strings, never built from user input.
# Product code / color look at ALL items of the receipt, even though the list only
# shows the first item, so a receipt is found by any of its items.
_SEARCH = {
    "ar_no": "CAST(h.ar_no AS TEXT) ILIKE %s",
    "ar_date": "TO_CHAR(h.ar_date, 'MM/DD/YYYY') ILIKE %s",   # same format the table shows
    "customer": "h.customer ILIKE %s",
    "prod_code": "EXISTS (SELECT 1 FROM tbl_ar02 s WHERE s.ar_no = h.ar_no AND s.prod_code ILIKE %s)",
    "prod_color": "EXISTS (SELECT 1 FROM tbl_ar02 s WHERE s.ar_no = h.ar_no AND s.prod_color ILIKE %s)",
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
    """One row per receipt (no repeats), no row limit. The item columns come from the
    receipt's first item; item_count is how many items it has:
    (ar_no, ar_date, customer, prod_code, prod_color, quantity, qty_unit, is_canceled, item_count)"""
    where, params = "", []
    search = (search or "").strip()
    if search:
        conditions = [_SEARCH[column]] if column in _SEARCH else list(_SEARCH.values())
        where = "WHERE (" + " OR ".join(conditions) + ")"
        params = [_like(search)] * len(conditions)

    return _fetch(f"""
        SELECT h.ar_no, h.ar_date, h.customer, f.prod_code, f.prod_color,
               f.quantity, f.qty_unit, h.is_canceled, COALESCE(c.item_count, 0)
        FROM tbl_ar01 h
        -- the first item of each receipt (lowest sequence)
        LEFT JOIN LATERAL (
            SELECT d.prod_code, d.prod_color, d.quantity, d.qty_unit
            FROM tbl_ar02 d
            WHERE d.ar_no = h.ar_no
            ORDER BY d.sequence, d.id
            LIMIT 1
        ) f ON TRUE
        LEFT JOIN (SELECT ar_no, COUNT(*) AS item_count
                   FROM tbl_ar02 GROUP BY ar_no) c ON c.ar_no = h.ar_no
        {where}
        ORDER BY h.ar_no DESC
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