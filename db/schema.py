from db.connection import get_connection


def create_table():
    con = get_connection()
    cursor = con.cursor()

    try:
        # 1. Roles
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS tbl_role(
                role_id SERIAL PRIMARY KEY,
                department VARCHAR(36) NOT NULL,
                role VARCHAR(10) NOT NULL,
                UNIQUE(department, role)
            )
        """)

        cursor.execute("""
            INSERT INTO tbl_role (department, role) VALUES 
                ('IT Department', 'ADMIN'),
                ('Laboratory Department', 'Head'),
                ('Laboratory Department', 'Staff'),
                ('Production Department', 'Viewer')
            ON CONFLICT (department, role) DO NOTHING; 
        """)

        cursor.execute("CREATE INDEX IF NOT EXISTS idx_role_department ON tbl_role(department);")

        # 2. Users
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS tbl_user(
                user_id SERIAL PRIMARY KEY,
                role_id INT NOT NULL,
                hostname VARCHAR(36),
                ip_address VARCHAR(32),
                username VARCHAR(50) NOT NULL,
                password VARCHAR(36) NOT NULL, 
                FOREIGN KEY (role_id) REFERENCES tbl_role(role_id)
            )
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_user_role_id ON tbl_user(role_id);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_user_hostname ON tbl_user(hostname);")
        cursor.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_user_username_unique ON tbl_user (LOWER(username));")

        # 3. MAC Address
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS tbl_mac_address(
                id SERIAL PRIMARY KEY,
                mac_address VARCHAR(32) UNIQUE,
                user_id INT UNIQUE,
                FOREIGN KEY (user_id) REFERENCES tbl_user(user_id)
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS tbl_ar01(
                id SERIAL PRIMARY KEY,
                ar_no INT NOT NULL UNIQUE,
                ar_date date,
                t_items INT,
                customer VARCHAR(128),
                encoded_by VARCHAR(128),
                updated_by VARCHAR(128),
                encoded_on TIMESTAMP, 
                updated_on TIMESTAMP, 
                user_id INT,
                is_canceled boolean,
                is_printed boolean,
                FOREIGN KEY (user_id) REFERENCES tbl_user(user_id)
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS tbl_ar02(
                id SERIAL PRIMARY KEY,
                ar_no INT NOT NULL,
                quantity DECIMAL(12,6),
                qty_unit VARCHAR(10),
                sequence INT,
                prod_code VARCHAR(128),
                prod_color VARCHAR(62),
                lot_no TEXT,
                notes TEXT, 
                FOREIGN KEY (ar_no) REFERENCES tbl_ar01(ar_no)
            )
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_ar02_ar_no ON tbl_ar02(ar_no);")

        # 5. Audit Trail
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS tbl_audit_trail(
                id SERIAL PRIMARY KEY,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                user_id INT,
                action_type VARCHAR(32),
                details TEXT,
                mac_id INT,
                FOREIGN KEY (user_id) REFERENCES tbl_user(user_id),
                FOREIGN KEY (mac_id) REFERENCES tbl_mac_address(id)
            )
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_audit_timestamp ON tbl_audit_trail(timestamp);")

        con.commit()

    except Exception as e:
        con.rollback()
        print(f"Error creating tables: {e}")
    finally:
        cursor.close()
        con.close()