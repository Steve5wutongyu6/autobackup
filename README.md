# AutoBackup

## 一、项目介绍

`AutoBackup` 是一个基于 `FastAPI + PostgreSQL + Vue3 + Element Plus` 实现的自动备份系统，主要用于对服务器指定目录进行定时打包、上传腾讯云 COS，并提供后台管理、恢复、日志审计等功能。

该项目用于：

1. 定时备份服务器目录
2. 将备份文件上传到一个或多个 COS 存储桶
3. 对备份产物进行统一管理和恢复
4. 尽量优先走 COS 内网，避免公网下载费用
5. 提供管理员后台、双因素登录和操作日志


## 二、主要功能

### 1. 备份任务管理

1. 支持新增、编辑、启用、禁用备份任务
2. 支持按固定间隔执行
3. 支持按每周指定星期和时间执行
4. 支持手动立即执行任务
5. 支持为 ZIP 压缩包设置密码

### 2. 备份产物管理

1. 自动将源目录打包为 `zip`
2. 使用 AES ZIP 加密方式写入压缩包
3. 支持同一个备份任务上传到多个存储桶
4. 上传成功后自动删除本地产物，减少磁盘占用
5. 按逻辑产物聚合展示多桶副本，避免重复显示

### 3. COS 管理

1. 支持维护 COS 凭据
2. 支持维护 COS 存储桶配置
3. 支持检测存储桶域名解析结果
4. 支持判断当前访问是否为内网地址
5. 支持删除 COS 中的对象副本

### 4. 恢复管理

1. 支持从备份产物创建恢复任务
2. 支持恢复到原目录或指定目录
3. 恢复前优先尝试内网副本
4. 如果不是内网链路，可以暂停并等待人工确认

### 5. 安全相关

1. COS `SecretId`、`SecretKey`、会话令牌加密存储
2. 管理员用户名密码不直接明文落库
3. 支持用户名密码登录
4. 支持 `TOTP` 二次验证
5. 支持 `Passkey / WebAuthn` 二次验证
6. 首次登录后要求完成初始化配置

### 6. 审计与日志

1. 记录系统启动日志
2. 记录备份任务保存、执行等操作
3. 记录 COS 凭据、存储桶管理操作
4. 记录管理员相关操作

## 三、项目结构

```text
autobackup
├── backend
│   ├── app
│   │   ├── api            # FastAPI 路由
│   │   ├── core           # 配置、日志、安全相关
│   │   ├── db             # 数据库初始化
│   │   ├── models         # ORM 实体
│   │   ├── repositories   # 数据访问层
│   │   ├── schemas        # Pydantic 请求响应模型
│   │   ├── services       # 业务服务层
│   │   └── workers        # APScheduler 定时任务进程
│   ├── Dockerfile
│   └── pyproject.toml
├── frontend
│   ├── src
│   │   ├── api            # 前端请求封装
│   │   ├── router         # 路由
│   │   ├── stores         # Pinia 状态管理
│   │   ├── styles         # 样式
│   │   ├── utils          # WebAuthn 等工具
│   │   └── views          # 页面
│   ├── Dockerfile
│   └── package.json
├── deploy
│   └── nginx
│       └── default.conf   # 前端静态资源和 API 反向代理
├── runtime-data           # 默认挂载的备份根目录
├── docker-compose.yml
├── .env.example
├── COS文档.md
└── 需求文档.md
```

## 四、开发环境

### 1. 后端

1. `Python 3.14`
2. `FastAPI`
3. `SQLAlchemy`
4. `PostgreSQL`
5. `APScheduler`
6. `cos-python-sdk-v5`

### 2. 前端

1. `Node.js 24.15.0`
2. `Vite 7`
3. `Vue 3`
4. `Pinia`
5. `Vue Router`
6. `Element Plus`

### 3. 部署相关

1. `Docker`
2. `Docker Compose`
3. `Nginx`


## 五、运行前说明

系统默认包含 4 个服务：

1. `postgres`：数据库
2. `api`：后端接口服务
3. `worker`：备份调度与恢复轮询进程
4. `web`：前端静态页面与 Nginx 代理

默认端口如下：

1. 前端：`8080`
2. 后端：`8000`
3. PostgreSQL：容器内使用，默认未直接暴露到宿主机

## 六、环境变量配置

可参考根目录下的 `.env.example`。

需要说明一下：

1. `.env.example` 目前主要作为参数示例使用
2. 当前仓库里的 `docker-compose.yml` 直接把环境变量写在了 `environment` 段中
3. 如果你走容器部署，需要同步修改 `docker-compose.yml` 里的对应值，或者自行改造成 `env_file` 方式

```env
DATABASE_URL=postgresql+psycopg://autobackup:autobackup@postgres:5432/autobackup
APP_MASTER_KEY=replace-with-a-strong-random-string
JWT_SECRET=replace-with-a-strong-random-string
BOOTSTRAP_ADMIN_USERNAME=admin
BOOTSTRAP_ADMIN_PASSWORD=change-me-now
BACKUP_ALLOWED_ROOTS=/data
BACKUP_TEMP_DIR=/tmp/autobackup
CORS_ORIGINS=http://localhost:8080,http://localhost
WEBAUTHN_RP_ID=localhost
WEBAUTHN_RP_NAME=AutoBackup
WEBAUTHN_EXPECTED_ORIGINS=http://localhost:8080,http://localhost:5173,http://127.0.0.1:8080,http://127.0.0.1:5173
```

各字段说明如下：

| 变量名 | 说明 |
| --- | --- |
| `DATABASE_URL` | PostgreSQL 连接地址 |
| `APP_MASTER_KEY` | 应用主密钥，用于敏感信息加密 |
| `JWT_SECRET` | 登录态签名密钥 |
| `BOOTSTRAP_ADMIN_USERNAME` | 初始管理员用户名 |
| `BOOTSTRAP_ADMIN_PASSWORD` | 初始管理员密码 |
| `BACKUP_ALLOWED_ROOTS` | 允许备份和恢复的根目录，多个值可用逗号分隔 |
| `BACKUP_TEMP_DIR` | 临时压缩包生成目录 |
| `CORS_ORIGINS` | 允许访问 API 的前端来源 |
| `WEBAUTHN_RP_ID` | Passkey 依赖域名 |
| `WEBAUTHN_RP_NAME` | Passkey 显示名称 |
| `WEBAUTHN_EXPECTED_ORIGINS` | WebAuthn 允许的前端来源 |

## 七、Docker 部署方式

### 1. 克隆项目

```bash
git clone <your-repo-url>
cd autobackup
```

### 2. 准备环境变量

如果你准备直接用 `docker compose`，建议先参考 `.env.example`，把 `docker-compose.yml` 中 `api` 和 `worker` 的环境变量改成你自己的配置。

如果你想保留一份本地参数文件，也可以先复制一份：

```bash
cp .env.example .env
```

需要特别注意下面几项：

1. `APP_MASTER_KEY` 不要使用默认值
2. `JWT_SECRET` 不要使用默认值
3. `BOOTSTRAP_ADMIN_PASSWORD` 第一次部署前就应改掉
4. `BACKUP_ALLOWED_ROOTS` 需要和实际挂载目录一致

### 3. 准备备份目录

项目默认把宿主机的 `./runtime-data` 挂载到容器内的 `/data`。

也就是说：

1. 备份源目录需要放在 `runtime-data` 下，或者
2. 你自己修改 `docker-compose.yml` 中的挂载路径与 `BACKUP_ALLOWED_ROOTS`

### 4. 启动项目

```bash
docker compose up -d --build
```

### 5. 查看运行状态

```bash
docker compose ps
```

### 6. 查看日志

```bash
docker compose logs -f api
docker compose logs -f worker
docker compose logs -f web
```

### 7. 访问系统

浏览器打开：

```text
http://localhost:8080
```

后端健康检查地址：

```text
http://localhost:8000/
```

返回结果类似：

```json
{"status":"ok","app":"AutoBackup"}
```

## 八、本地开发方式

### 1. 启动 PostgreSQL

可以直接复用 `docker compose` 里的数据库，也可以自己单独起一个 PostgreSQL。

### 2. 启动后端

```bash
cd backend
python -m pip install --upgrade pip
python -m pip install .
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

### 3. 启动调度进程

另开一个终端：

```bash
cd backend
python -m app.workers.scheduler
```

### 4. 启动前端

```bash
cd frontend
npm install
npm run dev
```

启动完成后默认访问：

```text
http://localhost:5173
```

## 九、使用流程

### 1. 首次登录

系统第一次启动后，需要先完成管理员初始化流程。

大致流程如下：

1. 使用环境变量中提供的初始管理员账号登录
2. 系统检测到当前账号尚未完成初始化
3. 跳转到初始化页面
4. 修改管理员用户名和密码
5. 配置 TOTP 或 Passkey

### 2. 配置 COS 凭据

在后台中先创建 COS 凭据，再配置存储桶。

建议顺序：

1. 新增 `SecretId / SecretKey`
2. 如果使用临时凭据，可补充 `SessionToken`
3. 录入存储桶名称、AppId、地域、访问模式
4. 执行连通性检查

### 3. 配置备份任务

创建任务时至少要填写：

1. 任务名称
2. 源目录
3. 压缩包密码
4. 调度方式
5. 目标存储桶

其中调度方式支持：

1. `interval`：按分钟间隔执行
2. `weekly`：按每周指定星期和时间执行

### 4. 查看备份产物

任务执行后，系统会生成逻辑产物记录，并关联多个 COS 副本。

在产物列表中可以看到：

1. 压缩包名称
2. 文件大小
3. SHA256
4. 任务状态
5. 每个副本对应的存储桶与上传状态

### 5. 执行恢复

恢复时，系统会优先选择已验证的内网副本。

如果检测到需要走公网下载，应由前端提示用户确认后再继续，这样可以尽量避免不必要的公网流量费用。

## 十、前端页面说明

当前路由页面主要包括：

| 路径 | 说明 |
| --- | --- |
| `/login` | 登录页 |
| `/bootstrap` | 首次初始化页 |
| `/` | 仪表盘 |
| `/buckets` | COS 存储桶管理 |
| `/tasks` | 备份任务管理 |
| `/artifacts` | 备份产物管理 |
| `/restore` | 恢复任务管理 |
| `/admin` | 管理员中心 |
| `/logs` | 日志查看 |

## 十一、后端接口概览

这里只列出目前比较核心的一部分接口，便于快速对照。

### 1. 认证相关

| 方法 | 地址 | 说明 |
| --- | --- | --- |
| `GET` | `/api/auth/bootstrap-status` | 查询初始化状态 |
| `POST` | `/api/auth/login` | 用户名密码登录 |
| `POST` | `/api/auth/2fa/totp/verify` | 验证 TOTP |
| `POST` | `/api/auth/2fa/passkey/options` | 获取 Passkey 登录选项 |
| `POST` | `/api/auth/2fa/passkey/verify` | 校验 Passkey |
| `POST` | `/api/auth/refresh` | 刷新令牌 |

### 2. COS 相关

| 方法 | 地址 | 说明 |
| --- | --- | --- |
| `POST` | `/api/cos/credentials` | 新增 COS 凭据 |
| `GET` | `/api/cos/credentials` | 查询 COS 凭据 |
| `DELETE` | `/api/cos/credentials/{credential_id}` | 删除未被引用的 COS 凭据 |
| `POST` | `/api/cos/buckets` | 新增存储桶 |
| `GET` | `/api/cos/buckets` | 查询存储桶 |
| `PUT` | `/api/cos/buckets/{bucket_id}` | 修改存储桶 |
| `POST` | `/api/cos/buckets/{bucket_id}/check` | 检测存储桶连通性 |
| `DELETE` | `/api/cos/buckets/{bucket_id}` | 删除存储桶 |

### 3. 备份相关

| 方法 | 地址 | 说明 |
| --- | --- | --- |
| `POST` | `/api/backup-tasks` | 新增备份任务 |
| `GET` | `/api/backup-tasks` | 查询备份任务 |
| `GET` | `/api/backup-tasks/{task_id}` | 查询单个任务 |
| `PUT` | `/api/backup-tasks/{task_id}` | 修改任务 |
| `POST` | `/api/backup-tasks/{task_id}/run` | 立即执行任务 |
| `GET` | `/api/artifacts` | 查询备份产物 |
| `DELETE` | `/api/artifacts/{artifact_id}` | 删除备份产物 |
| `POST` | `/api/artifacts/{artifact_id}/restore` | 创建恢复任务 |

## 十二、几个实现说明

### 1. 定时任务

调度器使用的是 `APScheduler`，独立运行在 `worker` 服务中。

目前已实现：

1. 间隔任务 `IntervalTrigger`
2. 周期任务 `CronTrigger`
3. 每分钟轮询待执行恢复任务

### 2. 压缩与加密

备份时使用 `pyzipper` 生成 AES ZIP 压缩包，并写入 `manifest.json`，便于后续恢复时识别来源。

### 3. 路径限制

后端会校验备份源目录和恢复目标目录是否在 `BACKUP_ALLOWED_ROOTS` 范围内，防止越权访问任意路径。

### 4. 内外网识别

项目会通过 `nslookup` 和 IP 判断逻辑识别 COS 域名解析结果是否属于内网地址，并记录相应状态。

## 十三、注意事项

1. 生产环境务必修改默认管理员账号密码
2. `APP_MASTER_KEY` 和 `JWT_SECRET` 必须使用高强度随机值
3. `BACKUP_ALLOWED_ROOTS` 不要直接放开到过大的系统目录
4. 如果要恢复到宿主机真实目录，请先确认 Docker 挂载关系
5. 使用 `Passkey` 时，`WEBAUTHN_RP_ID` 和实际访问域名要对应
6. 如需公网访问后台，请同步修改 `CORS_ORIGINS` 和 `WEBAUTHN_EXPECTED_ORIGINS`

## 十四、后续可完善的点

1. 增加更完整的数据库迁移脚本
2. 补充单元测试和集成测试
3. 增加任务执行历史和失败重试策略
4. 增加更细粒度的权限控制
5. 增加对象生命周期和保留策略

## 十五、参考文档

1. [需求文档](./需求文档.md)
2. [COS文档](./COS文档.md)

## 十六、启动命令汇总

### 1. 容器部署

```bash
docker compose up -d --build
```

### 2. 关闭服务

```bash
docker compose down
```

### 3. 查看日志

```bash
docker compose logs -f
```

### 4. 本地前端开发

```bash
cd frontend
npm install
npm run dev
```

### 5. 本地后端开发

```bash
cd backend
python -m pip install .
uvicorn app.main:app --reload
```
