# Configuration

The backend reads environment variables, and a `backend/.env` file when there is one. Create that file from the block below; it is ignored by git.

```ini
ENVIRONMENT=development
APP_NAME=QC Manager
# python -c "import secrets; print(secrets.token_urlsafe(48))"
SECRET_KEY=

# Database and Redis (docker-compose.yml provides both)
POSTGRES_USER=postgres
POSTGRES_PASSWORD=postgres
POSTGRES_SERVER=localhost
POSTGRES_PORT=5432
POSTGRES_DB=qc_manager
CACHE_REDIS_HOST=localhost
CACHE_REDIS_PORT=6379

# Where the app is served. The SPA and the API share one origin:
# Vite proxies /api in development, nginx in production.
FRONTEND_URL=http://localhost:5173
OAUTH_REDIRECT_BASE_URL=http://localhost:5173
OAUTH_DEFAULT_REDIRECT=/sign-in
CORS_ORIGINS=http://localhost:5173
# true wherever the app is served over https
SESSION_SECURE_COOKIES=false

# Microsoft Entra ID, for staff. See entra-setup.md
OAUTH_ENTRA_TENANT_ID=
OAUTH_ENTRA_CLIENT_ID=
OAUTH_ENTRA_CLIENT_SECRET=
OAUTH_ENTRA_GROUPS_CLAIM=true

# External users. Accounts come from invitations, not self-signup.
LOCAL_SIGNUP_ENABLED=false
# console prints emails to the API log; smtp for real deployments
EMAIL_BACKEND=console
EMAIL_FROM=no-reply@example.com
# EMAIL_SMTP_HOST=
# EMAIL_SMTP_PORT=587
# EMAIL_SMTP_USER=
# EMAIL_SMTP_PASSWORD=

# Business modules to switch off, e.g. cvr,portal
MODULES_DISABLED=

# Break-glass local administrator, created by scripts/create_first_superuser.py
ADMIN_NAME=Local Admin
ADMIN_EMAIL=admin@example.com
ADMIN_USERNAME=admin
ADMIN_PASSWORD=
# the SQLAdmin panel at /admin
ADMIN_ENABLED=false
```

Keep each comment on its own line: text after a value becomes part of it.

Everything else Fastro offers (session timeouts, login lockout, password policy, rate limits, cache, Taskiq broker) is listed in `backend/src/infrastructure/*/settings.py` and `backend/src/infrastructure/config/base.py`, each with its default.

## Production checklist

- `ENVIRONMENT=production`: the app refuses to start with a weak `SECRET_KEY` or other unsafe settings, and migrations need `CONFIRM_PRODUCTION_MIGRATION=yes`.
- `SESSION_SECURE_COOKIES=true`, served over https only.
- `TRUSTED_PROXY_HOPS=1` behind one reverse proxy, so login lockout sees the real client address.
- `EMAIL_BACKEND=smtp`, or invitations never arrive.
- Run the worker and the scheduler alongside the API (Graph sync, email delivery).
- Secrets (`SECRET_KEY`, `OAUTH_ENTRA_CLIENT_SECRET`, database and SMTP passwords) come from your secret store, not files in the image.
