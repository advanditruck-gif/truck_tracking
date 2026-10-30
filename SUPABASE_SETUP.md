# Supabase setup

The Flask server connects directly to Supabase PostgreSQL for event records and
uses a private Supabase Storage bucket for captured JPEGs. Browser code must
never receive a database password or a Supabase secret/service-role key.

## Configure Supabase

1. In Supabase, open **Project Settings → Database → Connect** and copy a
   PostgreSQL connection string supported by Render. Use the session pooler if
   the direct connection is unavailable. The app requires SSL.
2. In **Storage**, create a **private** bucket named `truck-tracker-images`.
   This is the default bucket name; `SUPABASE_STORAGE_BUCKET` can override it.
3. In **Project Settings → API Keys**, copy the server-only secret key (or the
   legacy `service_role` key). Do not use the publishable/anon key for storage.

## Configure Render

In the service's **Environment** settings, add:

| Key | Value |
| --- | --- |
| `DATABASE_URL` | Supabase PostgreSQL connection string |
| `SUPABASE_URL` | Project URL |
| `SUPABASE_SECRET_KEY` | Server-only Supabase secret key |

`SUPABASE_SERVICE_ROLE_KEY` is also accepted instead of `SUPABASE_SECRET_KEY`.
Save the variables and deploy the latest repository commit. The app creates
`public.events` if it does not already exist. Event details, including the
private Storage object path for each new image, are stored in that table.

The `SUPABASE_KEY` publishable key is not used by this server-side integration.
Do not expose a secret key or `DATABASE_URL` in frontend code or commit either
value to Git.

## Migrate existing event records

Back up the SQLite database first. Set `DATABASE_URL` in the local, ignored
`.env` file, install project requirements, then run:

```powershell
py -m pip install -r requirements.txt
py migrate_to_supabase.py tracker.db
```

Alternatively, pass a CSV downloaded from the admin page:

```powershell
py migrate_to_supabase.py "C:\path\to\truck-tracker-records.csv"
```

The migration preserves event IDs and reports conflicting destination rows.
Previously captured original photos cannot be migrated unless their image files
still exist; new camera captures are uploaded to the private bucket.
