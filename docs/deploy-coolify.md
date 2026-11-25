# Deploying on Coolify

QC Manager runs on Coolify as one **Docker Compose** resource built from this repository, using
[`docker-compose.coolify.yml`](../docker-compose.coolify.yml). Coolify builds the images, puts the
site behind its proxy with an HTTPS certificate, generates the database, Redis and secret-key
passwords, and redeploys when `main` changes.

What runs:

| Service | What it does |
|---|---|
| `web` | nginx serving the app and forwarding `/api` to the API. The only service on the internet. |
| `api` | The FastAPI backend (1 worker by default, about 600 MB; raise `API_WORKERS` on a bigger server). |
| `worker`, `scheduler` | Background jobs and scheduled jobs (mail, Entra sync, reports). |
| `db` | PostgreSQL 16, data on the `pgdata` volume. |
| `redis` | Sessions, cache, rate limits and the job queue, password protected, on the `redisdata` volume. |
| `migrate` | Runs on every deploy: applies database migrations, then exits. |
| `bootstrap` | Runs on every deploy: creates the first administrator if it doesn't exist yet, then exits. |

Uploaded files are kept on the `files` volume, shared by `api` and `worker`.

## 1. Before you start

You need:

- A domain or subdomain for the app (for example `qc.yourcompany.com.au`) with a DNS **A record**
  pointing at your Coolify server.
- An **SMTP account** for outgoing mail (Microsoft 365, SendGrid, Mailgun, Amazon SES…).
  Production refuses to start without one, because password-reset and invitation links must be
  e-mailed, never written to the log.
- Optional: a Microsoft Entra app registration for staff sign-in ([entra-setup.md](entra-setup.md)).

## 2. Create the resource

1. In Coolify, open your project and environment, then choose **+ New → Public/Private Repository**
   (use **Private Repository (with GitHub App)** for this private repo).
2. Select this repository and the branch `main`.
3. Under **Build Pack**, choose **Docker Compose**.
4. Set **Docker Compose Location** to `/docker-compose.coolify.yml` and **Base Directory** to `/`.
5. Save. Coolify reads the file and lists the services.

## 3. Domain

Open the **web** service and set its **Domain** to your address with `https://`, for example
`https://qc.yourcompany.com.au`. Coolify requests the certificate. The other services need no
domain. They are only reachable inside the stack.

## 4. Environment variables

Open **Environment Variables**. Coolify has already filled in `SERVICE_URL_WEB` (the full `https://` address of the domain)
and the generated passwords: `SERVICE_PASSWORD_POSTGRES`, `SERVICE_PASSWORD_REDIS` and
`SERVICE_PASSWORD_64_SECRETKEY`. Leave those alone.

Set the required ones. Coolify won't deploy until they have values:

| Variable | Example | Notes |
|---|---|---|
| `ADMIN_EMAIL` | `you@yourcompany.com.au` | The break-glass administrator's e-mail |
| `ADMIN_PASSWORD` | (your choice) | Needs upper and lower case, a number and a special character. Mark it **secret**. |
| `EMAIL_FROM` | `qc-manager@yourcompany.com.au` | Sender address for all mail |
| `EMAIL_SMTP_HOST` | `smtp.office365.com` | Your SMTP server |

Usually also needed:

| Variable | Default | Notes |
|---|---|---|
| `EMAIL_SMTP_PORT` | `587` | |
| `EMAIL_SMTP_USER` / `EMAIL_SMTP_PASSWORD` | empty | SMTP login. Mark the password **secret**. |
| `ADMIN_USERNAME` | `admin` | |
| `OAUTH_ENTRA_TENANT_ID`, `OAUTH_ENTRA_CLIENT_ID`, `OAUTH_ENTRA_CLIENT_SECRET` | empty | Staff sign-in with Microsoft. The redirect URI to register is `https://<your domain>/api/v1/auth/oauth/callback/entra` (see [entra-setup.md](entra-setup.md)). |
| `MODULES_DISABLED` | empty | Modules to switch off, e.g. `cvr,portal` |
| `API_WORKERS` | `1` | Each worker needs about 600 MB of memory. Raise it only when the server has the RAM to spare. |

## 5. Deploy

Click **Deploy**. The first build takes a few minutes. Coolify then starts the services in order:

1. `db` and `redis` come up first.
2. Once the database is ready, `migrate` builds the schema and `bootstrap` creates the administrator.
3. `api` starts, then `worker`, `scheduler` and `web`.

Open your domain and sign in with `ADMIN_USERNAME` / `ADMIN_PASSWORD`. Optionally load the demo
project from the **api** service's **Terminal** in Coolify:

```bash
cd /app && python -m scripts.seed_demo
```

## 6. Updates, backups and logs

- **Updates:** enable **Auto Deploy** on the resource (GitHub App) so a merge to `main` redeploys.
  Every deploy runs `migrate` first, and the API only starts after the migrations succeed.
- **Backups:** back up the database with Coolify's scheduled backups, or from the **db** service
  terminal with `pg_dump -U qcmanager qc_manager`. Also back up the `files` volume, which holds
  the uploaded documents and photos. The `redisdata` volume holds only sessions and queued jobs.
- **Logs:** each service's **Logs** tab. At startup the API logs warnings that Redis isn't using
  TLS. That's expected here, because Redis is reachable only on the stack's private network.
- **Startup refusals:** the API refuses to start in production with unsafe settings and logs why.
  Examples are a site address on `localhost` or plain `http`, or console mail. Fix the variable and
  redeploy.

## If you see "502 Bad Gateway"

The 502 page comes from the `web` container's nginx: it couldn't get an answer from `api`. The
usual causes, in order:

1. **The API ran out of memory and was killed mid-request.** Open the **api** service's logs. A
   restart right after the failing request, or `Killed`, means the server is short of memory.
   Check the server's free memory in Coolify. Keep `API_WORKERS` at `1`, which uses about 600 MB.
   The whole stack needs about 1.3 GB, plus whatever Coolify and your other apps use.
2. **The API isn't running.** Look for a startup refusal in the api logs (see above), fix the
   variable and redeploy.

nginx looks up the API's address on every request, so once the API is back the site recovers by
itself. You don't need to restart `web`.

## Notes

- Requests reach the API through two proxies (Coolify's proxy, then nginx), so the stack sets
  `TRUSTED_PROXY_HOPS=2`. Login lockouts and rate limits then see the real client address.
- `exclude_from_hc` on the one-off and background services is a Coolify key. It stops Coolify
  from reporting the stack as unhealthy when `migrate` and `bootstrap` exit after doing their
  job. Plain `docker compose` doesn't know the key; for local development use
  `docker-compose.yml`.
