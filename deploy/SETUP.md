# PM Desktop — Production Deployment Guide

## Architecture

```
                    ┌──────────────────────────────────┐
   Users ──────────▶│  Server A (LB + App + Monitor)   │
        HTTPS/WSS   │                                  │
                    │  ┌─────────┐  ┌──────┐  ┌─────┐ │
                    │  │  Nginx  │─▶│ API  │  │ ARQ │ │
                    │  │  (LB)   │  │:8001 │  │ Wkr │ │
                    │  └────┬────┘  └──────┘  └─────┘ │
                    │       │       ┌────────────────┐ │
                    │       │       │  Uptime Kuma   │ │
                    │       │       │    :3001       │ │
                    │       │       └────────────────┘ │
                    └───────┼──────────────────────────┘
                            │
                            │ :8001
                    ┌───────▼──────────────────────────┐
                    │  Server B (App only)              │
                    │                                  │
                    │  ┌──────┐  ┌─────┐               │
                    │  │ API  │  │ ARQ │               │
                    │  │:8001 │  │ Wkr │               │
                    │  └──────┘  └─────┘               │
                    └──────────────────────────────────┘

   External (already running):
   PostgreSQL · Redis · Meilisearch · MinIO
```

**Total: 2 Linux servers** — Nginx is lightweight enough to co-locate on Server A.

---

## Prerequisites

- 2x Linux servers (Ubuntu 22.04+ recommended), minimum 2 CPU / 4 GB RAM each
- Docker Engine 24+ and Docker Compose v2 on both servers
- Network connectivity: Server A ↔ Server B on port 8001
- Both servers can reach PostgreSQL, Redis, Meilisearch, MinIO
- A domain name (optional, but needed for SSL)

---

## Step 1 — Install Docker on Both Servers

```bash
# Run on BOTH Server A and Server B
sudo apt update && sudo apt upgrade -y

# Install Docker
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker $USER

# Verify
docker --version
docker compose version
```

Log out and back in for the group change to take effect.

---

## Step 2 — Clone the Repo on Both Servers

```bash
git clone https://github.com/sannge/PMS.git /opt/pm-project
cd /opt/pm-project
```

---

## Step 3 — Configure Environment

```bash
# On BOTH servers — copy and fill in your secrets
cp fastapi-backend/.env.prod.example fastapi-backend/.env.prod
nano fastapi-backend/.env.prod
```

Required values to set:
- `DB_SERVER`, `DB_PASSWORD` — your PostgreSQL host
- `REDIS_URL` — your Redis host (include password)
- `MINIO_ENDPOINT`, `MINIO_SECRET_KEY`
- `MEILISEARCH_URL`, `MEILISEARCH_API_KEY`
- `JWT_SECRET`, `JWT_REFRESH_SECRET` — generate with `openssl rand -hex 32`
- `AI_ENCRYPTION_KEY` — generate with `openssl rand -hex 32`
- `CORS_ORIGINS` — your frontend URL(s)

**Important**: Both servers must use the **exact same** `.env.prod` (same JWT secrets, same DB, same Redis).

---

## Step 4 — SSL Certificates (Server A)

Option A — Let's Encrypt (if you have a domain):
```bash
sudo apt install certbot -y
sudo certbot certonly --standalone -d yourdomain.com

# Copy certs to Nginx volume
mkdir -p /opt/pm-project/deploy/nginx/certs
sudo cp /etc/letsencrypt/live/yourdomain.com/fullchain.pem /opt/pm-project/deploy/nginx/certs/
sudo cp /etc/letsencrypt/live/yourdomain.com/privkey.pem /opt/pm-project/deploy/nginx/certs/
```

Option B — Self-signed (internal network):
```bash
mkdir -p /opt/pm-project/deploy/nginx/certs
openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
  -keyout /opt/pm-project/deploy/nginx/certs/privkey.pem \
  -out /opt/pm-project/deploy/nginx/certs/fullchain.pem \
  -subj "/CN=pm-desktop"
```

---

## Step 5 — Configure Nginx (Server A)

Edit the Nginx config to point to Server B's IP:

```bash
nano /opt/pm-project/deploy/nginx/nginx.conf
```

Replace `SERVER_B_IP` with the actual IP of Server B:
```nginx
upstream api_backends {
    ip_hash;
    server app:8001;                    # Server A (local)
    server 10.18.137.50:8001;           # Server B (replace with real IP)
}
```

---

## Step 6 — Start Server B First

```bash
# On Server B
cd /opt/pm-project/deploy
docker compose -f docker-compose.server2.yml up -d
```

Verify it's running:
```bash
docker compose -f docker-compose.server2.yml ps
curl http://localhost:8001/health
# Should return: {"status":"healthy"}
```

---

## Step 7 — Start Server A

```bash
# On Server A
cd /opt/pm-project/deploy
docker compose -f docker-compose.server1.yml up -d
```

Verify all services:
```bash
docker compose -f docker-compose.server1.yml ps

# Check each component
curl http://localhost:8001/health          # API direct
curl -k https://localhost/health           # Through Nginx
curl http://localhost/nginx-health         # Nginx itself
```

---

## Step 8 — Configure Uptime Kuma (Monitoring)

1. Open `http://SERVER_A_IP:3001` in your browser
2. Create an admin account
3. Add these monitors:

| Name               | Type | URL / Host                           | Interval |
|--------------------|------|--------------------------------------|----------|
| API - Server A     | HTTP | `http://pm-api:8001/health`          | 30s      |
| API - Server B     | HTTP | `http://SERVER_B_IP:8001/health`     | 30s      |
| Nginx LB           | HTTP | `http://pm-nginx/nginx-health`       | 30s      |
| Worker - Server A  | Docker | Container: `pm-worker`             | 60s      |
| PostgreSQL         | TCP  | `DB_SERVER_IP:5432`                  | 60s      |
| Redis              | TCP  | `REDIS_IP:6379`                      | 60s      |
| Meilisearch        | HTTP | `http://MEILI_IP:7700/health`        | 60s      |
| MinIO              | HTTP | `http://MINIO_IP:9000/minio/health/live` | 60s  |

4. Set up notifications (email, Slack, Discord, etc.) under Settings → Notifications

---

## Step 9 — Update CORS Origins

In `.env.prod` on both servers, add your production domain:
```
CORS_ORIGINS=https://yourdomain.com,http://localhost:5173
```

Then restart:
```bash
# Server A
docker compose -f docker-compose.server1.yml restart app worker

# Server B
docker compose -f docker-compose.server2.yml restart app worker
```

---

## Routine Operations

### View logs
```bash
docker compose -f docker-compose.server1.yml logs -f app       # API logs
docker compose -f docker-compose.server1.yml logs -f worker    # Worker logs
docker compose -f docker-compose.server1.yml logs -f nginx     # LB logs
```

### Deploy updates (zero-downtime rolling)
```bash
# 1. Pull latest code on both servers
cd /opt/pm-project && git pull

# 2. Rebuild and restart Server B first
# On Server B:
docker compose -f docker-compose.server2.yml up -d --build

# 3. Wait for Server B health check to pass (~15s)
# Nginx automatically routes all traffic to Server A while B restarts

# 4. Rebuild and restart Server A
# On Server A:
docker compose -f docker-compose.server1.yml up -d --build app worker
# Note: don't rebuild nginx/uptime-kuma unless their config changed
```

### Run database migrations
```bash
# On ONE server only (Server A)
docker compose -f docker-compose.server1.yml exec app \
  uv run alembic upgrade head
```

### Scale workers (if needed)
```bash
# Run extra worker containers
docker compose -f docker-compose.server1.yml up -d --scale worker=2
```

---

## Firewall Rules

```bash
# Server A (public-facing)
sudo ufw allow 80/tcp      # HTTP (redirects to HTTPS)
sudo ufw allow 443/tcp     # HTTPS
sudo ufw allow 3001/tcp    # Uptime Kuma (restrict to your IP in production)
sudo ufw allow from SERVER_B_IP to any port 8001   # Server B health checks

# Server B (internal only)
sudo ufw allow from SERVER_A_IP to any port 8001   # Only Server A's Nginx
```

---

## Troubleshooting

| Symptom | Check |
|---------|-------|
| 502 Bad Gateway | `docker ps` — is pm-api running? Check `docker logs pm-api` |
| WebSocket won't connect | Nginx config has `/ws` location with `Upgrade` headers? |
| SSE streaming cuts off | Check `/api/ai/chat/` location has `proxy_buffering off` |
| Worker not processing jobs | `docker logs pm-worker` — can it reach Redis? |
| Uneven load distribution | `ip_hash` groups behind NAT — consider `least_conn` if needed |
| Uptime Kuma can't reach Docker | For Docker monitoring, mount Docker socket (see note below) |

### Enable Docker monitoring in Uptime Kuma

If you want Uptime Kuma to monitor Docker container status directly, add this to the `uptime-kuma` service in `docker-compose.server1.yml`:
```yaml
volumes:
  - uptime-kuma-data:/app/data
  - /var/run/docker.sock:/var/run/docker.sock:ro
```
