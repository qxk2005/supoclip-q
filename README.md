# Fuck OpusClip.

…好剪辑不该又贵又带丑水印。

<p align="center">
  <a href="https://www.supoclip.com">
    <img src="assets/banner2.png" alt="SupoClip Banner" width="100%" />
  </a>
</p>

OpusClip 订阅约每月 15–29 美元，免费档还会打水印。SupoClip 提供类似的 AI 切片能力：开源、自托管时无平台水印；另有可选的托管版本。

> 托管版等候名单：[SupoClip Hosted](https://www.supoclip.com)

## 为什么要做 SupoClip

### OpusClip 侧的问题

长视频转短视频、字幕、爆款打分、模板等功能很强，但免费额度紧、免费导出常带水印、付费仍有分钟上限，且工作流绑在对方平台上。

### SupoClip 的定位

- **自托管**：数据与算力边界由你掌控。  
- **自部署无 OpusClip 式平台水印**（与官方免费档对比）。  
- **AGPL-3.0**：代码可审可改。  
- **托管产品**：当 `SELF_HOST=false` 时走 Stripe 等商业化与额度限制（详见仓库根目录 `.env.example` 中与计费相关的变量）。

## 仓库当前实际在做什么

单体仓库：**Next.js 15**（App Router）前端、**FastAPI** 后端（入口 `src/main_refactored.py`）、**ARQ** 异步任务 + **Redis** 队列、**PostgreSQL** 存任务 / 切片 / 认证等数据。

| 层级 | 实际情况 |
|------|----------|
| **转写** | **faster-whisper**（本机 CPU），词级时间轴缓存在视频同目录的 `.transcript_cache.json`。处理模式会选用不同 whisper 体量（如 `FAST_MODE_TRANSCRIPT_MODEL` 等）。 |
| **选片** | **pydantic-ai** + 你在 `LLM` 里配置的模型（Google / OpenAI / Anthropic / Ollama）分析带时间戳的转写文本。 |
| **成片** | **MoviePy**：默认竖屏 9:16（也可保留原画幅）、人脸相关裁切、字幕模板、可选 B-roll（Pexels）。 |
| **双语字幕** | 任务字段 `bilingual_subtitles_mode`：`auto` 在判定为偏英文内容时叠加 **中文主行 + 英文辅行**（英文字号比你在界面里选的主字号小 2）。短语翻译与选片共用同一套 `LLM`。数据库迁移见 `backend/migrations/006_add_bilingual_subtitles.sql`，创建任务时 JSON 里可传 `bilingual_subtitles_mode`。 |
| **遗留入口** | `src/main.py` 中仍可见 AssemblyAI 等旧路径说明；**日常开发请使用 `main_refactored` + Worker**，不要依赖该遗留入口。 |

## 快速开始

### 环境要求

- **PostgreSQL 15+**、**Redis**、系统 **ffmpeg** 在 `PATH` 中  
- **Python 3.11+**，包管理推荐 [**uv**](https://github.com/astral-sh/uv)  
- 前端需 **Node.js**（建议 LTS）  
- **至少一种 LLM**（或本机 Ollama）：与 `LLM=provider:model` 对应，用于选片分析；开启双语时也会用于短语翻译  
- 可选：**Pexels**（`PEXELS_API_KEY`）、**Apify**（`APIFY_API_TOKEN`，部分 YouTube 下载链路）、托管计费时的 **Resend** / **Stripe** 等  

### 1. 克隆与配置

```bash
git clone <your-fork-or-upstream-url>
cd supoclip
cp .env.example .env
# 复制示例后编辑 .env：DATABASE_URL、Redis、LLM 及对应 API Key 等
```

`.env.example` 里仍保留 `ASSEMBLY_AI_API_KEY` 字段，多为历史/兼容用途；**当前 refactored 的 Worker 流水线做转写不依赖它**（本机 faster-whisper）。若你本地其它工具仍读取该变量，可留空，仅跑 whisper 流程也能工作。

本地能跑通一条任务的最小变量示例（变量名保持英文，与代码一致）：

```env
# 后端 asyncpg 连接串（示例占位，请换成你的库名与账号）
DATABASE_URL=postgresql+asyncpg://user:pass@localhost:5432/supoclip
# 前端 Prisma 常用 postgresql://（同步驱动）；与上句可写在不同 .env 供各自进程读取

REDIS_HOST=localhost
REDIS_PORT=6379

LLM=google-gla:gemini-3-flash-preview
GOOGLE_API_KEY=your_key

BETTER_AUTH_SECRET=change_me
```

可选：Whisper 体量与 fast 模式切片数量等（仍使用仓库内已有变量名）：

```env
# 以下为可选调参；取值仍须与代码/文档中枚举一致
DEFAULT_PROCESSING_MODE=fast
FAST_MODE_MAX_CLIPS=4
FAST_MODE_TRANSCRIPT_MODEL=tiny
BALANCED_MODE_TRANSCRIPT_MODEL=medium
QUALITY_MODE_TRANSCRIPT_MODEL=large-v3
```

### 2. 数据库结构

```bash
# 仓库根目录：基础表结构
psql "$DATABASE_URL" -f init.sql

# 若数据库早于当前仓库，请顺序执行 backend 下增量 SQL
for f in backend/migrations/*.sql; do psql "$DATABASE_URL" -f "$f"; done

# 前端 Prisma（Better Auth、Task 等由 Prisma 管理的表）
cd frontend && npx prisma migrate deploy
```

**说明**：Python 后端连接串常用 `postgresql+asyncpg://`；前端 Prisma 侧常见为 `postgresql://`（同步驱动）。两套 URL 分别写在各自运行环境使用的 `.env` 里即可。

### 3. 跑起来（建议三个终端）

```bash
./start.sh
# 打印本地自检清单，再按其提示在其它终端启动各进程
```

典型三条命令对应：

1. **API**：`cd backend && uv sync && source .venv/bin/activate && uvicorn src.main_refactored:app --reload --host 0.0.0.0 --port 8000`  
2. **Worker**（必须，否则任务会一直排队）：`cd backend && source .venv/bin/activate && arq src.workers.tasks.WorkerSettings`  
3. **前端**：`cd frontend && npm install && npm run dev`  

- 前端：http://localhost:3000  
- API 文档：http://localhost:8000/docs  

### 4. 常见问题（精简）

| 现象 | 建议检查 |
|------|----------|
| 启动报 API Key | `LLM` 前缀与已配置的 Key 一致（如 `GOOGLE_API_KEY`）；若用 `LLM=ollama:...`，本机需已启动 Ollama。 |
| 任务一直 **queued** | Worker 是否在跑；Redis 是否可达。 |
| Prisma / 数据库报错 | 是否已 `migrate deploy`；前后端 `DATABASE_URL` 驱动是否与连接串匹配。 |
| 字体列表为空 | 将字体文件放入 `backend/fonts/` ——说明见 [backend/fonts/README.md](backend/fonts/README.md)。 |

更细的排错：[docs/troubleshooting.md](docs/troubleshooting.md)，开发约定另见 [CLAUDE.md](CLAUDE.md)、[AGENTS.md](AGENTS.md)。

## 使用说明（前端界面）

以下说明与当前 Next.js 前端界面一致：登录后默认进入首页 `/`，主要路由还有「生成记录」`/list`、单任务详情 `/tasks/[id]`、剪辑工作室 `/tasks/[id]/edit`、账户「设置」`/settings`。本地开发时前端一般为 http://localhost:3000。

### 界面总览与典型路径

```mermaid
flowchart LR
  A["首页 / 新建剪片任务"] --> B["任务详情 /tasks/id"]
  B --> C["剪辑工作室 /tasks/id/edit"]
  A --> D["生成记录 /list"]
  A --> E["设置 /settings"]
  D --> B
```

- **顶栏**：左侧为 SupoClip 标识；桌面端可见「全部生成」、（管理员）「管理后台」、「退出登录」、头像与邮箱（点击可进设置）；移动端为汉堡菜单，内含相同入口。
- **首页横幅**：若存在最近一次任务，会显示「最近一条生成」卡片（标题、来源类型、日期、片段数、状态），点击进入对应任务详情。

### 场景一：从 YouTube 或本地文件新建任务

在首页 **「新建剪片任务」** 区域：

1. **来源**  
   - 点选 **「YouTube 链接」**：在带 YouTube 图标的输入框粘贴完整视频 URL。  
   - 点选 **「上传视频」**：点击虚线框或拖放文件（界面提示支持常见格式、约 500MB 上限）。

2. **「AI 设置」卡片**（界面标题带语言图标）  
   - **视频语言**：自动检测 / 英语 / 中文，影响转写与后续分析。  
   - **AI 分析分块大小**：超长视频分段分析；问号提示说明「越小越省内存、可能损失上下文」，默认约 15000。  
   - **专业热词（可选）**：多行或逗号分隔，用于纠正 Whisper 与选片文案中的专名。  
   - **处理模式**：**快速** / **均衡** / **质量**（问号内说明速度与片段数量的权衡）。

3. **「样式与字幕」卡片**  
   - **字幕样式**：下拉选择后端返回的字幕模板（名称与简短描述并列）。  
   - **AI B-Roll**（仅当服务端已配置 Pexels 时出现）：开关「自动从 Pexels 匹配素材」。  
   - **宽屏比例**：打开则 **保留原始画幅**；关闭则默认 **9:16 竖屏**。  
   - **烧录字幕**：关闭可加快处理（成片无内嵌字幕）。  
   - **双语字幕**（在开启烧录字幕时）：**自动** / **始终双语** / **关闭**（自动模式下纯英文内容会中英叠行，界面有字号说明）。  
   - **音频淡入 / 音频淡出**：控制成片首尾原声音量渐变。

4. **「字体自定义」**（仅在开启 **烧录字幕** 时展开；可点 **展开/收起**）  
   - **上传字体**（.ttf/.otf；托管环境下可能仅限 Pro）。  
   - **搜索字体** + 下拉选择 **字体族**；**字号** 滑块、**颜色** 色盘与快捷色块。

5. **右侧「实时预览」（大屏）**  
   - 模拟手机竖屏：YouTube 会显示封面模糊背景，本地上传会取视频首帧；中间有 **「字幕预览效果」** 文案，随你选的字体/字号/颜色变化；下方汇总当前字体名、字号、颜色与模板名。

6. 点击 **「开始处理视频」** 后，前端会创建任务并 **跳转到该任务的详情页** `/tasks/{task_id}`。底部小字提示完成通知邮件与 **「设置」** 中的偏好相关。

### 场景二：在任务详情页跟进进度与粗剪

路径：**`/tasks/[id]`**（标题区显示素材名、来源类型、创建时间、状态）。

- **排队中 / 处理中**  
  - 中部为动画点与 **进度文案**（如「排队等待中」或后端推送的阶段说明）；有百分比时显示细 **进度条**。  
  - 处理过程中若已有片段就绪，会显示 **「已有 N 个片段就绪」** 的列表，每段含播放器、时间范围、**传播力/相关度** 徽章、**转写文本**、**AI 分析**、**下载**。  
  - 工具条：**「项目设置」**（侧栏里可改字体、模板、B-roll、淡入淡出、处理模式等并可选应用到已有片段）、**「取消」** 中止任务。

- **已完成**  
  - 每条片段卡片左侧为视频，右侧为文案与分数；可勾选 **「加入合并」**，选中至少两段后出现 **「合并所选」**。  
  - 单条片段内可进行 **裁剪**（入点/出点偏移）、**分割**、**字幕**（文案、位置、高亮词）、**导出**（预设如下拉中的 TikTok 等），以及 **下载**。  
  - 标题旁 **「打开编辑器」** 进入 **剪辑工作室**（见下）。  
  - **「项目设置」** 与处理中相同逻辑，用于批量重设样式或重跑相关选项。

- **失败 / 已取消**  
  - **「恢复」** 可重新入队；失败页会展示错误说明并可返回首页重试。

### 场景三：生成记录里批量管理

路径：**`/list`**（标题 **「生成记录」**）。

- 列表每行：多选框、标题（点击进入任务详情）、来源类型、时间、片段数、状态徽标（已完成 / 处理中 / 排队中 / 失败 / 已取消等）。  
- 顶部可选 **全选**；选中后底部浮层 **命令条** 提供：**取消**（进行中的任务）、**恢复**（失败或已取消）、**删除**（需确认对话框）。  
- 空状态引导 **「新建生成」** 回首页。

### 场景四：设置与计费（若开启商业化）

路径：**`/settings`**。

- 默认字体、字号、颜色会作为 **新建任务时的默认值**（与首页加载偏好一致）。  
- 可配置 **任务完成邮件通知** 等偏好。  
- 若 `monetization_enabled` 为真，会展示套餐、用量条与订阅/门户入口；首页顶栏也会显示 **Pro/免费** 与用量。

### 场景五：剪辑工作室（浏览器内精细调节与导出）

路径：**`/tasks/[id]/edit`**，入口为任务详情页 **「打开编辑器」**；页眉带 **「剪辑工作室」** 徽章与 **「导出当前片段」**。

- 仅当任务 **已完成** 且存在片段时可编辑；否则会提示返回任务页。  
- **左侧主区**：当前选中片段的视频预览（可叠加 **字幕预览**）、播放头滑条、**±1s**、**设为入点/出点**、**裁剪范围** 双滑块与 **应用裁剪**。  
- **右侧「精细调节」**：**分割**（对齐播放头 / 分割片段）、**音频**（音量、倍速、静音）、**画面效果**（亮度、对比度、饱和度、模糊、色相、缩放）等滑块。  
- **导出**：将当前调节（含裁剪区间与画面滤镜）通过浏览器端处理生成文件；与任务页 **服务端按预设导出** 互为补充，适合快速试效果。

---

> 说明：未登录时通常看到落地页或登录引导；若部署侧将应用配置为「仅展示落地页」模式，首页可能不显示上述工作台，以实际环境变量与前端配置为准。

## 测试

仓库内**已包含**自动化测试，覆盖深度因模块而异。

| 命令 | 作用 |
|------|------|
| `make test` | 后端 pytest + 前端 Vitest（带覆盖率），具体环境变量见 Makefile。 |
| `make test-backend` | `cd backend && uv sync --all-groups && pytest`；**注意** `pyproject.toml` 里对**部分模块**开启了 `--cov-fail-under=65`（如 `auth_headers`、`billing_service`）。 |
| `make test-frontend` | Vitest 带覆盖率。 |
| `make test-e2e` | Playwright；会先执行 `prisma migrate deploy`。 |

仅想快速跑后端单元测试、暂时不看覆盖率门禁时：

```bash
cd backend && uv run pytest tests/unit/ -q --no-cov
# --no-cov：跳过 pyproject 中的覆盖率与 fail-under 门禁，便于本地快速跑单测
```

全链路本地测试默认假定本机 Postgres / Redis 可用；Makefile 里默认示例指向 `127.0.0.1`，可按需改 `DATABASE_URL` / `TEST_DATABASE_URL`。

## 文档

更完整的说明在 [`docs/`](docs/README.md)：

- [docs/setup.md](docs/setup.md) · [docs/configuration.md](docs/configuration.md) · [docs/app-guide.md](docs/app-guide.md)  
- [docs/architecture.md](docs/architecture.md) · [docs/api-reference.md](docs/api-reference.md) · [docs/development.md](docs/development.md) · [docs/troubleshooting.md](docs/troubleshooting.md)  

## 托管计费（可选）

开启商业化（`SELF_HOST=false`）时会走 Stripe、Resend 等流程；环境变量见仓库内 `STRIPE_*`、`RESEND_*`、`BACKEND_AUTH_SECRET` 等与上文文档。

## 许可证

SupoClip 使用 **AGPL-3.0** 发布，全文见 [LICENSE](LICENSE)。
