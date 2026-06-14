# AMS-DIU — Docker Deployment Guide (VPS)

This guide deploys all three apps to a single VPS with Docker, each on its own
subdomain, with automatic HTTPS (Let's Encrypt). The PostgreSQL database lives
in a persistent Docker volume and is **never removed by a deploy**.

| App                | Repo                | Subdomain                    | Internal port |
|--------------------|---------------------|------------------------------|---------------|
| Backend (Django)   | `ams-diu-backend`   | https://api.tatomal.me       | 8000          |
| Admin (Vite/React) | `ams-diu-frontend`  | https://admin.tatomal.me     | 80            |
| Student (Next.js)  | `ams-diu-student`   | https://student.tatomal.me   | 3000          |

## Architecture

```
                         Internet (ports 80/443)
                                  │
                       ┌──────────▼───────────┐
                       │     nginx-proxy      │  ← shared, auto-routes by VIRTUAL_HOST
                       │   + acme-companion   │  ← issues/renews Let's Encrypt certs
                       └──────────┬───────────┘
              ┌───────────────────┼────────────────────┐
              │                   │                     │
   api.tatomal.me        admin.tatomal.me      student.tatomal.me
       (web)                 (admin)               (student)
        │
   ┌────▼────┐
   │ postgres│  ← volume "pgdata" (persistent, survives every deploy)
   └─────────┘
```

All containers share an external Docker network called **`web`**. Each app
container simply declares `VIRTUAL_HOST` / `LETSENCRYPT_HOST` and the proxy
discovers and routes to it — so each repo deploys completely independently.

---

## 0. Prerequisites (once)

- Docker Engine + the Docker Compose plugin installed on the VPS.
  Check with: `docker --version` and `docker compose version`.
- **DNS A records** all pointing to your VPS public IP:
  - `api.tatomal.me`
  - `admin.tatomal.me`
  - `student.tatomal.me`
  - (SSL issuance will fail until DNS resolves to this server.)
- Ports **80** and **443** open in the VPS firewall.
- Your repos cloned via the deploy key, e.g. under `~/apps/`:
  ```
  ~/apps/ams-diu-backend
  ~/apps/ams-diu-frontend
  ~/apps/ams-diu-student
  ```

---

## 1. First-time setup (run ONCE)

Start the shared reverse proxy + SSL. Do this from the **backend** repo:

```bash
cd ~/apps/ams-diu-backend
cp .env.example .env
nano .env                 # set SECRET_KEY, DB_PASSWORD, LETSENCRYPT_EMAIL, etc.
./setup.sh                # creates the 'web' network + starts nginx-proxy + acme
```

Generate a Django secret key for the `.env`:
```bash
python3 -c "import secrets; print(secrets.token_urlsafe(50))"
```

---

## 2. Deploy each app

Run each app's `deploy.sh` from inside its own repo. Order: backend first
(so the API and DB exist), then the two frontends — but they are independent
and can each be re-run any time.

### Backend
```bash
cd ~/apps/ams-diu-backend
# .env already created in step 1
./deploy.sh
```
The web container automatically runs `migrate` and `collectstatic` on start.
Create the first admin user:
```bash
docker compose exec web sh -c 'cd amsapp && python manage.py createsuperuser'
```

### Admin frontend
```bash
cd ~/apps/ams-diu-frontend
cp .env.example .env       # set LETSENCRYPT_EMAIL (domain default is fine)
./deploy.sh
```

### Student frontend
```bash
cd ~/apps/ams-diu-student
cp .env.example .env       # set LETSENCRYPT_EMAIL (domain default is fine)
./deploy.sh
```

First HTTPS request per domain may take ~30–60s while the certificate is
issued. Watch progress with: `docker logs -f acme-companion`.

---

## 3. Redeploying after a code change (your CI/CD step)

On every release, just pull + rebuild — **the database is untouched**:

```bash
cd ~/apps/ams-diu-backend  && ./deploy.sh   # or whichever repo changed
```

`deploy.sh` does: `git pull` → `docker compose up -d --build` → prune dangling
images. It **never** runs `down -v`, so the `pgdata` volume (your database)
always persists.

> Want it fully automatic on `git push`? See "Auto-deploy on push" below.

---

## 4. Common operations

```bash
# Logs
docker compose logs -f web            # (from a repo dir)
docker logs -f nginx-proxy

# Restart one app
cd ~/apps/ams-diu-backend && docker compose restart web

# Django shell / management commands
docker compose exec web sh -c 'cd amsapp && python manage.py <cmd>'

# Database backup (recommended before risky migrations)
docker exec ams-postgres pg_dump -U "$DB_USER" "$DB_NAME" > backup_$(date +%F).sql
# Restore:
cat backup.sql | docker exec -i ams-postgres psql -U "$DB_USER" -d "$DB_NAME"
```

> Use the `DB_USER` / `DB_NAME` values from your backend `.env`.

---

## 5. Auto-deploy on push (optional CI/CD)

Two simple options:

**A. Cron poll** — add to crontab on the VPS to redeploy when the remote moves:
```cron
*/5 * * * * cd ~/apps/ams-diu-backend && git fetch && \
  [ "$(git rev-parse HEAD)" != "$(git rev-parse @{u})" ] && ./deploy.sh >> deploy.log 2>&1
```

**B. GitHub Actions over SSH** — add a workflow in each repo that SSHes in and
runs `cd ~/apps/<repo> && ./deploy.sh`. Requires adding the VPS SSH key as a
repo secret. (The existing `.github/workflows/deploy.yml` targets Render; keep
or replace it as you prefer.)

---

## Safety notes

- **Never run `docker compose down -v`** in the backend repo — `-v` deletes the
  `pgdata` volume (your whole database). Plain `down` (no `-v`) is safe.
- `.env` files are git-ignored, so secrets and DB credentials survive deploys
  and are never committed.
- To change the DB password later, update `.env` **and** the existing role in
  postgres (the password is only applied at first volume creation).
