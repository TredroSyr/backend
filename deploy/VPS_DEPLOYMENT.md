# Tredro backend: single-VPS production deployment

This runbook deploys the API as the following stack:

- Caddy terminates HTTPS on ports 80 and 443.
- Gunicorn serves Django only on the private Docker network.
- PostgreSQL and Redis are not published to the host or internet.
- A one-shot `init` service applies migrations, seeds reference data, and
  collects static files before application services start.
- Celery worker and beat run independently from the web process.
- PostgreSQL, Redis, uploaded media, static files, Celery beat state, and Caddy
  certificates use persistent Docker volumes.

The examples assume Ubuntu 24.04 LTS, the repository directory
`/srv/tredro/backend`, and the API hostname `api.tredro.online`. Replace these
values if the VPS uses a different distribution, path, or hostname.

## 1. Prepare DNS before deployment

Create an `A` record:

```text
api.tredro.online -> YOUR_VPS_PUBLIC_IPV4
```

Only create an `AAAA` record if IPv6 is correctly configured on the VPS. A
wrong `AAAA` record can prevent certificate issuance for some clients. If the
domain uses Cloudflare, use **DNS only** until Caddy has obtained its first
certificate; the proxy can be enabled afterward if wanted.

Verify from your computer:

```bash
dig +short A api.tredro.online
dig +short AAAA api.tredro.online
```

## 2. Secure the new server

Log in with the temporary root credentials from the provider, update packages,
and create a named administrator account. Replace `deploy` if desired.

```bash
apt update
apt full-upgrade -y
apt install -y ca-certificates curl git ufw unattended-upgrades
adduser deploy
usermod -aG sudo deploy
install -d -m 700 -o deploy -g deploy /home/deploy/.ssh
cp /root/.ssh/authorized_keys /home/deploy/.ssh/authorized_keys
chown deploy:deploy /home/deploy/.ssh/authorized_keys
chmod 600 /home/deploy/.ssh/authorized_keys
```

Open a second terminal and prove that `ssh deploy@YOUR_VPS_IP` works before
changing SSH settings. Then use `/etc/ssh/sshd_config.d/99-hardening.conf`:

```text
PermitRootLogin no
PasswordAuthentication no
PubkeyAuthentication yes
```

Validate and reload SSH:

```bash
sudo sshd -t
sudo systemctl reload ssh
```

Enable the firewall only after allowing the actual SSH port:

```bash
sudo ufw allow OpenSSH
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw allow 443/udp
sudo ufw enable
sudo ufw status verbose
```

The Compose stack publishes only Caddy. Do not publish PostgreSQL 5432, Redis
6379, or Gunicorn 8000.

## 3. Install Docker Engine and Compose

Use Docker's official Ubuntu repository:

```bash
sudo install -m 0755 -d /etc/apt/keyrings
sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
sudo chmod a+r /etc/apt/keyrings/docker.asc

echo "Types: deb
URIs: https://download.docker.com/linux/ubuntu
Suites: $(. /etc/os-release && echo "${UBUNTU_CODENAME:-$VERSION_CODENAME}")
Components: stable
Architectures: $(dpkg --print-architecture)
Signed-By: /etc/apt/keyrings/docker.asc" | sudo tee /etc/apt/sources.list.d/docker.sources

sudo apt update
sudo apt install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
sudo systemctl enable --now docker
sudo usermod -aG docker deploy
```

Log out and back in so the group change applies, then verify:

```bash
docker version
docker compose version
docker run --rm hello-world
```

Membership in the `docker` group is effectively root-level access. Only add
trusted server administrators.

## 4. Clone a production revision

Deploy releases from `main` (or an immutable tag), not from a developer's
working directory. For a private GitHub repository, configure a read-only
deploy key first.

```bash
sudo install -d -m 0750 -o deploy -g deploy /srv/tredro
cd /srv/tredro
git clone --branch main https://github.com/TredroSyr/backend.git backend
cd /srv/tredro/backend
git status
git log -1 --oneline
```

The currently inspected local working branch is `dev`; merge and test the
deployment changes on `main` before using the command above. If the first
release intentionally comes from `dev`, replace `--branch main` with
`--branch dev`, then move production to tagged/main releases afterward.

## 5. Create production secrets

Copy the template, lock its permissions, and edit it:

```bash
cp .env.example .env
chmod 600 .env
openssl rand -hex 64
openssl rand -hex 32
nano .env
```

Use the first random value for `DJANGO_SECRET_KEY` and the second for
`DATABASE_PASSWORD`. The important production values are:

```dotenv
DJANGO_SETTINGS_MODULE=config.settings.production
DJANGO_SECRET_KEY=PASTE_THE_128_HEX_CHARACTER_VALUE
DJANGO_DEBUG=False
DJANGO_ALLOWED_HOSTS=api.tredro.online
DJANGO_CORS_ALLOWED_ORIGINS=https://tredro-dashboard.vercel.app,https://tredro-mandoub.vercel.app,https://tredro.online,https://www.tredro.online,https://dashboard.tredro.online
DJANGO_CSRF_TRUSTED_ORIGINS=https://api.tredro.online

DATABASE_NAME=tredro
DATABASE_USER=tredro
DATABASE_PASSWORD=PASTE_THE_DATABASE_PASSWORD
DATABASE_HOST=postgres
DATABASE_PORT=5432

REDIS_URL=redis://redis:6379/0
CELERY_BROKER_URL=redis://redis:6379/0
CELERY_RESULT_BACKEND=redis://redis:6379/0

GUNICORN_BIND=0.0.0.0:8000
GUNICORN_WORKERS=5
GUNICORN_TIMEOUT=60
CELERY_WORKER_CONCURRENCY=2
API_DOMAIN=api.tredro.online

DJANGO_SECURE_SSL_REDIRECT=True
DJANGO_SECURE_HSTS_SECONDS=0
DJANGO_SECURE_HSTS_INCLUDE_SUBDOMAINS=False
DJANGO_SECURE_HSTS_PRELOAD=False
```

CORS origins must match real frontend origins exactly and must not have a
trailing slash. Remove origins that are not in use. Never copy the local `.env`
to the server and never commit the production `.env`.

The old PgAdmin password in `.env.example` was public configuration. Rotate it
anywhere it was reused. PgAdmin is not included in production; use an SSH
tunnel and a short-lived administrative container if direct database access is
ever necessary.

## 6. Validate and launch

Render the configuration without printing resolved secrets, build the image,
and start the stack:

```bash
docker compose -f docker-compose.prod.yml config --quiet
docker compose -f docker-compose.prod.yml build
docker compose -f docker-compose.prod.yml up -d
docker compose -f docker-compose.prod.yml ps -a
docker compose -f docker-compose.prod.yml logs init
```

The `init` container should show migrations, seed commands, and `collectstatic`,
then exit with code 0. The other services should be running or healthy. Inspect
logs if not:

```bash
docker compose -f docker-compose.prod.yml logs --tail=200 backend caddy postgres redis celery celery-beat
```

Run Django's production checks and create the first administrator:

```bash
docker compose -f docker-compose.prod.yml exec backend python manage.py check --deploy
docker compose -f docker-compose.prod.yml exec backend python manage.py createsuperuser
```

Verify locally on the VPS and then through public TLS:

```bash
docker compose -f docker-compose.prod.yml exec backend \
  curl --fail \
  --header 'Host: api.tredro.online' \
  --header 'X-Forwarded-Proto: https' \
  http://localhost:8000/api/health/
curl --fail --show-error https://api.tredro.online/api/health/
curl -I https://api.tredro.online/admin/login/
```

Expected API response:

```json
{"status":"ok"}
```

After HTTPS has worked reliably, set `DJANGO_SECURE_HSTS_SECONDS=3600`, deploy,
observe it, and only later raise it to `31536000`. Do not enable HSTS preload or
include-subdomains unless every subdomain is permanently HTTPS-ready.

## 7. Routine deployments

Back up first, then fast-forward to a reviewed production revision:

```bash
cd /srv/tredro/backend
git fetch --prune origin
git checkout main
git pull --ff-only origin main
docker compose -f docker-compose.prod.yml config --quiet
docker compose -f docker-compose.prod.yml build
docker compose -f docker-compose.prod.yml up -d --remove-orphans
docker compose -f docker-compose.prod.yml ps -a
curl --fail --show-error https://api.tredro.online/api/health/
```

Because the image changes, Compose recreates the one-shot `init` service before
starting the new application containers. Read its logs on every release:

```bash
docker compose -f docker-compose.prod.yml logs init
```

Use tagged releases or record the deployed commit. A code rollback is:

```bash
git checkout THE_PREVIOUS_TESTED_TAG_OR_COMMIT
docker compose -f docker-compose.prod.yml up -d --build --remove-orphans
```

Database migrations are not automatically reversible. For destructive schema
changes, take a fresh backup and define the rollback migration before release.

## 8. Backups

At minimum, back up PostgreSQL and the media volume daily, retain multiple
generations, and copy them off the VPS. A disk snapshot alone is not a database
backup.

Create a private backup directory owned by the deployment account:

```bash
sudo install -d -m 0700 -o deploy -g deploy /srv/tredro-backups
```

Manual PostgreSQL backup:

```bash
cd /srv/tredro/backend
docker compose -f docker-compose.prod.yml exec -T postgres \
  pg_dump -U tredro -d tredro -Fc \
  > /srv/tredro-backups/tredro-$(date -u +%Y%m%dT%H%M%SZ).dump
```

Manual media backup (the Compose project name is fixed as `tredro`; confirm the
volume with `docker volume ls`):

```bash
docker run --rm \
  -v tredro_media_data:/source:ro \
  -v /srv/tredro-backups:/backup \
  alpine:3 tar -C /source -czf /backup/media-$(date -u +%Y%m%dT%H%M%SZ).tar.gz .
```

Test restoration on a separate database/container. Encrypt and transfer
backups to independent object storage with a tool such as restic, and alert if
the scheduled job fails.

## 9. Operations checklist

Useful commands:

```bash
docker compose -f docker-compose.prod.yml ps
docker compose -f docker-compose.prod.yml logs -f --tail=100 backend
docker stats
df -h
free -h
sudo journalctl -u docker --since today
```

Also configure:

- external uptime monitoring for `/api/health/`;
- error reporting (for example Sentry) before real customer traffic;
- disk, memory, CPU, certificate, backup-age, and HTTP 5xx alerts;
- provider firewall rules matching UFW (SSH, 80, and 443 only);
- monthly OS and container-image patching;
- log retention and Docker disk-usage monitoring;
- a tested restore drill and documented recovery owner.

The health endpoint is currently a liveness probe only; it does not test a
database query or Redis. Add a separate readiness endpoint before introducing
a load balancer or automated failover.

## 10. Repository findings to close before customer data

These do not prevent a controlled first deployment, but should be tracked:

- Product images and company logo/cover uploads are unrestricted `FileField`s.
  Validate file size, decoded image type, and allowed extensions; consider a
  separate media hostname so untrusted uploads do not share the API origin.
- `requirements.txt` uses version ranges rather than a fully resolved lock.
  Generate and review a reproducible dependency lock for production builds.
- `/api/health/` checks only that Django can answer. Add authenticated or
  non-public readiness checks for PostgreSQL and Redis.
- No Celery tasks were found during this review. Worker and beat can remain
  deployed for the planned architecture, but watch their memory use and remove
  them until needed if capacity matters.
- Application logs go to container stdout, but there is no exception tracker
  or centralized log destination yet.
- `.github/workflows/deploy.yml` still pushes a Docker Hub image and triggers a
  Render deployment. It does not deploy this VPS; update or disable it when the
  VPS becomes the production target.
