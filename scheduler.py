from apscheduler.schedulers.background import BackgroundScheduler
from datetime import datetime
from app import database

def cleanup_expired_otps():
    try:
        with database() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "DELETE FROM otps WHERE expires_at_unix < %s",
                    (int(datetime.utcnow().timestamp()),)
                )
        print("Expired OTPs cleaned up.")
    except Exception as e:
        print(f"OTP cleanup error: {e}")

def start_scheduler():
    sched = BackgroundScheduler()
    sched.add_job(cleanup_expired_otps, 'interval', minutes=5)
    sched.start()
    print("OTP cleanup scheduler started.")
