# 2C2G 共用服务器部署方案（已部署官网的旧机器）

> 适用对象：**2 vCPU / 2 GiB 内存**（即「2V2G」，下文统称 2C2G）且**已经跑着官网**的同一台服务器，需要在不中断官网的前提下新增部署 SparklightAIGEO（原 GEOFlow）生产实例。
>
> 本文是 [`DEPLOYMENT.md`](DEPLOYMENT.md) 的**场景化补充**：基础流程、停机排空升级协议、受管删除门禁仍以该文为准，本文只覆盖低配共用机的**资源取舍、共存拓扑、精简编排与验收清单**。
>
> 假设与占位符请按实际替换：`example.com`（官网域名）、`geo.example.com`（新站域名）、`18080`（内网 Web 端口）、`/opt/geoflow`（部署目录）。

---

## 1. 结论先行

| 问题 | 结论 |
| --- | --- |
| 2C2G 能不能跑 | 能，但必须**精简进程组合 + 开 swap + 异地构建镜像**，不能按默认 compose 全量启动 |
| 官网会不会被影响 | 只要按本文隔离端口、限制容器内存、**不在这台机器上构建镜像**，官网不受影响 |
| 最大风险 | ① 服务器本地 `docker build`（vite/Composer 峰值可超 1.5 GB，直接 OOM）；② 容器无内存上限导致整机 OOM Killer 杀掉官网进程 |
| 最省内存的取舍 | 只保留 `postgres / redis / app / web / queue / ai-quality-queue(1 副本) / scheduler / reverb`；`knowledge-queue`、`ai-quality-backfill-queue`、`ai-optimization-queue` 按需临时启动 |

**两条硬红线：**

1. 容器必须有 `mem_limit`，且所有容器上限之和 + 官网实测占用 ≤ 物理内存 + swap × 60%。
2. PostgreSQL、Redis、`WEB_PORT` 一律不得监听公网；`18080` 仅允许 `127.0.0.1` 访问。

---

## 2. 上线前盘点（先在服务器上跑一遍）

```bash
# 1) 真实可用内存与现有 swap
free -m
# 2) 官网及系统进程的实际占用（按内存倒序，记录前 10）
ps -eo pid,ppid,user,%cpu,%mem,rss,comm --sort=-rss | head -20
# 3) 已占用的端口，确认 80/443 归属，挑一个空闲内网端口（默认用 18080）
ss -lntup | grep -E ':(80|443|18080|18081|5432|6379)\b'
# 4) 磁盘：至少保留 25 GB（镜像 ~2.5 GB + 数据 + 备份）
df -h / /opt
df -i /
# 5) 官网是否也用 Docker（决定稍后能否随意动 docker daemon）
docker ps --format 'table {{.Names}}\t{{.Image}}\t{{.Status}}' 2>/dev/null
docker network ls 2>/dev/null
ip route
# 6) 虚拟化类型与 CPU（部分轻量机的 2 vCPU 是共享核）
lscpu | egrep 'Model name|^CPU\(s\)|Thread'
```

记录以下数值，后面算内存预算要用：

| 项目 | 实测值 |
| --- | --- |
| MemTotal | ______ MB |
| 官网 + 系统常驻 RSS | ______ MB |
| 可用磁盘 | ______ GB |
| 空闲内网端口 | 18080 / ______ |

**判定**：若「官网 + 系统常驻」已超过 900 MB，本方案的极简档也难以稳定运行，建议先升配到 2C4G（见第 14 节扩容触发线）。

---

## 3. 内存预算

### 3.1 标准档（推荐，合计 ≈ 1.61 GB）

适用于官网较轻（Nginx 静态站或轻量 PHP，占用 ≤ 400 MB）且业务低峰并发不高。

| 容器 | 内存上限 | 说明 |
| --- | --- | --- |
| `postgres` | 320 MB | pgvector，需承担向量检索 |
| `redis` | 160 MB | 队列 + 缓存，`maxmemory` 再限到 128 MB |
| `app` | 448 MB | php-fpm，`pm.max_children` 降到 3 |
| `web` | 64 MB | 容器侧 Nginx |
| `queue` | 224 MB | 主队列，已有 `--memory=128` 进程级保护 |
| `ai-quality-queue` | 224 MB | 副本数固定为 **1**（默认 2） |
| `scheduler` | 96 MB | `schedule:work` |
| `reverb` | 112 MB | WebSocket；不用实时通知可停 |
| **合计** | **≈ 1 648 MB** | 另需 OS + 官网 + swap 支撑 |

### 3.2 极简档（合计 ≈ 1.12 GB）

适用官网偏重（WordPress/宝塔等，占用 400–800 MB）或只是演示、内部使用。停用 `knowledge-queue`、`ai-quality-backfill-queue`、`ai-optimization-queue`。

| 容器 | 标准档 | 极简档 |
| --- | --- | --- |
| `postgres` | 320 MB | 256 MB |
| `redis` | 160 MB | 128 MB |
| `app` | 448 MB | 320 MB |
| `web` | 64 MB | 48 MB |
| `queue` | 224 MB | 192 MB |
| `ai-quality-queue` | 224 MB | 停（需质检时临时拉起 192 MB） |
| `scheduler` | 96 MB | 80 MB |
| `reverb` | 112 MB | 96 MB |
| 合计 | 1 648 MB | **1 120 MB** |

### 3.3 Swap（必做）

2 GiB 物理内存跑这套栈，**必须**配 swap，否则峰值直接 OOM。

```bash
sudo fallocate -l 2G /swapfile            # 磁盘紧张可给 1G，宽裕建议 4G
sudo chmod 600 /swapfile
sudo mkswap /swapfile
sudo swapon /swapfile
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab

sudo sysctl -w vm.swappiness=10
sudo sysctl -w vm.vfs_cache_pressure=50
echo -e 'vm.swappiness=10\nvm.vfs_cache_pressure=50' | sudo tee /etc/sysctl.d/99-geoflow-lowmem.conf
swapon --show
```

> swap 只是防 OOM 的缓冲垫，**不要依赖 swap 承载常态流量**。若 `si/so` 长期非零，说明该升配了。

---

## 4. 共存拓扑

```text
                       ┌──────────────────────── 公网 ────────────────────────┐
   https://example.com │ 官网（保持现状，不动）                                │
   https://geo.example.com ─┐                                                 │
                            ▼                                                 │
                宿主机 Nginx（官网现有的那个）                                 │
                     │  proxy_pass 127.0.0.1:18080                            │
                     ▼                                                        │
              Docker 网络 geoflow-prod-net (10.88.0.0/16)                     │
              ┌───────────┬────────────┬──────────┬────────────┐              │
              │ web:80    │ app:9000   │ queue    │ scheduler  │  ……         │
              │ (Nginx)   │ (php-fpm)  │ ai-quality│ reverb     │             │
              └───────────┴────────────┴──────────┴────────────┘              │
                     │            │          │                                │
                 postgres:5432 redis:6379（**仅容器网络可达，不发布端口**）    │
```

要点：

- 官网 Nginx 继续占用 `80/443`，新增站点通过**独立子域名**接入；
- GEOFlow 的 `WEB_PORT` 只绑本机回环（第 9 节防火墙），公网一律走 443；
- 容器网络默认 `10.88.0.0/16`，上线前用 `ip route` 与内网网段比对，避免和 VPC/官网容器网段冲突；冲突时改 `.env.prod` 的 `DOCKER_NETWORK_SUBNET`。

> **一级目录（`https://example.com/geo`）不推荐。** 该部署形态需要反向代理透传 `X-Forwarded-Prefix`，且 Laravel 侧的 URL 生成、资产路径、后台跳转都要额外校验，在 2C2G 共用环境下排错成本远高于一个子域名。确实只能走子目录时，把 `APP_URL` 写成 `https://example.com/geo`，`ADMIN_BASE_PATH` **仍保持** `geo_admin`（不要写成 `geo/geo_admin`），并全量回归后台所有导航与上传后再开放。

---

## 5. 镜像策略：不要在 2C2G 机器上构建

生产 Dockerfile 有两个吃内存阶段：`composer install`（vendor）与 `npm run build`（Vite 前端资产）。后者在这类机器上峰值常超过 1.5 GB，极易在中途 OOM。推荐在**本地构建后推送**，直接用仓库自带的构建脚本即可。

### 方案 A：本地构建 + 推送镜像仓库（首选）

```bash
# 本机（Mac/Linux，需 docker buildx）
REGISTRY=registry.cn-xxxx.aliyuncs.com NS=geo_flow VERSION=20260925 \
  bash deploy-scripts/build-and-push-amd64-images.sh
```

脚本产出两个 tag（注意 app/web 名称不同，写 `.env.prod` 时别抄混）：

```env
GEOFLOW_APP_IMAGE=registry.cn-xxxx.aliyuncs.com/geo_flow/sparklightaigeo-app-prod:20260925
GEOFLOW_WEB_IMAGE=registry.cn-xxxx.aliyuncs.com/geo_flow/geoflow-web-prod:20260925
```

服务器侧只需 `docker pull`（约几百 MB 内存开销，安全），不再触发任何构建。

### 方案 B：本地打包 + 流式导入（无镜像仓库时）

```bash
# 本机
docker buildx build --platform linux/amd64 -f docker/Dockerfile.prod -t geoflow-app:20260925 --load .
docker buildx build --platform linux/amd64 -f docker/nginx/Dockerfile.prod -t geoflow-web:20260925 --load .

docker save geoflow-app:20260925  | ssh -C root@服务器 'docker load'
docker save geoflow-web:20260925 | ssh -C root@服务器 'docker load'

# 服务器上给镜像打与 .env.prod 中 GEOFLOW_APP_IMAGE / GEOFLOW_WEB_IMAGE 一致的 tag
docker tag geoflow-app:20260925 registry.cn-xxxx.aliyuncs.com/geo_flow/sparklightaigeo-app-prod:20260925
docker tag geoflow-web:20260925 registry.cn-xxxx.aliyuncs.com/geo_flow/geoflow-web-prod:20260925
```

### 方案 C：不得不在服务器构建（下策）

```bash
# 先临时释放内存
sudo systemctl stop php-fpm nginx        # 或把官网容器 docker stop（请先确认可停）
sync && echo 3 > /proc/sys/vm/drop_caches

# 逐个构建，避免两个大阶段并行
docker compose --env-file .env.prod -f docker-compose.prod.yml build app
docker compose --env-file .env.prod -f docker-compose.prod.yml build web
```

失败（137 / Killed / `JavaScript heap out of memory`）时先加到 4 GB swap 再重试，或改回方案 A/B。**构建完成后立刻恢复官网进程。**

### 国内镜像拉取

服务器上拉取基础镜像慢时，用不重启 Docker 的方式（避免打断官网容器）：

- 隧道方式：`deploy-scripts/start-docker-pull-tunnel.sh` + `pull-images-once-via-tunnel.sh`
- 本机代拉取：`ECS_HOST=user@ip bash deploy-scripts/sync-images-from-local.sh`

不要直接 `echo registry-mirrors >> /etc/docker/daemon.json && systemctl restart docker`——**重启 daemon 会中断已在运行的官网容器**。

---

## 6. 精简编排文件（override）

不改仓库自带的 `docker-compose.prod.yml`（便于后续 `git pull`），新增一个 overlay 文件：

`/opt/geoflow/docker-compose.2c2g.yml`

```yaml
# 2C2G 共用服务器精简覆盖层。
# 用法：docker compose --env-file .env.prod \
#        -f docker-compose.prod.yml -f docker-compose.2c2g.yml <command>
services:
  postgres:
    mem_limit: ${PG_MEMORY_LIMIT:-320m}
    command:
      - postgres
      - -c
      - "shared_buffers=${PG_SHARED_BUFFERS:-128MB}"
      - -c
      - "effective_cache_size=${PG_EFFECTIVE_CACHE_SIZE:-512MB}"
      - -c
      - "work_mem=${PG_WORK_MEM:-4MB}"
      - -c
      - "maintenance_work_mem=64MB"
      - -c
      - "max_connections=${PG_MAX_CONNECTIONS:-40}"
      - -c
      - "wal_buffers=8MB"
      - -c
      - "max_wal_size=${PG_MAX_WAL_SIZE:-512MB}"
      - -c
      - "min_wal_size=64MB"
      - -c
      - "random_page_cost=1.1"
      - -c
      - "max_parallel_workers=1"
      - -c
      - "max_parallel_workers_per_gather=0"
      - -c
      - "max_worker_processes=2"
      - -c
      - "autovacuum_max_workers=1"
      - -c
      - "autovacuum_vacuum_scale_factor=0.05"
      - -c
      - "autovacuum_vacuum_cost_limit=500"

  redis:
    mem_limit: ${REDIS_MEMORY_LIMIT:-160m}
    # command 为单值字段，此处整体覆盖 base 文件；逻辑与 base 一致，只是加上 maxmemory。
    command:
      - /bin/sh
      - -lc
      - |
        exec redis-server --appendonly yes \
          --maxmemory ${REDIS_MAXMEMORY:-128mb} \
          --maxmemory-policy ${REDIS_MAXMEMORY_POLICY:-noeviction} \
          $${REDIS_PASSWORD:+--requirepass "$$REDIS_PASSWORD"}

  app:
    mem_limit: ${APP_CONTAINER_MEMORY_LIMIT:-448m}
    volumes:
      # 低配专属 php-fpm 进程池（见第 7 节）；这是追加挂载，不会覆盖原有存储目录
      - ./deploy-2c2g/www.conf:/usr/local/etc/php-fpm.d/zz-geoflow.conf:ro

  web:
    mem_limit: ${WEB_CONTAINER_MEMORY_LIMIT:-64m}

  queue:
    mem_limit: ${QUEUE_CONTAINER_MEMORY_LIMIT:-224m}

  ai-quality-queue:
    mem_limit: ${AI_QUALITY_QUEUE_CONTAINER_MEMORY_LIMIT:-224m}
    deploy:
      replicas: ${AI_QUALITY_QUEUE_REPLICAS:-1}

  scheduler:
    mem_limit: ${SCHEDULER_CONTAINER_MEMORY_LIMIT:-96m}

  reverb:
    mem_limit: ${REVERB_CONTAINER_MEMORY_LIMIT:-112m}
```

> Redis 用 `noeviction` 是为了保住队列任务不被淘汰。若出现 `OOM command not allowed when used memory > 'maxmemory'`，优先清理 Laravel 缓存键或把 `.env.prod` 的 `CACHE_STORE` 改为 `database`（队列仍走 Redis），再考虑 `allkeys-lru`——后者会丢队列 job，只在无所谓丢任务的演示环境使用。

---

## 7. 精简 php-fpm 进程池

镜像内置的 `docker/php-fpm/www.conf` 是 `pm.max_children = 5` + `memory_limit = 128M`，远超预算。通过挂载覆盖：

`/opt/geoflow/deploy-2c2g/www.conf`

```ini
[www]
listen = 9000
listen.mode = 0666
pm = dynamic
pm.max_children = 3
pm.start_servers = 1
pm.min_spare_servers = 1
pm.max_spare_servers = 2
pm.max_requests = 200
clear_env = no
catch_workers_output = yes
php_admin_value[error_log] = /proc/self/fd/2
php_admin_flag[log_errors] = on
php_admin_value[memory_limit] = 128M
```

`pm.max_requests = 200` 用于抑制低配环境下的内存缓慢增长（每次处理 200 个请求后回收进程）。极简档可进一步 `pm.max_children = 2`。

---

## 8. `.env.prod` 关键项

以下为该场景需要主动确认/修改的值，其余保持 `.env.prod.example` 默认：

```env
# --- 访问入口 ---
APP_ENV=production
APP_DEBUG=false
APP_URL=https://geo.example.com
# 反代来自本机回环；若官网 Nginx 与容器在不同 IP，填实际来源 IP/CIDR，禁止填 *
TRUSTED_PROXIES=127.0.0.1
SESSION_SECURE_COOKIE=true

# --- 后台入口 ---
ADMIN_BASE_PATH=换个难猜的自定义后台前缀（不要沿用默认 geo_admin）
GEOFLOW_ADMIN_USERNAME=换个非 admin 的用户名
GEOFLOW_ADMIN_PASSWORD=强密码
GEOFLOW_INITIAL_ADMIN_HINT_ENABLED=false

# --- 容器 Nginx 认的对外域名（必须与外层反代一致）---
GEOFLOW_NGINX_PRIMARY_HOST=geo.example.com
GEOFLOW_NGINX_PRIMARY_ALIASES=
GEOFLOW_NGINX_HOSTED_ROOT_DOMAIN=invalid
GEOFLOW_NGINX_PUBLIC_SCHEME=https
GEOFLOW_NGINX_PUBLIC_PORT=443

# --- 凭据：务必改 ---
DB_PASSWORD=强密码
REDIS_PASSWORD=强密码
REVERB_APP_SECRET=随机长串

# --- Reverb（走主站 443 的 /reverb 入口）---
REVERB_HOST=geo.example.com
REVERB_PORT=443
REVERB_SCHEME=https
REVERB_ALLOWED_ORIGINS=geo.example.com

# --- 端口与隔离 ---
WEB_PORT=18080
COMPOSE_PROJECT_NAME=geoflow-prod
DOCKER_NETWORK_NAME=geoflow-prod-net
DOCKER_NETWORK_SUBNET=10.88.0.0/16
POSTGRES_DATA_DIR=./docker-data/prod/postgres

# --- 低配精简 ---
AI_QUALITY_QUEUE_REPLICAS=1
APP_CONTAINER_MEMORY_LIMIT=448m
QUEUE_CONTAINER_MEMORY_LIMIT=224m
KNOWLEDGE_QUEUE_CONTAINER_MEMORY_LIMIT=224m
AI_QUALITY_QUEUE_CONTAINER_MEMORY_LIMIT=224m
REDIS_MAXMEMORY=128mb
REDIS_MAXMEMORY_POLICY=noeviction
PG_SHARED_BUFFERS=128MB
PG_MAX_CONNECTIONS=40
GEOFLOW_KNOWLEDGE_EMBEDDING_JOB_SIZE=8
LOG_LEVEL=error

# --- 预构建镜像（第 5 节方案 A/B 时填写；填了就直接使用远端镜像，不再本地构建）---
# GEOFLOW_APP_IMAGE=registry.cn-xxxx.aliyuncs.com/geo_flow/sparklightaigeo-app-prod:20260925
# GEOFLOW_WEB_IMAGE=registry.cn-xxxx.aliyuncs.com/geo_flow/geoflow-web-prod:20260925
```

初始化方式：

```bash
cd /opt/geoflow
cp .env.prod.example .env.prod
# 按上面清单逐项设置（vi 或 sed）；密码用 openssl rand -base64 24 生成
# 核对关键项是否已生效
grep -E '^(APP_URL|ADMIN_BASE_PATH|TRUSTED_PROXIES|SESSION_SECURE_COOKIE|WEB_PORT|AI_QUALITY_QUEUE_REPLICAS)=' .env.prod
```

> 不要直接执行 `deploy-scripts/sparklightaigeo-docker-deploy.sh` 走完整个流程，原因见第 10 节脚本注记。

---

## 9. 宿主机 Nginx 共存反代

在官网 Nginx 上新增一个 server（不要改官网原有 server）：

```nginx
# /etc/nginx/conf.d/geo.example.com.conf
server {
    listen 80;
    listen [::]:80;
    server_name geo.example.com;
    location /.well-known/acme-challenge/ { root /var/www/certbot; }
    location / { return 301 https://$host$request_uri; }
}

server {
    listen 443 ssl http2;
    listen [::]:443 ssl http2;
    server_name geo.example.com;

    ssl_certificate     /etc/nginx/ssl/geo.example.com/fullchain.pem;
    ssl_certificate_key /etc/nginx/ssl/geo.example.com/key.pem;
    ssl_protocols TLSv1.2 TLSv1.3;

    client_max_body_size 64m;   # 与容器 Nginx 对齐，否则后台上传会 413

    # 静态资产：容器 Nginx 已带长效缓存头，这里原样透传即可
    location ^~ /build/assets/ {
        proxy_pass http://127.0.0.1:18080;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header X-Forwarded-Host $host;
        proxy_set_header X-Forwarded-Port $server_port;
        expires 1y;
    }

    # Reverb WebSocket（后台实时通知依赖）
    location ^~ /reverb/ {
        proxy_pass http://127.0.0.1:18080;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header X-Forwarded-Host $host;
        proxy_set_header X-Forwarded-Port $server_port;
        proxy_read_timeout 86400s;
        proxy_send_timeout 86400s;
    }

    # 主入口（含后台 /$ADMIN_BASE_PATH）
    location / {
        proxy_pass http://127.0.0.1:18080;
        proxy_http_version 1.1;
        proxy_set_header Host              $host;
        proxy_set_header X-Real-IP         $remote_addr;
        proxy_set_header X-Forwarded-For   $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header X-Forwarded-Host  $host;
        proxy_set_header X-Forwarded-Port  $server_port;
        proxy_buffering off;
        proxy_request_buffering off;
        proxy_connect_timeout 10s;
        proxy_read_timeout 300s;    # 长任务（如更新预演）需要放宽
        proxy_send_timeout 300s;
    }
}
```

```bash
sudo nginx -t && sudo systemctl reload nginx     # reload 而非 restart，官网不中断
```

证书建议 `certbot certonly --webroot -w /var/www/certbot -d geo.example.com`，**避免用 `certbot --nginx` 自动改写官网配置**。

### 收紧 18080（务必）

容器端口由 compose 发布为 `0.0.0.0:18080`，需从外部隔离。用 Docker 的 `DOCKER-USER` 链（作用于 FORWARD，对本机回环访问不受影响）：

```bash
IFACE=$(ip route get 1.1.1.1 | awk '{print $5; exit}')       # 公网网卡，如 eth0
sudo iptables -I DOCKER-USER -i "$IFACE" -p tcp --dport 18080 -j DROP
sudo iptables -I DOCKER-USER -i "$IFACE" -p tcp --dport 5432  -j DROP
sudo iptables -I DOCKER-USER -i "$IFACE" -p tcp --dport 6379  -j DROP

# 持久化（Debian/Ubuntu）
sudo apt-get install -y iptables-persistent
sudo netfilter-persistent save
```

云厂商安全组同步关闭 18080/5432/6379 的入方向。

---

## 10. 首次部署步骤

> **脚本注记（踩坑点）**：`deploy-scripts/sparklightaigeo-docker-deploy.sh` 结尾会调用 `deploy-scripts/geoflow-healthcheck.sh`，但仓库里该文件已改名为 `sparklightaigeo-healthcheck.sh`，一键脚本会在健康检查环节直接失败。因此本场景建议**按下列手工顺序执行**；确需脚本自动检查时，先在服务器上 `cp deploy-scripts/sparklightaigeo-healthcheck.sh deploy-scripts/geoflow-healthcheck.sh`。

```bash
cd /opt/geoflow
export COMPOSE_PROD='docker compose --env-file .env.prod -f docker-compose.prod.yml -f docker-compose.2c2g.yml'
```

> 之后所有 compose 命令都要带 `-f docker-compose.2c2g.yml`，否则会带着默认（无限制、2 副本）配置启动——这是共用机上最容易翻车的一步。

```bash
# 1) 拉/载预构建镜像（未设置 GEOFLOW_*_IMAGE 时 compose 会在本机构建，见第 5 节）
docker pull "$(grep '^GEOFLOW_APP_IMAGE=' .env.prod | cut -d= -f2-)"
docker pull "$(grep '^GEOFLOW_WEB_IMAGE=' .env.prod | cut -d= -f2-)"

# 2) 起数据库与缓存，先确认健康
$COMPOSE_PROD up -d postgres redis
$COMPOSE_PROD ps     # postgres / redis 都要 healthy

# 3) 一次性 init：迁移 + 首次安装（仅空库；已有数据实例走停机排空升级）
$COMPOSE_PROD up init
$COMPOSE_PROD logs init | tail -40

# 4) 启动精简服务组合（不启动 knowledge / backfill / optimization 三个队列）
$COMPOSE_PROD up -d --remove-orphans \
  app web queue ai-quality-queue scheduler reverb

# 5) 同步 AI 工作台系统知识（可重复执行）
$COMPOSE_PROD run --rm app php artisan geoflow:sync-system-knowledge --key=ai_workspace_manual --media

# 6) 看容器是否稳定在 30 秒以上没有被杀
sleep 30 && docker stats --no-stream
```

按需队列的使用方式（跑完即停，避免常驻占内存）：

```bash
# 知识库切片/向量化时
$COMPOSE_PROD up -d knowledge-queue
$COMPOSE_PROD logs -f knowledge-queue
$COMPOSE_PROD stop knowledge-queue

# 历史质检回填、AI 内容优化同理
$COMPOSE_PROD up -d ai-quality-backfill-queue
$COMPOSE_PROD up -d ai-optimization-queue
```

---

## 11. 验收清单

### 11.1 官方健康检查的适用范围

`deploy-scripts/sparklightaigeo-healthcheck.sh` 把 `knowledge-queue`、`ai-quality-backfill-queue`、`ai-optimization-queue` 都列为必需服务，**精简部署下它会判失败**。这是预期结果，不代表部署有问题。

替代做法（二选一）：

```bash
# A. 临时拉起全部队列跑完整检查，跑完再停
export COMPOSE_PROD='docker compose --env-file .env.prod -f docker-compose.prod.yml -f docker-compose.2c2g.yml'
$COMPOSE_PROD up -d knowledge-queue ai-quality-backfill-queue ai-optimization-queue
bash deploy-scripts/sparklightaigeo-healthcheck.sh
$COMPOSE_PROD stop knowledge-queue ai-quality-backfill-queue ai-optimization-queue
```

```bash
# B. 精简版自检（日常使用，逐条过）
$COMPOSE_PROD ps --status running --services
curl -fsS --max-time 10 http://127.0.0.1:18080/up && echo OK
$COMPOSE_PROD exec -T app php artisan migrate:status --pending=1
$COMPOSE_PROD exec -T app php artisan geoflow:ai-quality-health --json --probe --wait=10
$COMPOSE_PROD exec -T app php artisan geoflow:security-audit
```

### 11.2 上线前必须确认的项

| # | 检查项 | 通过标准 |
| --- | --- | --- |
| 1 | 官网访问 | 官网首页、后台、证书均未受影响 |
| 2 | 新站前台 | `https://geo.example.com` 200，静态资产无 404 |
| 3 | 新站后台 | `https://geo.example.com/<ADMIN_BASE_PATH>/login` 可登录，登录后不跳回登录页 |
| 4 | 心跳 | `curl -fsS http://127.0.0.1:18080/up` 返回 200 |
| 5 | 迁移 | `migrate:status --pending=1` 无待执行 |
| 6 | 安全审计 | `geoflow:security-audit` 退出码 0 或已逐项处理 finding |
| 7 | WebSocket | 后台触发一次实时通知，浏览器控制台无 WS 报错（`/reverb/` 走 443） |
| 8 | 上传 | 后台上传一张图片成功（验证 `client_max_body_size` 链路） |
| 9 | 队列 | 生成一篇文章，任务被 `queue` 消费并完成 |
| 10 | 内存 | `docker stats` 稳态下无容器被 OOM kill；`free -m` 仍有余量 |
| 11 | 端口隔离 | 外网 `nc -vz 公网IP 18080` 不通；`nc -vz 127.0.0.1 18080` 通 |
| 12 | 默认口令 | 初始/随机生成的管理员密码已修改，且 `GEOFLOW_INITIAL_ADMIN_HINT_ENABLED=false` |
| 13 | 备份 | 已跑通一次 dump 并验证恢复（见第 12 节） |

---

## 12. 备份、更新与回滚

### 12.1 备份（每日，保留 7 天）

`/opt/geoflow/backup.sh`

```bash
#!/usr/bin/env bash
set -euo pipefail
cd /opt/geoflow
COMPOSE=(docker compose --env-file .env.prod -f docker-compose.prod.yml -f docker-compose.2c2g.yml)
STAMP=$(date +%F-%H%M)
OUT=/var/backups/geoflow
install -d "$OUT"

DB_USERNAME="$(grep '^DB_USERNAME=' .env.prod | cut -d= -f2-)"
DB_DATABASE="$(grep '^DB_DATABASE=' .env.prod | cut -d= -f2-)"

"${COMPOSE[@]}" exec -T postgres pg_dump -U "$DB_USERNAME" -Fc "$DB_DATABASE" > "$OUT/db-$STAMP.dump"
tar czf "$OUT/storage-$STAMP.tgz" storage
cp .env.prod "$OUT/env-$STAMP.bak"

find "$OUT" -type f -mtime +7 -delete
```

```bash
sudo chmod +x backup.sh
(crontab -l 2>/dev/null; echo '20 3 * * * /opt/geoflow/backup.sh >> /var/log/geoflow-backup.log 2>&1') | crontab -
```

> 单实例 Docker Postgres 不支持在线基础备份，务必用 `pg_dump`。备份文件建议同步到对象存储，别只留在本机 40 GB 磁盘上。

### 12.2 更新（沿用官方停机排空协议）

注意：`git pull` + `build` + `up -d` **不能直接替代**停机排空升级。低配机的正确顺序：

1. 按第 5 节在**异地**构建并推送新镜像，**不要**在服务器上 build；
2. `docker compose ... pull`（或 `docker load`）；
3. 执行 `DEPLOYMENT.md` 3.1 节的 `down → stop/drain → 一次性确认 → 迁移 → 启动新版本 → readiness → security-audit → 恢复流量`；
4. 更新完成确认容器全部来自新镜像后，解除维护模式。

停机窗口只影响新站；官网不在编排范围与大版本边界内，保持原样即可。

### 12.3 回滚

```bash
# 回到上一个已知版本：把 .env.prod 里的镜像 tag 改回旧版本号再起
sed -i -E 's#^(GEOFLOW_(APP|WEB)_IMAGE=.*:).*$#\1<上一个可用的版本号>#' .env.prod
grep '^GEOFLOW_.*_IMAGE=' .env.prod

$COMPOSE_PROD down
$COMPOSE_PROD pull
$COMPOSE_PROD up -d
# 数据库 schema 兼容性检查与停机排空边界见 DEPLOYMENT.md 第 7 节
```

---

## 13. 监控与排错

### 13.1 监控阈值

```bash
watch -n 5 'free -m; echo; docker stats --no-stream --format "table {{.Name}}\t{{.MemUsage}}\t{{.MemPerc}}\t{{.CPUPerc}}"'
```

| 指标 | 阈值 | 处理 |
| --- | --- | --- |
| 可用内存（含 swap） | < 300 MB | 立即排查最大容器；临时停用 `ai-quality-queue` |
| swap `si/so` | 持续非 0 超过 10 分钟 | 降档或升配 |
| 某容器内存 | 达到 `mem_limit` 的 95% | 该容器即将 OOM，调低下批次任务规模或重启该容器 |
| `/up` | 非 200 | 先看 `web`、`app` 日志 |
| Redis used_memory | > 90% maxmemory | 清缓存键或改 `CACHE_STORE=database` |

内核日志看是否发生过 OOM：

```bash
dmesg -T | egrep -i 'killed process|out of memory' | tail -20
journalctl -k --since '1 hour ago' | egrep -i 'oom|killed process'
```

### 13.2 常见问题

| 现象 | 原因 | 处理 |
| --- | --- | --- |
| 构建到 Vite/`npm run build` 被 Killed | 内存不足（最常见） | 改第 5 节方案 A/B；临时加到 4 GB swap；构建时先停官网释放内存 |
| 官网突然 502 | 容器吃内存触发整机 OOM Killer | 补 `mem_limit`；检查是否漏加 `-f docker-compose.2c2g.yml` |
| 后台登录后又跳回登录页 | `SESSION_SECURE_COOKIE` 与访问协议不符，或反代未传 `X-Forwarded-Proto` | HTTPS 场景设 `true`，并在反代补三个 `X-Forwarded-*` |
| 后台实时通知不生效 | `REVERB_*` 域名/端口写错，或 18080 被防火墙拦 | 核实 `REVERB_SCHEME=https`、`REVERB_PORT=443`，`DOCKER-USER` 只限制公网网卡 |
| 上传超过 2 MB 报错 | 外层反代没设 `client_max_body_size 64m` | 补对齐；Laravel 侧还受 `GEOFLOW_MAX_UPLOAD_BYTES` 约束 |
| 前台样式丢失，或 `/build/assets/` 静态资源 404 | 外层反代把 `/build/` 做了 rewrite 或 root 指定 | 外层 `location ^~ /build/assets/` 直接 `proxy_pass` 不做 rewrite |
| 队列长期积压 | 单 worker + AI 请求耗时 | 临时扩容：`$COMPOSE_PROD up -d --scale queue=2`，完成后回落 1 |
| Redis 报 OOM command not allowed | `noeviction` + 内存打满 | 降低 `REDIS_MAXMEMORY` 使用量或 `CACHE_STORE=database` |
| Postgres 启动慢 / 连接数满 | `max_connections=40` 被占满 | 排查未释放的长连接；临时上调 `PG_MAX_CONNECTIONS=60` 并同步下调其他内存项 |

---

## 14. 扩容触发线

出现以下任一情况，请升到 **2C4G（≈ 4 GB 内存）** 而不是继续调参数：

1. 稳态下 `free -m` 的 available 长期低于 300 MB，或 swap 持续被读写；
2. 需要常态化使用知识库向量化、AI 质检回填、AI 内容优化三个额外队列；
3. 文章生成/分发并发超过 2，或后台同时编辑人数 ≥ 3；
4. 官网本身流量增长，两者互相抢占内存已不可避免。

升配后可直接删掉 `-f docker-compose.2c2g.yml` 这一层（保留文件备用），恢复 `AI_QUALITY_QUEUE_REPLICAS=2`，并把全部队列纳入常驻。

---

## 15. 相关文档

- [生产 Docker 部署（基础流程与停机排空升级协议）](DEPLOYMENT.md)
- [初始化问题排查](docker-prod-init-troubleshooting.md)
- [蓝绿部署与自动迁移教程](../blue-green-deployment-usage.md)
- [部署脚本说明](../../deploy-scripts/README.md)
- [AI 质检运行手册](../ai-quality-inspection-runbook.md)
