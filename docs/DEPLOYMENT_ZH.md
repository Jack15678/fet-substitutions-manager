# 校内部署与远程维护手册

本文档用于将本项目部署到学校提供的专用电脑，并在无法到校时安全地进行远程维护。网站默认仅供已连接校内网的设备使用。

最后核对日期：2026-08-16。

## 1. 推荐方案

本项目已使用 Linux 容器封装，不需要开发“Windows 版本”。目标电脑也不需要单独安装 Python、Node.js 或 Git；只要能运行 Docker 即可。

| 学校提供的系统 | 部署方式 | 建议 |
|---|---|---|
| Ubuntu Server 24.04 LTS | Docker Engine + Compose | 首选，适合无人值守 |
| Windows 10/11 Education、Pro 或 Enterprise | Docker Desktop + WSL2 | 可用，适合学校只能提供 Windows 工作站的情况 |
| Windows Server | Hyper-V 中运行 Ubuntu Server，再安装 Docker Engine | 不要安装 Docker Desktop |

如果服务器必须在重启后、无人登录时立即恢复服务，应选择 Linux 或 Windows Server/Windows 上的 Ubuntu 虚拟机。Docker Desktop的自动启动发生在 Windows 用户登录后，不适合作为严格的无人值守服务。

官方参考：

- [Docker Desktop Windows 要求](https://docs.docker.com/desktop/setup/install/windows-install/)
- [Docker Desktop WSL2 后端](https://docs.docker.com/desktop/features/wsl/)
- [Microsoft WSL 安装说明](https://learn.microsoft.com/windows/wsl/install)
- [Docker Engine Ubuntu 安装说明](https://docs.docker.com/engine/install/ubuntu/)
- [Docker Desktop 许可说明](https://docs.docker.com/subscription/desktop-license/)

## 2. 系统和网络要求

### 2.1 建议硬件

| 项目 | 最低建议 | 推荐 |
|---|---:|---:|
| CPU | 2 个 64 位核心 | 4 核 |
| 内存 | Linux 4 GB；Windows 8 GB | 8 GB 或以上 |
| 磁盘 | 30 GB 可用空间 | 60 GB 以上 SSD |
| 网络 | 稳定有线校内网 | 千兆有线网络 |
| 供电 | 可长期运行 | UPS 不间断电源 |

Windows 使用 WSL2 或 Hyper-V 时，CPU 必须支持虚拟化，并在 BIOS/UEFI 中启用。Docker Desktop当前要求 WSL 2.1.5 或以上、Windows 10 22H2 build 19045，或 Windows 11 23H2 build 22631 及以上；部署前应重新查看官方要求。

### 2.2 需要学校 IT 提供的信息

部署前必须确认：

1. 操作系统名称、版本、构建号，以及它是实体机还是虚拟机。
2. 管理员权限，以及是否允许 Docker、WSL2 或 Hyper-V。
3. 固定 IP，或 DHCP 地址保留。
4. 内网 DNS 名称，例如 `substitution.intra.example.edu`。
5. 允许访问网站的校内网段/VLAN，例如行政网和教师 Wi-Fi。
6. 学校内部 CA 签发的 HTTPS 证书，或是否允许分发 Caddy 内部根证书。
7. 安装和更新时能否访问 GitHub、Docker Hub、Microsoft和 Ubuntu 软件源。
8. 学校 VPN 或其他经批准的远程维护通道。
9. 备份 NAS/文件服务器位置、保留期限和负责人。
10. Windows 更新、停电或网络故障后的现场联系人。

### 2.3 网络端口

| 端口 | 用途 | 来源限制 |
|---|---|---|
| TCP 443 | 正式 HTTPS 网站 | 仅允许指定校内网段 |
| TCP 80 | 可选的 HTTP 到 HTTPS 跳转 | 仅允许指定校内网段 |
| TCP 22 | Linux SSH 维护 | 仅学校 VPN 或管理网段 |
| TCP 3389 | Windows RDP 维护 | 仅学校 VPN 或管理网段 |

不要向公网开放 22、3389、8000 或 8080，也不要在校内路由器上配置公网端口转发。后端 8000 端口只在 Docker 内部网络使用。

## 3. 应用架构和持久化数据

```text
校内浏览器
  -> HTTPS 443
  -> Caddy
       -> /api/*  -> FastAPI backend:8000
       -> 其他路径 -> Vue/Nginx frontend:80

主机 data/
  -> 容器 /app/data
  -> auth.db
  -> <学校标识>/gestor.db、课表、导出文件
```

生产 Compose 只应发布 Caddy 的 80/443 端口。`./data:/app/data` 是业务数据的持久化挂载；删除或重建容器不会删除主机上的 `data`，但删除、损坏或未备份主机目录会丢失数据。

## 4. 获取和传输发布版本

### 4.1 有互联网的目标电脑

目标电脑可以安装 Git 后克隆仓库，也可以直接下载 GitHub Release/源码 ZIP。Git不是运行要求。

```bash
git clone https://github.com/mrtvillaret/fet-substitutions-manager.git
cd fet-substitutions-manager
```

生产目录内不要直接修改源代码。更新时只部署已经测试并打标签的版本。

### 4.2 无互联网的目标电脑（推荐准备方式）

在开发电脑上构建固定版本镜像：

```powershell
$Release = "2026.08.1"

docker build --platform linux/amd64 `
  -t school-substitution-backend:$Release `
  .\backend

docker build --platform linux/amd64 `
  -t school-substitution-frontend:$Release `
  .\frontend

docker pull --platform linux/amd64 caddy:2

docker save -o ".\images-$Release.tar" `
  "school-substitution-backend:$Release" `
  "school-substitution-frontend:$Release" `
  "caddy:2"

Get-FileHash ".\images-$Release.tar" -Algorithm SHA256
```

离线部署包应包含：

```text
release-<版本>/
├── images-<版本>.tar
├── docker-compose.yml
├── Caddyfile
├── .env.template
├── 本文档
└── SHA256SUMS.txt
```

离线 Compose 应将现有 `build:` 改为对应的 `image:`，例如：

```yaml
services:
  backend:
    image: school-substitution-backend:2026.08.1
  frontend:
    image: school-substitution-frontend:2026.08.1
  caddy:
    image: caddy:2
```

其余环境变量、数据挂载、端口、日志和 `restart: unless-stopped` 设置继续复用仓库中的 `docker-compose.yml.example`。在一台干净电脑上完整测试离线包后再带到学校。

## 5. 通用生产配置

### 5.1 创建配置文件

Linux：

```bash
cp .env.example .env
cp docker-compose.yml.example docker-compose.yml
cp Caddyfile.example Caddyfile
```

Windows PowerShell：

```powershell
Copy-Item .env.example .env
Copy-Item docker-compose.yml.example docker-compose.yml
Copy-Item Caddyfile.example Caddyfile
```

### 5.2 设置 `.env`

```env
SECRET_KEY=<32字节随机密钥>
APP_INSTITUCIO=school
DATA_DIR=/app/data
AUTH_DB_PATH=/app/data/auth.db
ADMIN_USERNAME=super_admin
ADMIN_PASSWORD=<仅首次登录使用的强密码>
ADMIN_INSTITUCIO=school
ENVIRONMENT=production
COOKIE_SECURE=true
```

学校标识只使用小写英文字母、数字、点、下划线或连字符，不使用中文、空格和斜线。

Linux 生成密钥：

```bash
openssl rand -hex 32
```

Windows PowerShell 生成密钥：

```powershell
$Bytes = New-Object byte[] 32
$Rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
$Rng.GetBytes($Bytes)
-join ($Bytes | ForEach-Object { $_.ToString("x2") })
$Rng.Dispose()
```

首次登录后立即在系统内修改管理员密码，然后可以清空 `.env` 中的 `ADMIN_PASSWORD`。不要在更新时更换 `SECRET_KEY`，也不要将 `.env` 提交到 Git。

### 5.3 配置内网 HTTPS

首选由学校 IT 提供内网 DNS 和学校 CA 证书。证书私钥只允许部署管理员和系统账户读取。

如果学校没有内部 CA，可以让 Caddy 签发内部证书：

```caddy
substitution.intra.example.edu {
    tls internal
    encode zstd gzip

    handle /api/* {
        reverse_proxy backend:8000
    }

    handle {
        reverse_proxy frontend:80
    }
}
```

启动后导出 Caddy 根证书并交给学校 IT，通过组策略安装到获准访问网站的设备：

```bash
docker compose cp caddy:/data/caddy/pki/authorities/local/root.crt ./school-app-root.crt
```

如果使用 `tls internal`，必须安全备份 Caddy 的 `/data`，因为其中包含内部 CA。不要把根私钥上传到 GitHub。

正式环境不要使用仓库的 HTTP-only 本地 Compose；HTTP 会让登录凭证和学校数据在内网中明文传输。

## 6. Ubuntu Server 部署

### 6.1 要求

- Ubuntu Server 24.04 LTS 64 位。
- 具有 `sudo` 权限的独立维护账户。
- 固定 IP/DNS、正确时区和 NTP 时间同步。
- 建议部署目录 `/opt/substitute-teacher`。

### 6.2 安装 Docker Engine

以下命令来自 Docker 官方 apt 仓库流程；执行前应与官方文档核对：

```bash
sudo apt update
sudo apt install -y ca-certificates curl
sudo install -m 0755 -d /etc/apt/keyrings
sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg \
  -o /etc/apt/keyrings/docker.asc
sudo chmod a+r /etc/apt/keyrings/docker.asc

sudo tee /etc/apt/sources.list.d/docker.sources > /dev/null <<EOF
Types: deb
URIs: https://download.docker.com/linux/ubuntu
Suites: $(. /etc/os-release && echo "${UBUNTU_CODENAME:-$VERSION_CODENAME}")
Components: stable
Architectures: $(dpkg --print-architecture)
Signed-By: /etc/apt/keyrings/docker.asc
EOF

sudo apt update
sudo apt install -y docker-ce docker-ce-cli containerd.io \
  docker-buildx-plugin docker-compose-plugin
sudo systemctl enable --now docker
sudo docker version
sudo docker compose version
```

不必为了省略 `sudo` 而把普通用户加入 `docker` 组；Docker官方说明该组具有接近 root 的权限。维护人员使用 `sudo docker ...` 即可。

### 6.3 安装应用

```bash
sudo mkdir -p /opt/substitute-teacher
sudo chown "$USER":"$USER" /opt/substitute-teacher
cd /opt/substitute-teacher
```

把仓库或离线发布包复制到该目录，完成第 5 节的 `.env`、Compose和 Caddy配置，然后启动：

```bash
sudo docker compose up --build -d   # 源码部署
# 或先 sudo docker load -i images-<版本>.tar，再执行：
sudo docker compose up -d           # 离线镜像部署

sudo docker compose ps
sudo docker compose logs --tail 100
```

Ubuntu/Debian 上 Docker服务默认可以随系统启动，Compose中的 `restart: unless-stopped` 会恢复应用容器。仍必须执行一次完整重启测试。

### 6.4 Linux 网络限制

只发布 Caddy 的 80/443。允许访问的来源范围应优先由学校核心防火墙/VLAN ACL控制。Docker发布端口可能绕过部分 `ufw` 规则，不能只看到 `ufw allow` 就认为访问已经受限；参考 [Docker 与防火墙说明](https://docs.docker.com/engine/install/ubuntu/#firewall-limitations)。

## 7. Windows 10/11 部署

### 7.1 要求

- 受支持的 64 位 Windows 10/11 Education、Pro 或 Enterprise。
- 8 GB 或以上内存。
- BIOS/UEFI 已启用虚拟化。
- 第一次启用 WSL2 时可使用管理员权限。
- 专用 Windows 部署账户，电脑不得睡眠或休眠。

### 7.2 安装 WSL2

管理员 PowerShell：

```powershell
wsl --install --no-distribution
wsl --update
```

重启后检查：

```powershell
wsl --version
wsl --status
```

Docker Desktop不要求另外安装 Ubuntu发行版；日常 Docker命令可以直接在 PowerShell运行。如果 Microsoft Store被学校策略阻止，应提前准备官方 WSL MSI和 Docker Desktop安装程序。

### 7.3 安装 Docker Desktop

安装完成后：

1. 使用 Linux containers。
2. 启用 `Use WSL 2 based engine`。
3. 启用 `Start Docker Desktop when you sign in`。
4. 不启用 Kubernetes。
5. 检查 `docker version` 和 `docker compose version`。

Docker Desktop当前对教育用途免费，但学校仍应确认机构的软件许可政策。

### 7.4 安装应用

建议目录：

```text
C:\SchoolApps\SubstituteTeacher
```

不要放在桌面、下载目录、OneDrive同步目录或网络共享盘。将仓库或离线发布包复制到上述目录，完成第 5 节配置。

离线镜像导入：

```powershell
cd C:\SchoolApps\SubstituteTeacher
docker load -i .\images-2026.08.1.tar
docker compose up -d
docker compose ps
docker compose logs --tail 100
```

源码构建：

```powershell
docker compose up --build -d
```

### 7.5 Windows 防火墙

由学校 IT 将示例网段替换为真实网段：

```powershell
New-NetFirewallRule `
  -DisplayName "School substitution HTTPS" `
  -Direction Inbound `
  -Action Allow `
  -Protocol TCP `
  -LocalPort 443 `
  -RemoteAddress 10.20.0.0/16 `
  -Profile Domain,Private
```

如果教师 Wi-Fi和行政网属于不同的路由网段，应显式加入所有获准网段，不能只使用 `LocalSubnet`。

### 7.6 Windows 重启限制

容器设置了 `restart: unless-stopped`，但必须先有 Docker Desktop运行。Windows重启后需要部署账户登录，Docker Desktop才会根据设置启动。必须保留一个现场联系人处理：

- Windows更新后登录。
- Docker Desktop启动失败。
- 电脑关机、睡眠或硬件故障。

如果学校不能接受这一限制，应改用 Ubuntu Server，或采用下一节的 Hyper-V Ubuntu虚拟机。

## 8. Windows Server 部署

Docker官方明确不支持在 Windows Server上运行 Docker Desktop。本项目使用 Linux容器，不要改造成 Windows容器。

推荐步骤：

1. 由学校 IT 在 Windows Server启用 Hyper-V。
2. 创建 Ubuntu Server 24.04 LTS Generation 2 虚拟机。
3. 分配至少 2 vCPU、4 GB 内存和 40 GB 动态磁盘。
4. 使用 External Virtual Switch接入校内网。
5. 为虚拟机设置 DHCP保留或固定 IP及内部 DNS。
6. 将虚拟机启动行为设为主机启动时自动启动。
7. 在虚拟机内按照第 6 节安装 Docker和应用。
8. 仅通过学校 VPN/管理网段 SSH进入虚拟机维护。

如果 Windows Server本身运行在其他虚拟化平台上，Hyper-V可能需要嵌套虚拟化，应由学校基础设施管理员决定是否可用。不能启用时，请学校直接提供一台 Ubuntu虚拟机。

## 9. 首次上线验收

部署人员和学校 IT共同检查：

- [ ] 从服务器本机访问 `/api/health` 返回 `{"status":"ok"}`。
- [ ] 行政网和教师 Wi-Fi均能通过内网 DNS访问网站。
- [ ] 未获准 VLAN和校外网络无法访问。
- [ ] 浏览器没有 HTTPS证书警告。
- [ ] 后端 8000、前端 80 未直接对客户端暴露。
- [ ] 使用新管理员密码登录，示例密码均已删除。
- [ ] `ENVIRONMENT=production`，`/docs` 和 `/openapi.json` 不公开。
- [ ] 导入课表、调课、查询记录和导出功能正常。
- [ ] 两个普通用户可以同时完成关键操作。
- [ ] 主机重启后服务恢复。
- [ ] 系统时间、时区和 NTP正常。
- [ ] 已完成第一次备份和恢复演练。

## 10. 远程维护方案

应用访问和维护访问必须分开：网站仍然只在校内网开放，维护人员先进入受控维护网络，再连接服务器。

### 10.1 首选：学校 VPN

由学校 IT提供带 MFA的 VPN账号。连接 VPN后：

- Windows 10/11：通过 RDP连接部署电脑。
- Ubuntu/Windows Server内的 Ubuntu VM：通过 SSH密钥连接。
- 仅 VPN地址段或管理 VLAN可以访问 22/3389。

不得将 RDP或 SSH直接暴露到公网。

Linux SSH建议：

- 为每位维护人员创建独立账号。
- 使用每人独立 SSH密钥，不共享私钥。
- 禁止 root远程登录。
- 确认密钥登录正常后再禁用密码登录。
- 离职、设备丢失或职责变更时立即移除相应密钥。

Windows RDP建议：

- 启用网络级别身份验证（NLA）。
- 使用独立维护账号和强密码。
- 仅在学校 VPN/管理网段放行 3389。
- 不把浏览器保存密码当作凭证保管方案。

### 10.2 学校没有 VPN

按优先顺序选择：

1. 请求学校建立 VPN；这是长期维护最合适的方案。
2. 经学校书面批准，使用带 MFA和访问控制的组网 VPN，例如 Tailscale或 ZeroTier；只提供服务器管理地址，不把网站改成公网服务。
3. 临时故障由现场联系人使用 Microsoft Quick Assist等学校批准的屏幕协助工具，并全程有人确认。

任何第三方远程工具都应由学校 IT审批。不要私自安装常驻远控软件，也不要复用个人共享账号。

### 10.3 完全离线的学校

没有任何对外网络时无法真正远程维护。需要：

- 指定现场联系人负责重启电脑、登录 Windows和插入更新介质。
- 使用带校验值的离线发布包。
- 维护者通过电话/视频指导现场人员执行固定命令。
- 每次操作前先备份，现场人员返回日志和校验结果。

## 11. 日常远程检查

在部署目录执行：

```bash
docker compose ps
docker compose logs --since 30m --tail 200
docker stats --no-stream
```

Linux检查磁盘和系统服务：

```bash
df -h
sudo systemctl status docker --no-pager
curl -fsS https://substitution.intra.example.edu/api/health
```

Windows PowerShell检查磁盘和健康端点：

```powershell
Get-PSDrive C
docker compose ps
Invoke-RestMethod https://substitution.intra.example.edu/api/health
```

不要使用 `curl -k` 或跳过证书检查作为长期方案；出现证书错误时应修复 DNS、证书链或客户端信任。

常用恢复动作：

```bash
docker compose restart backend
docker compose up -d
docker compose logs backend --tail 200
docker compose logs caddy --tail 200
```

不要把 `docker compose down -v` 写进维护流程；`-v` 会删除命名卷，可能同时删除 Caddy证书数据。

## 12. 备份和恢复

### 12.1 必须备份的内容

- `data/`：用户、SQLite数据库、课表和导出文件。
- `.env`：JWT密钥和运行配置，必须加密并限制权限。
- `docker-compose.yml` 和 `Caddyfile`。
- 学校 HTTPS证书/私钥，或者 Caddy `/data`。
- 当前部署版本号和对应 Git提交。

日志是否备份及保存多久，由学校的数据保护政策决定。访问日志包含用户名、IP和请求路径，应限制读取权限和保留时间。

### 12.2 一致的 SQLite备份

业务量较小时，最可靠的简单方法是短暂停止后端再复制：

```bash
docker compose stop backend
# 将 data/ 复制到学校 NAS 或加密备份位置
docker compose start backend
```

自动备份脚本必须使用 `try/finally` 或等效错误处理，保证复制失败时也会重新启动后端。不要只备份数据库而遗漏上传课表和配置文件。

建议最低策略：

- 每日备份一次到另一台设备。
- 更新前额外备份一次。
- 至少保留 7 个每日版本和 4 个每周版本，最终以学校政策为准。
- 每学期至少做一次恢复演练。

### 12.3 恢复步骤

1. 确认恢复点和应用版本。
2. `docker compose stop` 停止应用。
3. 将当前 `data` 改名保留，不立即删除。
4. 把备份的 `data`、配置和证书恢复到原位置。
5. `docker compose up -d`。
6. 检查 `/api/health`、登录、查询、保存和导出。
7. 确认恢复成功后，再按学校保留政策处理旧数据。

## 13. 远程更新和回滚

### 13.1 更新原则

- 不在生产服务器上直接编辑代码。
- 不自动追踪 `main` 并无人值守更新。
- 每个部署版本对应一个 Git标签、镜像标签和发布说明。
- 更新前备份，更新后执行验收清单。
- 保留上一个可用镜像和部署包。

### 13.2 在线源码更新

只部署明确版本，不直接 `git pull` 未审核的最新代码：

```bash
git fetch --tags
git checkout <已测试的版本标签>
docker compose up --build -d
docker compose ps
docker compose logs --tail 100
```

### 13.3 离线镜像更新

```bash
docker load -i images-<新版本>.tar
# 将 docker-compose.yml 中的 image 标签改为新版本
docker compose up -d
docker compose ps
```

随后检查健康端点并完成功能冒烟测试。

### 13.4 回滚

1. 将 Compose中的镜像标签改回上一版。
2. `docker compose up -d`。
3. 如果新版修改了数据结构并导致旧版无法读取，停止应用并恢复更新前备份。
4. 记录故障时间、版本、日志和回滚结果。

## 14. 安全和交接

- 网站只允许校内网访问；远程维护只允许 VPN/管理网络访问。
- VPN、远控和 GitHub账号启用 MFA。
- 每位管理员使用独立账号，不共享个人账号。
- `.env`、数据库、备份和证书私钥不得上传 GitHub。
- Windows启用 BitLocker，Linux使用学校批准的磁盘加密方案。
- 服务器不用于浏览网页、收邮件或日常办公。
- 及时安装操作系统、Docker和安全更新，但先在非生产环境测试应用更新。
- 保留维护记录：日期、人员、原因、命令、版本、备份和结果。
- 项目使用 AGPL许可证；应保留部署版本对应的完整源代码和许可证信息。

学校至少应保管以下交接资料：

```text
服务器位置、资产编号、系统版本
固定 IP、内网 DNS、允许访问的 VLAN
部署目录和当前应用版本
VPN/RDP/SSH 维护方式
管理员和紧急恢复账号的保管人
备份位置、频率、保留期限和最近恢复测试日期
证书到期时间和负责人
现场联系人及故障升级流程
```

## 15. 故障速查

| 现象 | 首先检查 |
|---|---|
| 全校都打不开 | 主机电源、网络、DNS、Docker服务、`docker compose ps` |
| 首页能开但操作报错 | `docker compose logs backend`、`/api/health` |
| 只有部分网络打不开 | VLAN路由、防火墙来源网段、DNS |
| HTTPS证书警告 | 域名是否匹配、证书是否过期、内部 CA是否已下发 |
| Windows重启后离线 | 部署账户是否登录、Docker Desktop是否启动 |
| Linux重启后离线 | `systemctl status docker`、容器 restart策略 |
| 磁盘空间不足 | Docker日志、旧镜像、导出文件和备份是否堆积 |
| 登录突然失效 | 系统时间、`SECRET_KEY` 是否被更换、Cookie的 HTTPS设置 |
| 数据异常 | 立即停止写入，保留现状，检查日志和最近备份，不要先覆盖数据 |
