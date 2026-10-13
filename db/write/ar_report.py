from db.connection import get_connection

_INSERT_ITEM = """
    INSERT INTO tbl_ar02 (ar_no, quantity, qty_unit, sequence, prod_code, prod_color, lot_no, notes)
    VALUES (%(ar_no)s, %(quantity)s, %(qty_unit)s, %(sequence)s,
            %(prod_code)s, %(prod_color)s, %(lot_no)s, %(notes)s)
"""


def create_receipt(header, items):
    """header: ar_date, customer, t_items, user. Returns the new ar_no."""
    conn = get_connection()
    try:
        conn.autocommit = False
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO tbl_ar01 (ar_no, ar_date, customer, t_items, encoded_by,
                                      encoded_on, is_canceled, is_printed)
                SELECT COALESCE(MAX(ar_no), 0) + 1, %(ar_date)s::date, %(customer)s::varchar,
                       %(t_items)s::int, %(user)s::varchar, NOW(), FALSE, FALSE
                FROM tbl_ar01
                RETURNING ar_no
            """, header)
            ar_no = cur.fetchone()[0]
            cur.executemany(_INSERT_ITEM, [dict(i, ar_no=ar_no) for i in items])
        conn.commit()
        return ar_no
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def update_receipt(ar_no, header, items):
    """Update the header and replace all items of an existing receipt."""
    conn = get_connection()
    try:
        conn.autocommit = False
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE tbl_ar01
                SET ar_date = %(ar_date)s, customer = %(customer)s, t_items = %(t_items)s,
                    updated_by = %(user)s, updated_on = NOW()
                WHERE ar_no = %(ar_no)s
            """, dict(header, ar_no=ar_no))
            cur.execute("DELETE FROM tbl_ar02 WHERE ar_no = %s", (ar_no,))
            cur.executemany(_INSERT_ITEM, [dict(i, ar_no=ar_no) for i in items])
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()