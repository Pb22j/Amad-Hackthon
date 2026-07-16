import os
import psycopg
from pathlib import Path
from decimal import Decimal
from datetime import datetime, timezone, timedelta
from uuid import NAMESPACE_URL, uuid5

# Import helper from the existing seed script
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))
from scripts.seed_postgres import _password_hash, _date, _email, _phone, seed_financial_data, DEMO_HASH

DATABASE_URL = "postgresql://amad:development-only-password@localhost:55432/amad"
now = datetime.now(timezone.utc)

def reset_and_seed():
    demo_accounts = [
        ("3f1f7a3e-8d1e-4a67-9f7d-2b6f3a1c9e01", "khalid", "خالد عبدالعزيز السالم", "1990-05-15", "Male", "مصرف الإنماء", "SA4405000068201234567890", "حساب جاري", "125000.00", "20000", "khalid@amad.sa", "+966500000001", "12345678"),
        ("7c3d9f81-2e5a-4b18-9d64-1f8e6a2c4b05", "sara", "سارة محمد النصار", "1994-08-22", "Female", "بنك الرياض", "SA0320000005556667772222", "حساب ادخار", "85400.50", "10000", "sara@amad.sa", "+966500000002", "12345678"),
        ("9d2c5b74-6a0f-4e3b-8c11-5e9a7d4f2b02", "fahad", "فهد ناصر القحطاني", "1988-11-30", "Male", "البنك الأهلي", "SA1545000003334445553333", "حساب جاري", "3420.00", "5000", "fahad@amad.sa", "+966500000003", "12345678"),
        ("5a8e1c29-3b7d-4f56-a0e2-7c4d9b8e6f03", "noura", "نورة سلطان الحربي", "1997-02-14", "Female", "مصرف الراجحي", "SA6015000078965432101234", "حساب جاري", "19750.00", "15000", "noura@amad.sa", "+966500000004", "12345678"),
        ("1a2b3c4d-5e6f-7a8b-9c0d-1e2f3a4b5c6d", "yousef", "يوسف عمر العتيبي", "1985-01-10", "Male", "بنك البلاد", "SA7015000078965432101234", "حساب جاري", "500.00", "2000", "yousef@amad.sa", "+966500000005", "12345678"),
        ("f1e2d3c4-b5a6-9f8e-7d6c-5b4a3f2e1d0c", "maha", "مها طارق الدوسري", "1999-09-09", "Female", "البنك السعودي الأول", "SA8015000078965432101234", "حساب جاري", "54300.00", "10000", "maha@amad.sa", "+966500000006", "12345678"),
    ]

    try:
        with psycopg.connect(DATABASE_URL) as conn:
            with conn.cursor() as cur:
                print("Truncating tables...")
                cur.execute("TRUNCATE platform_users, users, beneficiaries, transactions, investment_holdings, investment_assets, qattas, qatta_bills, fatoorahs, checkpoint_writes, checkpoint_blobs, checkpoints CASCADE;")
                
                ids = {}
                print("Inserting 6 clean accounts...")
                for index, item in enumerate(demo_accounts, start=1):
                    uid, username, name, dob, gender, bank, account, account_type, balance, limit, email, phone, pwd = item
                    
                    # Insert into platform_users
                    cur.execute(
                        """INSERT INTO platform_users
                           (id, username, full_name, email, password_hash, phone_e164, country_code,
                            city, role, preferred_language, timezone, verified, status,
                            last_login_at, created_at, updated_at)
                           VALUES (%s,%s,%s,%s,%s,%s,'SA','Riyadh','user','ar','Asia/Riyadh',true,'active',%s,%s,%s)""",
                        (index, username, name, email, _password_hash(pwd, username), phone, now, now, now)
                    )
                    
                    # Insert into bank users
                    cur.execute(
                        """INSERT INTO users
                           (uuid,tenant_id,username,source_username,full_name_ar,dateofbirth,gender,email,
                            phone_e164,bank_name_ar,account_number,account_type_ar,balance_sar,
                            available_balance_sar,daily_spend_limit_sar,hashedpassword,status,nafath_linked,
                            kyc_status,kyc_tier,risk_rating,last_login_at,createdat,updatedat)
                           VALUES (%s,'evaluation-tenant',%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,
                                   'active','Yes','verified',2,'low',%s,%s,%s)""",
                        (uid, username, username, name, _date(dob), gender, email, phone,
                         bank, account, account_type, Decimal(balance), Decimal(balance), Decimal(limit), _password_hash(pwd, username),
                         now - timedelta(days=2), now - timedelta(days=300), now)
                    )
                    ids[username] = uid

                print("Seeding financial transactions and bills...")
                # The seed_financial_data relies on the active users in DB.
                counts = seed_financial_data(conn, ids)
                print("Seeding complete! Counts:", counts)
                
            conn.commit()
    except Exception as e:
        print("Error:", e)

if __name__ == "__main__":
    reset_and_seed()
