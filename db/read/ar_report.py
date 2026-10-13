from db.connection import get_connection


def _fetch(sql, params=None):
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(sql, params or ())
            return cur.fetchall()
    finally:
        conn.close()


def get_records(search, limit):
    """One row per item:
    (ar_no, ar_date, customer, prod_code, prod_color, quantity, qty_unit, is_canceled, item_count)"""
    return _fetch("""
        SELECT h.ar_no, h.ar_date, h.customer, d.prod_code, d.prod_color,
               d.quantity, d.qty_unit, h.is_canceled, COALESCE(c.item_count, 0)
        FROM tbl_ar01 h
        LEFT JOIN tbl_ar02 d ON d.ar_no = h.ar_no
        LEFT JOIN (SELECT ar_no, COUNT(*) AS item_count
                   FROM tbl_ar02 GROUP BY ar_no) c ON c.ar_no = h.ar_no
        WHERE (%(q)s = ''
               OR CAST(h.ar_no AS TEXT) ILIKE %(like)s
               OR h.customer   ILIKE %(like)s
               OR d.prod_code  ILIKE %(like)s
               OR d.prod_color ILIKE %(like)s)
        ORDER BY h.ar_no DESC, d.sequence
        LIMIT %(limit)s
    """, {"q": search, "like": f"%{search}%", "limit": limit})


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