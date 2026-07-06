# 译如原（TransTeX）— LaTeX 论文翻译产品

> 品牌名：**译如原**（对外中文名）· 代号 **TransTeX**（仓库/包名）。
> 含义:译文如同原版——公式、图表、引用、LaTeX 排版原样保留,翻译不走样。

把 arXiv 英文论文一键翻译成中文 PDF(可选中英对照),完整保留 LaTeX 排版、公式、图表、引用。

## 架构

```
textrans/          翻译内核(MIT)—— 二值掩码 + 链表 + 顺序合并
  core/            mask 掩码规则 · linkedlist · split · merge · fix · compile · pdf · cache · pipeline
  llm/             多模型抽象(kimi / openai,可扩展)
  latexutil/       arXiv 下载 · 中文字体注入 · cls 修复 · PDF 水印
textrans_api/      FastAPI 后端 —— REST + WebSocket 进度 + PDF 下载
dochero-ai/        Next.js 前端 —— arXiv 链接/zip 上传 · 实时进度 · 结果下载
legacy/            旧脚本归档(已被上面取代,保留备查)
gpt_academic/      算法思路参考(GPL v3,不进发布,见下)
```

### 核心设计:为什么不会翻坏

旧方案用「编号回填」(把段落编号发给 LLM 再按号找回),模型一漏号就整篇错位,还需一堆事后修复脚本。新内核改用 **二值掩码**:

1. **mask** — 给源码每个字符标记「翻译 / 保护」。公式、命令、`\cite`、图表、注释保护;`\caption`/`\abstract`/`\section` 的**花括号内部**挖回翻译。
2. **linkedlist** — 转成交替的保护段/翻译段;翻译段边界空白归还相邻保护段(根治 `\quad Kernel→\quadKernel` 命令粘连)。
3. **merge** — 按链表**顺序**拼回,无编号 → 对齐崩坏在协议上不可能发生。`fix_content` 对每段做安全修复(命令数不符/括号不平 → 回退原文)。
4. **compile** — 编译失败时从 `.log` 提取报错行号,把命中的译文段回退成原文再重编译(最多 32 轮)。

## 快速开始

### 依赖
```bash
pip install -r requirements.txt          # Python(含 fastapi/uvicorn/tiktoken)
cd dochero-ai && npm install             # 前端
```
系统需装 XeLaTeX(`xelatex`/`bibtex`/`latexmk`)与中文字体(macOS 建议 Noto CJK)。
翻译 API key:`export KIMI_API_KEY=...`(或 `OPENAI_API_KEY` + `TEXTRANS_PROVIDER=openai`)。

### CLI(最快)
```bash
python3 -m textrans 2606.20781 --provider kimi          # arXiv ID
python3 -m textrans ./mysource --no-bilingual           # 本地源码目录
python3 -m textrans ./mysource --debug-mask             # 只导出掩码可视化 HTML
```

### Web(前后端)
```bash
# 终端 1:后端
python3 -m uvicorn textrans_api.main:app --port 8000
# 终端 2:前端(已代理 /api /ws 到 8000)
cd dochero-ai && npm run dev
# 打开 http://localhost:3000
```

### Docker(推荐,一键部署到服务器)

无需在机器上装 TeXLive / 中文字体 / Node —— 全打包在容器里。

```bash
cp .env.example .env        # 填入 KIMI_API_KEY(留空则用内置默认 key)
docker compose up -d --build
# 首次构建含完整 TeXLive,约 10-20 分钟;之后秒起
# 打开 http://localhost/         (nginx 单一入口,默认 80 端口)
```

架构:`nginx`(唯一对外入口)→ `/` 转前端、`/api` `/ws` 转后端。翻译产物持久化在宿主 `./data/`,重启不丢、缓存续用。

服务器部署要点:
- 换端口:改 `docker-compose.yml` 里 nginx 的 `ports`(如 `"8080:80"`)。
- 上 HTTPS:在 nginx 前再挂一层带证书的网关,或改 `nginx.conf` 加 443。
- 产物备份:`./data/` 目录即全部翻译结果与缓存。
- 停止:`docker compose down`;看日志:`docker compose logs -f backend`。

## API

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/api/tasks` | 提交任务(`{arxiv_url, make_bilingual, provider}`) |
| POST | `/api/tasks/upload` | 上传 `.zip`/`.tar.gz` 源码 |
| GET | `/api/tasks/{id}` | 查询状态 |
| GET | `/api/tasks/{id}/download/{translated\|bilingual}` | 下载 PDF |
| WS | `/ws/{id}` | 实时进度流 |

API 文档:后端启动后访问 `/docs`。

## 许可证说明

本项目 `textrans/`、`textrans_api/`、`dochero-ai/` 为原创(MIT)。翻译内核的**算法思路**(掩码保护 / 链表合并 / 编译日志回退)受 [gpt_academic](https://github.com/binary-husky/gpt_academic)(GPL v3)启发,但为 **clean-room 重写**,未复制其任何代码。`gpt_academic/` 目录仅作本地参考,不随本产品分发。
