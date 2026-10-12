import collections
import os
import traceback
import datetime

import dbfread
from dbfread import FieldParser
from PyQt6.QtCore import pyqtSignal, QObject, QCoreApplication
from sqlalchemy import text, create_engine

from db.connection import get_connection

# --- Database Connection Config ---
temp_conn = get_connection()
DB_CONFIG = {
    "host": temp_conn.info.host,
    "port": temp_conn.info.port,
    "dbname": temp_conn.info.dbname,
    "user": temp_conn.info.user,
    "password": temp_conn.info.password
}
temp_conn.close()

# --- DBF Legacy File Paths for AR ---
DBF_AR_BASE_PATH = r'\\System-server\mbpi ar\FORMS\DBINV-2'
AR_PRIMARY_DBF_PATH = os.path.join(DBF_AR_BASE_PATH, 'tbl_del01.dbf')
AR_SECONDARY_DBF_PATH = os.path.join(DBF_AR_BASE_PATH, 'tbl_del02.dbf')

try:
    db_url = f"postgresql+psycopg2://{DB_CONFIG['user']}:{DB_CONFIG['password']}@{DB_CONFIG['host']}:{DB_CONFIG['port']}/{DB_CONFIG['dbname']}"
    engine = create_engine(db_url, pool_pre_ping=True, pool_recycle=3600)
except Exception as e:
    print(f"CRITICAL: Could not create database engine for AR Sync. Error: {e}")


# --- Custom Safe DBF Parser to Handle Null Bytes (\x00) for Numbers, Dates, and Logicals ---
class SafeDBFParser(FieldParser):
    def parseN(self, field, data):
        """Safely parse numeric fields containing null bytes or spaces."""
        data = data.strip(b'*\x00 ')
        if not data:
            return None
        try:
            return int(data)
        except ValueError:
            try:
                return float(data.replace(b',', b'.'))
            except ValueError:
                return 0.0

    def parseD(self, field, data):
        """Safely parse date fields containing null bytes or spaces."""
        data = data.strip(b'\x00 ')
        if not data or len(data) < 8 or b'\x00' in data:
            return None
        try:
            return datetime.date(int(data[:4]), int(data[4:6]), int(data[6:8]))
        except (ValueError, TypeError):
            return None

    def parseL(self, field, data):
        """Safely parse logical fields containing null bytes or unexpected values."""
        if data in b'TtYy':
            return True
        elif data in b'FfNn':
            return False
        else:
            return None  # Defaults null bytes or corrupted flags to None


# --- Data Conversion Helpers ---

def _to_bool(value):
    if value is None: return False
    if isinstance(value, bool): return value
    v_str = str(value).strip().upper()
    if v_str in ('T', '.T.', 'Y', '1', 'TRUE', 'YES'): return True
    return False


def _to_float(value, default=0.0):
    if value is None: return default
    try:
        return float(value)
    except:
        return default


def _to_int(value, default=None):
    if value is None: return default
    try:
        return int(float(value))
    except:
        return default


def _to_str(value, default=''):
    if value is None: return default
    if isinstance(value, bytes):
        try:
            return value.decode('latin1').replace('\x00', '').strip() or default
        except:
            return default
    return str(value).replace('\x00', '').strip() or default


def _is_valid_date(d):
    if d is None: return False
    try:
        if isinstance(d, (datetime.date, datetime.datetime)): return d.year >= 1900
        s = str(d).strip()
        return bool(s) and not s.startswith('1899')
    except:
        return False


class SyncAR(QObject):
    finished = pyqtSignal(bool, str)
    progress = pyqtSignal(str)

    def run(self):
        try:
            dbf = dbfread.DBF(AR_SECONDARY_DBF_PATH, encoding='latin1', parserclass=SafeDBFParser)
            print(dbf.field_names)
            print(next(iter(dbf)))
            self.progress.emit("Phase 1/2: Reading AR secondary and primary records from DBF files...")

            # 1. READ AR SECONDARY ITEMS (tbl_del02.dbf)
            items_by_ar_no = collections.defaultdict(list)
            if os.path.exists(AR_SECONDARY_DBF_PATH):
                dbf_ar_items = dbfread.DBF(AR_SECONDARY_DBF_PATH, encoding='latin1', char_decode_errors='ignore',
                                           parserclass=SafeDBFParser)
                for item in dbf_ar_items:
                    if _to_bool(item.get('T_DELETED')): continue
                    ar_no = _to_int(item.get('T_DRNUM'))
                    if ar_no is None: continue

                    items_by_ar_no[ar_no].append({
                        "ar_no": ar_no,
                        "quantity": _to_float(item.get('T_WTPERPAC')),
                        "qty_unit": _to_str(item.get('T_UNITWT')),
                        "sequence": _to_int(item.get('T_SEQ')),
                        "prod_code": _to_str(item.get('T_PRODCODE')),
                        "prod_color": _to_str(item.get('T_PRODCOLO')),
                        "lot_no": _to_str(item.get('T_DESC1')),
                        "notes": _to_str(item.get('T_DESC2'))
                    })

            # 2. READ AR PRIMARY RECORDS (tbl_del01.dbf)
            primary_ar_recs = []
            if os.path.exists(AR_PRIMARY_DBF_PATH):
                dbf_primary_ar = dbfread.DBF(AR_PRIMARY_DBF_PATH, encoding='latin1',
                                             char_decode_errors='ignore', parserclass=SafeDBFParser)

                # Helper to find dictionary keys case-insensitively
                def get_field(record, *field_names):
                    """Case-insensitive lookup that tolerates DBF's 10-char field-name limit.
                    Returns the first non-empty match among field_names."""
                    lowered = {str(k).lower(): v for k, v in record.items()}
                    short = {k[:10]: v for k, v in lowered.items()}
                    for name in field_names:
                        n = name.lower()
                        v = lowered.get(n)
                        if v is None:
                            v = short.get(n[:10])
                        if v is not None and str(v).strip().strip('\x00') != '':
                            return v
                    return None

                for r in dbf_primary_ar:
                    # Exclude deleted records
                    if _to_bool(get_field(r, 'T_DELETED')): continue

                    ar_no = _to_int(get_field(r, 'T_DRNUM'))
                    if ar_no is None: continue

                    # Ignore records where ar_date has no value or is invalid
                    ar_date = get_field(r, 'T_DRDATE')
                    if not _is_valid_date(ar_date):
                        continue

                    # Safe extraction of encoded_on (checking both common variations)
                    encoded_on = get_field(r, 't_dencoded') or get_field(r, 'T_DENCODEDON')
                    if not _is_valid_date(encoded_on):
                        encoded_on = None

                    # Safe extraction of encoded_by (checking both common variations)
                    encoded_by_val = get_field(r, 't_encodedby') or get_field(r, 'T_ENCODEDBY')

                    primary_ar_recs.append({
                        "ar_no": ar_no,
                        "ar_date": ar_date,
                        "customer": _to_str(get_field(r, 'T_CUSTOMER'))[:128],
                        "t_items": _to_int(get_field(r, 'T_ITEMS')),
                        "encoded_by": _to_str(encoded_by_val)[:128],
                        "updated_by": None,
                        "encoded_on": encoded_on,
                        "updated_on": None,
                        "is_canceled": _to_bool(get_field(r, 'T_CANCEL')),
                        "is_printed": _to_bool(get_field(r, 'T_PRINTED'))
                    })

            if not primary_ar_recs:
                self.finished.emit(True, "Sync Info: No valid AR records found with dates.")
                return

            self.progress.emit("Phase 2/2: Synchronizing AR records to PostgreSQL...")
            with engine.connect() as conn:
                with conn.begin():
                    # --- AR HEADERS SYNC (UPSERT) ---
                    conn.execute(text("""
                        INSERT INTO tbl_ar01 (ar_no, ar_date, customer, t_items, encoded_by, updated_by, encoded_on, updated_on, is_canceled, is_printed)
                        VALUES (:ar_no, :ar_date, :customer, :t_items, :encoded_by, :updated_by, :encoded_on, :updated_on, :is_canceled, :is_printed)
                        ON CONFLICT (ar_no) DO UPDATE SET 
                            ar_date = EXCLUDED.ar_date,
                            customer = EXCLUDED.customer,
                            t_items = EXCLUDED.t_items,
                            encoded_by = EXCLUDED.encoded_by,
                            encoded_on = EXCLUDED.encoded_on,
                            is_canceled = EXCLUDED.is_canceled,
                            is_printed = EXCLUDED.is_printed;
                    """), primary_ar_recs)

                    # --- AR DETAILS SYNC (UPSERT) ---
                    all_ar_items = [item for r in primary_ar_recs for item in items_by_ar_no.get(r['ar_no'], [])]
                    if all_ar_items:
                        conn.execute(text("""
                            INSERT INTO tbl_ar02 (ar_no, quantity, qty_unit, sequence, prod_code, prod_color, lot_no, notes)
                            VALUES (:ar_no, :quantity, :qty_unit, :sequence, :prod_code, :prod_color, :lot_no, :notes)
                            ON CONFLICT DO NOTHING;
                        """), all_ar_items)

            self.finished.emit(True, "AR Legacy mirror completed successfully.")

        except Exception as e:
            traceback.print_exc()
            self.finished.emit(False, f"Critical AR Sync Error: {e}")


if __name__ == "__main__":
    app = QCoreApplication([])


    def on_progress(msg):
        print(f"[PROGRESS] {msg}")


    def on_finished(success, msg):
        print(f"\n[FINISHED] Success: {success} | Message: {msg}")
        app.quit()


    print("Initializing standalone AR Sync execution...")
    syncer = SyncAR()
    syncer.progress.connect(on_progress)
    syncer.finished.connect(on_finished)

    # Run the worker directly
    syncer.run()

    app.exec()