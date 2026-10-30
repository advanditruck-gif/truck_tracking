"""Copy SQLite events or an admin CSV export to the PostgreSQL database in DATABASE_URL."""
import argparse

import config
import db


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("sqlite_path", nargs="?", default=config.DB_PATH)
    args = parser.parse_args()

    if not config.DATABASE_URL:
        parser.error("Set DATABASE_URL to the Supabase PostgreSQL connection string first.")

    if args.sqlite_path.lower().endswith(".csv"):
        count = db.migrate_csv_to_postgres(args.sqlite_path)
    else:
        count = db.migrate_sqlite_to_postgres(args.sqlite_path)
    print(f"Imported {count} event(s) into Supabase.")


if __name__ == "__main__":
    main()
