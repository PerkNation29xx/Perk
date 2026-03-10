from sqlalchemy import text
from sqlalchemy.engine import Engine


def run_migrations(engine: Engine) -> None:
    """
    Minimal, SQLite-only migrations for this MVP.

    NOTE: In production you should use Alembic migrations instead.
    """

    driver = engine.url.drivername
    if driver.startswith("sqlite"):
        with engine.begin() as conn:
            # If the table doesn't exist yet, create_all() will create it with the
            # latest schema and we can skip.
            try:
                rows = conn.execute(text("PRAGMA table_info(users)")).fetchall()
            except Exception:
                return

            existing_columns = {row[1] for row in rows}  # 2nd column is "name"
            if not existing_columns:
                return

            added_email_verified = False

            if "email_verified" not in existing_columns:
                conn.execute(text("ALTER TABLE users ADD COLUMN email_verified BOOLEAN NOT NULL DEFAULT 0"))
                added_email_verified = True

            if "email_verification_code_hash" not in existing_columns:
                conn.execute(text("ALTER TABLE users ADD COLUMN email_verification_code_hash VARCHAR(64)"))

            if "email_verification_expires_at" not in existing_columns:
                conn.execute(text("ALTER TABLE users ADD COLUMN email_verification_expires_at DATETIME"))

            if "supabase_user_id" not in existing_columns:
                conn.execute(text("ALTER TABLE users ADD COLUMN supabase_user_id VARCHAR(36)"))

            if "alert_radius_miles" not in existing_columns:
                conn.execute(text("ALTER TABLE users ADD COLUMN alert_radius_miles INTEGER NOT NULL DEFAULT 5"))

            if "notification_categories" not in existing_columns:
                conn.execute(text("ALTER TABLE users ADD COLUMN notification_categories TEXT"))

            # Any existing users predate email-verification; mark them verified so
            # we don't lock out seeded/demo accounts.
            if added_email_verified:
                conn.execute(text("UPDATE users SET email_verified = 1"))

            # Merchant profile fields.
            try:
                rows = conn.execute(text("PRAGMA table_info(merchant_profiles)")).fetchall()
            except Exception:
                return

            merchant_cols = {row[1] for row in rows}
            if merchant_cols and "logo_url" not in merchant_cols:
                conn.execute(text("ALTER TABLE merchant_profiles ADD COLUMN logo_url VARCHAR(255)"))

        return

    # Postgres / Supabase migrations.
    if driver.startswith("postgresql"):
        with engine.begin() as conn:
            table = conn.execute(text("SELECT to_regclass('public.users')")).scalar()
            if not table:
                return

            rows = conn.execute(
                text(
                    """
                    SELECT column_name, is_nullable
                    FROM information_schema.columns
                    WHERE table_schema = 'public' AND table_name = 'users'
                    """
                )
            ).fetchall()
            cols = {r[0]: r[1] for r in rows}

            if "supabase_user_id" not in cols:
                conn.execute(text("ALTER TABLE users ADD COLUMN supabase_user_id VARCHAR(36)"))
                conn.execute(
                    text(
                        "CREATE UNIQUE INDEX IF NOT EXISTS ix_users_supabase_user_id ON users(supabase_user_id)"
                    )
                )

            if "alert_radius_miles" not in cols:
                conn.execute(text("ALTER TABLE users ADD COLUMN alert_radius_miles INTEGER NOT NULL DEFAULT 5"))

            if "notification_categories" not in cols:
                conn.execute(text("ALTER TABLE users ADD COLUMN notification_categories TEXT"))

            # Allow password_hash to be null when Supabase Auth is used.
            if cols.get("password_hash") == "NO":
                conn.execute(text("ALTER TABLE users ALTER COLUMN password_hash DROP NOT NULL"))

            # Merchant profile fields.
            merchant_table = conn.execute(text("SELECT to_regclass('public.merchant_profiles')")).scalar()
            if merchant_table:
                rows = conn.execute(
                    text(
                        """
                        SELECT column_name
                        FROM information_schema.columns
                        WHERE table_schema = 'public' AND table_name = 'merchant_profiles'
                        """
                    )
                ).fetchall()
                merchant_cols = {r[0] for r in rows}
                if "logo_url" not in merchant_cols:
                    conn.execute(text("ALTER TABLE merchant_profiles ADD COLUMN logo_url VARCHAR(255)"))

        return

    # Unknown database type: no-op.
    return
