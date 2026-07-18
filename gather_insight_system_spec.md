# GatherInsight：前沿信号、洞见与判断追踪系统工程规格

> **仓库名**：`gather_insight`  
> **项目名**：GatherInsight  
> **中文定位**：前沿信号、洞见与判断追踪系统  
> **英文副标题**：Frontier Signal & Judgment System  
> **文档用途**：交给 Codex，作为分阶段开发、测试、验收和长期维护的实施依据  
> **版本**：v0.1  
> **日期**：2026-07-18  
> **关联项目**：`haiguangboy/read_papers`

---

## 0. 项目命名

### 0.1 推荐名称

保留仓库名：

```text
gather_insight
```

正式产品名：

```text
GatherInsight
```

完整定位：

> **GatherInsight：从前沿人物、机构和长期访谈中提取证据，追踪观点变化，发现趋势、瓶颈与早期非共识，并接入可验证、可修正的长期判断账本。**

这个名称保留了两个关键动作：

- `Gather`：收集和整理分散在视频、播客、访谈、演讲、官方文字稿中的信号；
- `Insight`：不是保存全部内容，而是提炼能改变判断、行动和长期世界模型的信息。

需要强调：项目的真正价值不只是 gather，而是：

```text
gather
→ verify
→ connect
→ judge
→ track
→ settle
```

未来如需更强调“判断账本”，可稳定使用副标题：

```text
GatherInsight — Frontier Signal & Judgment System
```

MVP 阶段不再继续改名。

---

## 1. 一句话定义

GatherInsight 不是播客摘要器、YouTube 字幕下载器或名人金句收集器，而是：

> **从硅谷和全球科技领域关键人物、公司与投资机构的公开视频、播客、访谈、演讲和官方文字稿中，持续提取可追溯证据，形成候选主张、预测、分歧和二阶洞见，并把它们接入 `read_papers` 的主题判断、后验更新和长期结算体系。**

系统最终追踪的不是“内容数量”，而是：

- 能力发生了什么变化；
- 旧瓶颈是否被解除；
- 新瓶颈转移到了哪里；
- 关键人物的时间表是否提前或推迟；
- 同一人物或机构的立场是否改变；
- 早期非共识是否开始形成共识；
- 资本、人才、算力和组织正在流向哪里；
- 哪些预测正在被现实印证、削弱或推翻；
- 哪些判断框架经受住了时间检验。

---

## 2. 背景与核心价值判断

生成式 AI 正在大幅降低以下内容的生产成本：

- 文字；
- 图片；
- 视频；
- 代码；
- 摘要；
- 翻译；
- 普通知识整理；
- 普通信息检索。

供给爆发后，人的以下资源没有同步增加：

- 时间；
- 注意力；
- 理解复杂问题的能力；
- 判断重要性的能力；
- 审核真假与边界的能力；
- 承担决策后果的能力；
- 长期建立信任的能力。

价值因此向下游迁移：

```text
内容生成
→ 内容筛选
→ 来源审核
→ 重要性判断
→ 跨来源关联
→ 趋势推断
→ 决策
→ 承担责任
→ 长期信任
```

但“摘要和筛选”本身也会快速商品化。因此，GatherInsight 不应把壁垒定义为“比别人总结得更快”，而应定义为：

1. 有明确领域模型的筛选；
2. 证据和判断严格分离；
3. 长期纵向跟踪同一人物、机构和主题；
4. 保存冲突观点，而不是强行合并；
5. 对预测设置时间窗和证伪条件；
6. 定期结算并修正错误；
7. 积累可供未来核验的判断历史；
8. 将正确和错误共同转化为判断能力的训练数据。

项目的长期使命是：

> **持续更新世界模型，尽早识别新的价值卡点、技术路线变化和产业转折点。**

---

## 3. 与 `read_papers` 的关系

### 3.1 不建设第二套判断系统

`read_papers` 已经具备：

- 论文证据抽取；
- evidence-bound cards；
- `fact / claim / boundary` 卡片；
- Stage B 候选生成；
- Stage C 人工审核；
- Stage D 发布内容生成；
- 主题级 judgment card；
- `lifecycle` 生命周期；
- `prior_confidence / probability`；
- `falsification` 证伪条件；
- `review_due / settle_date`；
- `posterior_log` 后验更新；
- `LEDGER.md`；
- 预测复核与双月结算；
- 网站、小红书、邮件等输出适配器；
- GitHub 作为纯文本知识唯一真相源。

GatherInsight 只新增一种上游证据输入，不复制上述系统。

```text
Stage A-Paper
PDF / arXiv / GitHub / Project Page
→ GROBID
→ paper evidence

Stage A-Media
YouTube / 官方 Transcript / uListen / UseTranscribe
→ media transcript normalization
→ media evidence
```

两类证据之后统一进入：

```text
evidence
→ Stage B candidate cards
→ Stage C human review
→ theme/entity relations
→ judgment posterior update
→ settlement
→ publishing adapters
```

### 3.2 两种情报的差异

| 类型 | 主要回答 |
|---|---|
| 论文证据 | 技术能力是否被实验验证，方法是什么，边界在哪里 |
| 访谈证据 | 关键人物如何判断未来，组织和资本正在押注什么 |
| 公司行动 | 真实资源、产品、招聘和商业模式发生了什么 |
| 工程反馈 | 真实部署中哪个环节成为瓶颈 |
| 市场反馈 | 客户是否付费，需求是否存在，规模化是否成立 |

GatherInsight 的独特价值是把“人物和机构的认知信号”接入已有技术判断系统。

---

## 4. 项目使命

### 4.1 主要使命

持续追踪以下对象。

#### 关键人物

- Elon Musk；
- Dario Amodei；
- Sam Altman；
- Naval Ravikant；
- Demis Hassabis；
- Jensen Huang；
- Marc Andreessen；
- Dwarkesh Patel 采访对象；
- YC 合伙人、创始人与重要创业者；
- AI、机器人、具身智能、软件工程和未来经济领域的关键研究者与投资人。

#### 关键机构

- OpenAI；
- Anthropic；
- Google DeepMind；
- xAI；
- Tesla；
- NVIDIA；
- Y Combinator；
- a16z；
- Sequoia；
- 其他对 AI、机器人和产业趋势有长期影响的机构。

#### 关键问题

- AI 能力与时间表；
- Agent 与软件工程；
- AI 对公司组织的影响；
- 编码加速后的瓶颈迁移；
- 数据、算力、能源与物理世界；
- 具身智能和机器人；
- 通用模型与垂直应用；
- 资本、商业模式和竞争结构；
- 就业、教育和社会影响；
- 判断、品味、责任和信任；
- 技术路线的早期非共识；
- 产业拐点与价值迁移。

### 4.2 主要产出

系统最终应形成四类资产：

1. **原始媒体证据**：带来源、说话人、时间戳和上下文；
2. **审核后的知识卡片**：事实、主张、边界、预测；
3. **长期主题和人物档案**：观点变化、冲突关系、共识演化；
4. **发布内容**：网站文章、小红书文案、简报和机器可读文件。

---

## 5. MVP 非目标

MVP 阶段明确不做：

1. 不长期保存视频；
2. 不长期保存音频；
3. 不默认部署 Whisper；
4. 不默认做 speaker diarization；
5. 不建立声纹库；
6. 不逐句标注三小时访谈中的全部说话人；
7. 不建设向量数据库；
8. 不建设复杂 SQLite 知识库；
9. 不使用 Git LFS；
10. 不自动抓取 X；
11. 不自动化登录或浏览 X、小红书、微信公众号；
12. 不自动发布小红书；
13. 不自动把任何摘要写入正式知识库；
14. 不依赖付费字幕插件；
15. 不为少数异常视频提前设计重型兜底系统；
16. 不把全部视频都处理成文章；
17. 不把第三方编辑文章当作原始事实源；
18. 不以“处理数量”作为核心成功指标。

原则：

> **低成本优先，现有第三方文字源优先，人工闸门优先，真实瓶颈出现后再扩展。**

---

## 6. 数据来源与优先级

### 6.1 来源角色必须区分

不同来源承担不同职责，不应混成一个“字幕质量排名”。

| 来源 | 主要职责 |
|---|---|
| YouTube 原视频 | 最终证据、统一时间轴、人工核验 |
| 官方 Transcript | 最高质量文本、说话人和结构 |
| uListen | 高质量说话人、时间戳、章节、重点频道预处理 |
| UseTranscribe | 完整时间戳文字覆盖 |
| YT Transcript Exporter | 免费浏览器侧字幕导出兜底 |
| WebSearchAPI 等文章 | 编辑分析、重点筛选、二阶观点参考 |
| X / 社交媒体 | 人工发现的稀疏高价值外部表达，不自动采集 |

### 6.2 自动处理优先级

对一个新 YouTube 视频，按以下顺序检查：

```text
1. 官方人工文字稿
2. uListen
3. UseTranscribe
4. YT Transcript Exporter
5. YouTube 自带字幕的其他免费导出方式
6. 人工放弃或标记为暂不可处理
```

说明：

- 官方人工文字稿包括 `nav.al`、Lex Fridman 官网、公司官方演讲稿等；
- uListen 权重高，因为其覆盖的频道有限但质量高；
- UseTranscribe 提供完整带时间戳文本，但不一定有说话人；
- YT Transcript Exporter 是免费兜底；
- MVP 不因字幕缺失自动进入 Whisper。

### 6.3 分析增强来源

下列来源不作为主文字稿，但可增强洞见：

- 高质量博客文章；
- WebSearchAPI 文章；
- 公司官方博客；
- 嘉宾个人博客；
- 相关论文；
- 用户人工提交的 X 帖子或评论；
- Hacker News、Reddit 等公开讨论。

它们必须标注：

```text
primary_evidence
secondary_evidence
external_analysis
external_expression
system_derived
```

### 6.4 X 的定位

X 不进入自动采集主链。

用户人工发现高价值表达后，可手动加入：

```yaml
type: external_expression
source_url: https://x.com/...
related_media_id: yt_x2VHFgyawPE
content: "5x coding ≠ 5x company."
why_important: "局部编码加速不会等比例转化为公司整体产出。"
```

系统随后做：

```text
外部表达
→ 搜索原视频证据
→ 判断是否为原话
→ 判断是否为合理推论
→ 连接到支持它的 evidence/card
```

X 的主要用途是：

> 作为洞见召回率测试集，而不是自动化数据源。

---

## 7. 输入

### 7.1 MVP 输入形式

MVP 只要求支持：

```text
一个 YouTube URL
```

可选附加输入：

```yaml
priority: high
reason: "Dario 关于软件护城河和瓶颈迁移的访谈"
manual_sources:
  - "https://www.usetranscribe.io/..."
  - "https://websearchapi.ai/..."
external_insights:
  - "5x coding ≠ 5x company."
```

### 7.2 后续输入形式

后续支持：

- 官方 Transcript URL；
- `nav.al` 页面；
- uListen 页面；
- YouTube 播放列表；
- 人物名；
- 频道名；
- 手动提交的外部洞见；
- 已处理视频的复核请求；
- 某个主题的观点更新请求。

---

## 8. 核心数据流

```text
用户提交 YouTube URL
        ↓
规范化 URL，提取 video_id
        ↓
获取 YouTube metadata
        ↓
依次查询：
官方 transcript → uListen → UseTranscribe → YT Transcript Exporter
        ↓
选择主文字稿
        ↓
规范化 transcript
        ↓
生成 media evidence
        ↓
提取 candidate fact / claim / boundary
        ↓
识别 prediction / tension / external expression
        ↓
Stage C 人工审核
        ↓
正式卡片进入 read_papers 知识库
        ↓
连接人物、机构、主题和已有判断
        ↓
更新 posterior_log / lifecycle
        ↓
生成网站文章、小红书文案和机器文件
        ↓
定期复核、冲突分析和结算
```

---

## 9. 系统层级

### 9.1 Source Layer

负责：

- URL 规范化；
- video_id 识别；
- metadata 获取；
- 来源可用性检测；
- 主文字源选择；
- 原始文字保存；
- 来源质量标记。

不做判断。

### 9.2 Evidence Layer

负责把文字稿转换为可引用证据单元：

- 说话人；
- 开始时间；
- 结束时间；
- 章节；
- 原文；
- 简短摘要；
- 来源类型；
- 归属置信度；
- 可点击 YouTube 时间链接。

不直接生成正式判断。

### 9.3 Candidate Card Layer

从 evidence 生成候选：

- `fact`；
- `claim`；
- `boundary`；
- prediction 语义；
- 候选冲突；
- 候选二阶洞见。

所有输出默认 `pending`。

### 9.4 Human Review Layer

人工完成：

- 接受；
- 修改；
- 丢弃；
- 合并重复；
- 判断说话人；
- 判断是否属于原话；
- 判断是否为系统推导；
- 判断重要性；
- 关联主题；
- 设置证伪条件；
- 设置复核时间。

### 9.5 Longitudinal Intelligence Layer

负责：

- 人物观点时间线；
- 机构立场变化；
- 同一主题多源证据；
- 冲突观点；
- 共识形成；
- 早期非共识；
- 后验更新；
- 生命周期；
- 预测结算。

### 9.6 Publishing Layer

负责生成：

- 网站文章；
- 小红书文案；
- Agent/LLM 可读摘要；
- 周度判断；
- 双月结算材料。

发布必须基于 Stage C 已审核资产。

---

## 10. 存储设计

### 10.1 总原则

本项目是纯文本优先的低成本系统。

```text
GitHub
= 代码 + 配置 + 原始文字 + evidence + cards + judgments + 发布稿

Acer
= Git 工作区 + 临时下载 + 临时处理文件

不保存
= 音频 + 视频 + 模型 + Whisper 大文件
```

### 10.2 GitHub 保存

保存：

- `.md`；
- `.yaml`；
- `.json`；
- `.jsonl`；
- `.py`；
- 测试 fixtures；
- prompts；
- schemas；
- processing reports。

不保存：

- `.mp3`；
- `.m4a`；
- `.wav`；
- `.mp4`；
- 模型权重；
- 浏览器缓存；
- 临时文件；
- 私密令牌；
- `.env`。

### 10.3 是否需要 R2

MVP 不要求 R2。

未来仅在以下场景使用：

- 网站公开静态资源；
- 公开 brief；
- 少量封面图；
- 与现有 `read_papers` 发布体系保持一致。

媒体原始音视频不进入 R2。

### 10.4 数据库策略

MVP 不建设数据库。

使用：

- JSONL；
- Markdown；
- YAML；
- `ripgrep`；
- GitHub 搜索；
- Git 历史。

当正式内容达到数百或上千条、跨主题查询出现真实瓶颈后，再从 JSONL 构建派生 SQLite。

---

## 11. 推荐仓库结构

建议 GatherInsight 独立仓库开发，稳定后与 `read_papers` 通过明确契约集成。

```text
gather_insight/
├── README.md
├── docs/
│   ├── SYSTEM_SPEC.md
│   ├── DATA_CONTRACT.md
│   ├── SOURCE_POLICY.md
│   └── TEST_PLAN.md
│
├── config/
│   ├── sources.yaml
│   ├── channels.yaml
│   ├── people.yaml
│   ├── topics.yaml
│   └── scoring.yaml
│
├── schemas/
│   ├── media_manifest.schema.json
│   ├── media_evidence.schema.json
│   ├── external_expression.schema.json
│   └── export_bundle.schema.json
│
├── prompts/
│   ├── normalize_transcript.md
│   ├── extract_candidates.md
│   ├── derive_insights.md
│   ├── detect_conflicts.md
│   └── generate_publish_drafts.md
│
├── inbox/
│   ├── videos.yaml
│   └── external_insights.yaml
│
├── data/
│   └── media/
│       └── yt_x2VHFgyawPE/
│           ├── manifest.yaml
│           ├── source.md
│           ├── evidence.jsonl
│           ├── candidates.jsonl
│           ├── review.md
│           ├── accepted_cards.jsonl
│           ├── insight_note.md
│           └── publish/
│               ├── website.md
│               └── xiaohongshu.md
│
├── pipeline/
│   ├── ingest.py
│   ├── source_resolver.py
│   ├── transcript_normalizer.py
│   ├── evidence_builder.py
│   ├── candidate_extractor.py
│   ├── exporter.py
│   └── validators.py
│
├── adapters/
│   ├── youtube.py
│   ├── official_transcript.py
│   ├── ulisten.py
│   ├── usetranscribe.py
│   └── manual_markdown.py
│
├── integrations/
│   └── read_papers_export.py
│
├── tests/
│   ├── fixtures/
│   ├── unit/
│   ├── integration/
│   └── golden/
│
├── tmp/
└── .gitignore
```

### 11.1 与 `read_papers` 的边界

GatherInsight 负责：

```text
media URL
→ transcript
→ media evidence
→ candidate bundle
```

`read_papers` 负责：

```text
candidate cards
→ Stage C
→ cards_stage_c
→ themes
→ judgments
→ LEDGER
→ settlement
→ publishing
```

MVP 初期可在 GatherInsight 内生成预览稿，但正式长期判断仍以 `read_papers` 为真相源。

---

## 12. ID 与主键规则

### 12.1 Media ID

YouTube：

```text
media_id = yt_{video_id}
```

示例：

```text
yt_x2VHFgyawPE
```

官方网页：

```text
media_id = web_{domain}_{slug}_{YYYY_MM}
```

示例：

```text
web_nav_al_industrial_2026_07
```

### 12.2 Evidence ID

```text
{media_id}.ev_{NNNN}
```

示例：

```text
yt_x2VHFgyawPE.ev_0017
```

### 12.3 Candidate Card ID

```text
{media_id}.candidate_{NNN}
```

### 12.4 正式卡片 ID

正式卡片进入 `read_papers` 后，服从其现有 card ID 和 judgment ID 规则，不由 GatherInsight 擅自改变。

---

## 13. 数据格式

### 13.1 `manifest.yaml`

```yaml
schema_version: media_manifest_v1
media_id: yt_x2VHFgyawPE
media_type: youtube_video
title: "Inside the Mind of Anthropic CEO Dario Amodei"
source_url: "https://www.youtube.com/watch?v=x2VHFgyawPE"
video_id: x2VHFgyawPE
channel: Bloomberg Originals
published_at: null
duration_seconds: null

participants:
  - name: Dario Amodei
    role: guest
  - name: Emily Chang
    role: host

topics:
  - ai
  - software_engineering
  - organization
  - jobs
  - ai_safety

source_resolution:
  primary_provider: usetranscribe
  primary_url: "https://www.usetranscribe.io/yt/x2VHFgyawPE/..."
  checked:
    official_transcript: false
    ulisten: false
    usetranscribe: true
    youtube_export: true

processing:
  status: reviewed
  transcript_language: en
  speaker_mode: host_guest
  created_at: "2026-07-18"
  updated_at: "2026-07-18"
```

### 13.2 `evidence.jsonl`

每行一个可引用证据单元：

```json
{
  "evidence_id": "yt_x2VHFgyawPE.ev_0017",
  "media_id": "yt_x2VHFgyawPE",
  "source_type": "third_party_transcript",
  "provider": "usetranscribe",
  "speaker": "Dario Amodei",
  "speaker_confidence": 0.86,
  "attribution_method": "qa_structure",
  "start_seconds": 908,
  "end_seconds": 951,
  "timestamp": "15:08",
  "youtube_url": "https://www.youtube.com/watch?v=x2VHFgyawPE&t=908s",
  "section": "Software moats",
  "quote": "Short original excerpt.",
  "summary_zh": "复杂软件本身形成的护城河会下降，但客户关系和领域知识仍会存在。",
  "relevance": "high",
  "needs_review": false
}
```

规则：

- `quote` 必须短；
- 不在 evidence 中塞入整段十分钟正文；
- `speaker_confidence` 必须存在；
- 不确定说话人可为 `unknown`；
- 时间戳必须能跳回原视频；
- 第三方文字源不能冒充官方来源。

### 13.3 `candidates.jsonl`

```json
{
  "card_id": "yt_x2VHFgyawPE.candidate_001",
  "type": "claim",
  "title": "软件实现能力商品化后，护城河向其他约束迁移",
  "content": "快速编写复杂软件形成的护城河会下降，客户关系、领域知识和新的限制因素相对升值。",
  "speaker": "Dario Amodei",
  "source": "media_interview",
  "evidence": [
    "yt_x2VHFgyawPE.ev_0017",
    "yt_x2VHFgyawPE.ev_0018"
  ],
  "confidence": "high",
  "stage_c_decision": "pending",
  "candidate_topics": [
    "ai_software_company_bottlenecks"
  ],
  "prediction_semantics": false,
  "falsification": "",
  "connections": []
}
```

规则：

- 默认 `pending`；
- 不自动写入正式知识库；
- `evidence` 不得为空；
- 由系统推导的内容必须 `source: system_derived`；
- 受访者原话和系统推导不可混淆。

### 13.4 外部表达

```json
{
  "expression_id": "ext_x_001",
  "type": "external_expression",
  "content": "5x coding ≠ 5x company.",
  "source_url": "manual_submission",
  "related_media_id": "yt_x2VHFgyawPE",
  "is_verbatim_speaker_quote": false,
  "represents": "AI解除编码瓶颈后，系统约束会向其他环节迁移。",
  "supporting_evidence": [
    "yt_x2VHFgyawPE.ev_0017",
    "yt_x2VHFgyawPE.ev_0024"
  ],
  "status": "reviewed"
}
```

---

## 14. 文字稿规范化

### 14.1 原始文字保留原则

系统应同时保留：

- 原始英文；
- 时间戳；
- 章节；
- 来源；
- 必要的说话人信息。

不应：

- 直接用中文改写替代原文；
- 删除 `may / could / perhaps / likely` 等不确定词；
- 把主持人的假设改写成嘉宾结论；
- 把外部文章的概括写成受访者原话；
- 为追求流畅而丢失限制条件。

### 14.2 分块

建议语义块：

```text
15–60 秒
```

优先按以下边界：

1. 官方章节；
2. 问题与回答；
3. 主题变化；
4. 固定时间窗口。

不追求逐条字幕原样保存，也不把十分钟内容压成一个 evidence。

### 14.3 说话人模式

```yaml
single_speaker:
  policy: 默认归属主讲人

host_guest:
  policy: 使用问答结构推断，重要卡人工复核

multi_speaker:
  policy: 保守归属；无法确认时使用 unknown
```

归属等级：

```text
A：官方文字稿明确标注
B：uListen 等高质量来源明确标注
C：问答结构推断
D：上下文推断
U：未知
```

正式人物档案优先接受 A/B；C 需较高置信度或人工核验。

---

## 15. 洞见模型

系统必须区分三种内容。

### 15.1 Explicit Claim

人物明确表达的主张。

```text
Dario：软件实现形成的护城河会下降。
```

### 15.2 Derived Insight

系统根据多条 evidence 推导出的二阶洞见。

```text
编码效率提高不会使公司整体效率等比例提高，因为约束会迁移。
```

必须保存：

```text
derived_from
reasoning
confidence
```

### 15.3 External Expression

外部作者对复杂观点的高密度压缩。

```text
5x coding ≠ 5x company.
```

必须标记：

```text
不是受访者逐字原话
```

三者不能混为一类，否则会产生最危险的“聪明幻觉”：系统得出了好观点，却错误归因给某个权威人物。

---

## 16. 主题聚合

### 16.1 不按视频孤立存储判断

单个视频只是证据包，不是最终判断单位。

判断应挂到 `read_papers/specs/themes.yaml` 中的主题。

示例主题：

```yaml
theme_id: ai_implementation_to_judgment
name: AI 解除实现瓶颈后，价值向判断、交付和责任迁移
definition: >
  跟踪代码、内容和一般执行能力商品化后，
  企业与个人的新约束是否转移到问题定义、验证、
  客户关系、组织协调、责任和长期信任。
status: active
```

### 16.2 主题证据可跨来源

```text
论文
+ Dario 访谈
+ Naval 访谈
+ Sam Altman 博客
+ 公司招聘变化
+ 用户真实机器人交付经验
```

共同支持或挑战同一 judgment。

### 16.3 主题关系

使用已有关系词汇，优先高层展示：

```text
supports
contradicts
qualifies
```

内部可保留：

```text
extends
refines
duplicates
theme
```

---

## 17. 人物与机构纵向追踪

### 17.1 人物档案

每个重点人物至少追踪：

```yaml
person:
  name:
  organizations:
  roles:
  tracked_topics:
  first_seen:
  last_updated:
```

观点记录：

```text
日期
来源
主题
原始主张
时间窗
置信度
与过去立场关系
后续现实结果
```

### 17.2 观点变化类型

```text
consistent：延续原判断
strengthened：语气或时间表更激进
weakened：降低概率或延后时间
reversed：明确反转
qualified：增加限制条件
silent_shift：不再提及过去核心主张
```

### 17.3 机构档案

机构追踪：

- 公司使命和叙事；
- 关键产品；
- 公开路线；
- 招聘方向；
- 商业模式；
- 安全和治理立场；
- 资本开支；
- 与创始人口头观点是否一致。

---

## 18. 冲突观点

系统不得为了生成“统一总结”而消灭冲突。

### 18.1 冲突记录

```json
{
  "conflict_id": "conflict_001",
  "theme": "ai_job_displacement_timeline",
  "position_a": {
    "speaker": "Dario Amodei",
    "statement": "初级白领工作可能很快受到重大冲击。",
    "evidence": ["..."]
  },
  "position_b": {
    "speaker": "Other",
    "statement": "组织吸收速度会使影响显著延后。",
    "evidence": ["..."]
  },
  "conflict_type": "timeline",
  "status": "open",
  "resolution_conditions": "观察 2027–2028 年相关岗位数量和工资变化。"
}
```

### 18.2 冲突类型

- 事实冲突；
- 时间表冲突；
- 因果解释冲突；
- 技术路线冲突；
- 商业模式冲突；
- 价值观冲突；
- 风险偏好冲突。

### 18.3 处理原则

- 保存双方最强版本；
- 不使用弱化后的稻草人；
- 标记各自利益位置；
- 明确什么现实数据可以裁决；
- 允许长期悬而未决。

---

## 19. 输出文件

每个处理完成的视频至少生成：

```text
manifest.yaml
source.md
evidence.jsonl
candidates.jsonl
review.md
insight_note.md
```

通过 Stage C 后可生成：

```text
accepted_cards.jsonl
read_papers_export.jsonl
```

发布层生成：

```text
publish/website.md
publish/xiaohongshu.md
```

### 19.1 `insight_note.md`

建议结构：

```markdown
# 标题

## 一句话判断

## 为什么值得处理

## 核心增量

## 章节时间线

## 关键主张

## 二阶洞见

## 重要预测

## 主要边界

## 冲突与张力

## 与已有主题的关系

## 哪些地方需要核验

## 对技术、产业、职业或投资判断的影响

## 原始来源
```

---

## 20. 发布策略

### 20.1 个人网站

个人网站是 canonical public source。

访谈文章不是逐字稿，也不是普通摘要，应回答：

- 这场访谈真正增加了什么信息；
- 哪个旧判断被增强或削弱；
- 哪个新瓶颈被暴露；
- 哪个时间表发生变化；
- 哪些内容是人物立场，哪些是作者推论；
- 哪些判断未来可以验证。

建议新增内容类型：

```yaml
content_type:
  - paper
  - interview
  - podcast
  - speech
  - official_blog
```

### 20.2 新小红书账号

定位：

> 追踪硅谷关键人物和机构，通过长访谈判断 AI、机器人、创业和经济趋势。

不做海外内容搬运号。

单篇结构：

```text
1. 一句话结论
2. 关键原话
3. 这句话真正意味着什么
4. 它改变了哪个旧判断
5. 对现实行动的影响
6. 原视频和时间戳
```

发布行为人工完成，不使用登录态自动化。

### 20.3 发布纪律

- 只能引用 Stage C 已审核卡；
- 区分原话、转述和系统推导；
- 短引用并给出时间戳；
- 不发布完整第三方文字稿；
- 不为流量夸大概率；
- 错误后公开修正；
- 网站文章更新时保留变更记录。

---

## 21. 长期维护与结算

GatherInsight 不单独建立结算系统，接入 `read_papers` 现有机制。

### 21.1 生命周期

```text
active
corroborated
weakened
refuted
superseded
```

### 21.2 后验更新

新访谈可能：

- 支持已有 judgment；
- 挑战已有 judgment；
- 增加限制条件；
- 缩短或延长时间表；
- 暴露新的观测指标；
- 触发新主题。

写入：

```text
posterior_log
```

### 21.3 定期节律

沿用现有设计：

```text
L1：日常论文/访谈解读，为账本供料
L2：周度主题判断或后验更新
L3：双月公开结算和错误归因
```

### 21.4 复核重点

- 重要人物的时间表；
- 明确数字预测；
- 重大就业和经济预测；
- 技术路线终局；
- 资本和商业模式判断；
- 反复传播但缺乏原始支持的流行表达。

---

## 22. 分阶段开发计划

# Phase 0：基准样本与工具对比

## 目标

先证明“现有免费文字源 + AI + 人工审核”可以稳定产出高价值 evidence 和 cards。

## 固定测试样本

1. Dario Amodei / Bloomberg  
   `https://www.youtube.com/watch?v=x2VHFgyawPE`

2. Naval Industrial Roundtable  
   `https://nav.al/industrial`

3. Lex Fridman 一期有官方 transcript 的访谈；

4. Joe Rogan #2404 Elon Musk；用于长视频、无官方友好文字稿压力测试。

## 测试来源

- uListen；
- UseTranscribe；
- YT Transcript Exporter；
- 官方 transcript；
- WebSearchAPI 编辑文章。

## 产物

```text
tests/golden/<media_id>/
├── source_variants/
├── gold_evidence.jsonl
├── gold_claims.jsonl
├── gold_insights.jsonl
└── evaluation.md
```

## 验收

- 至少为 Dario 视频建立 15–30 条高价值 gold claims；
- 明确标记“5x coding ≠ 5x company”不是 Dario 逐字原话；
- 每条 gold claim 有时间戳证据；
- 能比较不同文字源的洞见召回差异；
- 确定正式来源优先级。

---

# Phase 1：单视频 MVP

## 目标

输入一个 YouTube URL，生成标准媒体证据包。

## 功能

- URL 规范化；
- video_id 提取；
- metadata 文件创建；
- 手动指定主文字源；
- Markdown 文字稿导入；
- transcript 规范化；
- evidence 构建；
- schema 验证；
- 生成 review 文件。

## CLI 建议

```bash
python -m gather_insight ingest \
  --url "https://www.youtube.com/watch?v=x2VHFgyawPE" \
  --transcript-file /path/to/transcript.md \
  --provider usetranscribe
```

## 验收

- 重复运行幂等；
- 生成稳定 media_id；
- 时间戳链接正确；
- evidence ID 不重复；
- 所有 evidence 可追溯到 source；
- 不依赖音频、视频或 Whisper；
- 无数据库依赖。

---

# Phase 2：来源适配器与自动选择

## 目标

自动检测免费高质量文字源。

## 开发顺序

1. `official_transcript`；
2. `uListen`；
3. `UseTranscribe`；
4. `manual_markdown`；
5. YT Transcript Exporter 导出文件导入。

注意：若网页结构不稳定，允许适配器只返回“可用 URL”，由人工下载后导入，不强求自动抓取全文。

## 验收

- 来源失败时可降级；
- 不因单个来源不可用导致整个任务失败；
- manifest 保存所有检查结果；
- 来源类型标记准确；
- 不调用付费 API；
- 不使用登录态自动化。

---

# Phase 3：候选卡与人工审核

## 目标

从 evidence 生成 `fact / claim / boundary` 候选，并接入人工闸门。

## 功能

- candidate extraction；
- prediction semantics；
- derived insight；
- external expression；
- review markdown；
- `pending / accept / drop / edit`；
- schema 质量门；
- evidence orphan 检查。

## 验收

- 默认全部 pending；
- 无 evidence 的卡硬失败；
- 系统推导与人物原话严格区分；
- 人工未接受的卡不能导出到 `read_papers`；
- 说话人不确定时不强行归属；
- 失败报告落盘。

---

# Phase 4：与 `read_papers` 集成

## 目标

将审核后的媒体卡导入现有知识系统。

## 集成契约

GatherInsight 输出：

```text
exports/read_papers/<media_id>.jsonl
```

字段映射：

```text
media_id
→ source namespace

media evidence_id
→ read_papers evidence reference

candidate type
→ fact / claim / boundary

candidate_topics
→ themes.yaml routing suggestions
```

## 验收

- 不破坏现有 paper card schema；
- 媒体证据使用独立 namespace；
- 可被现有 Stage C、relations、LEDGER 使用；
- 现有 CI 能识别孤儿证据；
- 正式判断仍由 `read_papers` 管理。

---

# Phase 5：人物、主题和冲突追踪

## 目标

形成长期纵向情报，而不是视频孤岛。

## 功能

- people registry；
- organization registry；
- stance timeline；
- topic aggregation；
- conflict records；
- same-speaker position change；
- theme support/contradict/qualify；
- weekly diff report。

## 验收

能够回答：

- Dario 对 AI 时间表过去一年是否更激进；
- Naval、Dario 和 Sam 对“判断力升值”有哪些相同与不同；
- 某主题有哪些支持和反对证据；
- 哪些判断目前仍缺乏可结算条件；
- 某人物是否出现立场反转。

---

# Phase 6：发布适配器

## 目标

从已审核资产生成网站和小红书草稿。

## 功能

- website draft；
- xiaohongshu draft；
- 引用和时间戳；
- 公开/私有字段分离；
- 网站 content_type；
- 发布状态。

## 验收

- 不包含完整第三方文字稿；
- 每个关键观点可回到视频；
- 原话、推导和外部表达标记清楚；
- 文案只引用 accepted cards；
- 网站版本可更新并保留判断变化。

---

# Phase 7：低成本发现与周期维护

## 目标

减少人工寻找视频的成本，但保持人作为闸门。

## 可实现范围

- 维护重点频道列表；
- 使用 YouTube 公开 feed 或人工 URL；
- 生成候选短名单；
- 按人物、主题、时长和关键词评分；
- 人工选择后才进入 ingest。

## 不做

- 自动处理所有新视频；
- 自动浏览 X；
- 自动发布社交平台；
- 大规模抓取登录平台。

## 验收

- 候选池有自动清理周期；
- “未选择”不会进入长期知识库；
- 已选视频有持久日志；
- 处理成本可控。

---

## 23. 测试计划

### 23.1 单元测试

必须覆盖：

- YouTube URL 规范化；
- video_id 提取；
- media_id 生成；
- timestamp 解析；
- YouTube 时间链接生成；
- evidence ID 生成；
- JSONL 校验；
- speaker confidence 校验；
- provider 优先级；
- manifest 幂等更新；
- orphan evidence 检查。

### 23.2 集成测试

场景：

1. 官方 transcript；
2. uListen 可用；
3. 只有 UseTranscribe；
4. 只有手动 Markdown；
5. 多人访谈；
6. 超长视频；
7. 没有说话人；
8. 来源网页失效；
9. 同一视频重复 ingest；
10. 一个外部表达关联多个 evidence。

### 23.3 Golden Test

Dario 视频建立人工黄金集。

指标：

```text
Evidence Coverage
Speaker Attribution Precision
High-value Claim Recall
Insight Recall
Insight Precision
Evidence Link Completeness
Hallucination Rate
```

### 23.4 关键质量目标

MVP 目标：

- 正式卡片 evidence 绑定率：100%；
- 时间戳可跳转率：100%；
- 无证据正式卡片：0；
- 外部表达误标成受访者原话：0；
- Stage C 默认接受：0；
- 系统推导未标注：0；
- 关键说话人错误归属：低于 5%，且高价值卡人工复核；
- 同一输入重复运行产生重复 ID：0。

---

## 24. 质量门

CI 至少执行：

```text
1. YAML / JSON / JSONL 语法校验
2. schema 校验
3. ID 唯一性
4. evidence 引用存在性
5. 时间戳合法性
6. source_url 存在性
7. accepted card 必须有 evidence
8. system_derived 必须有 derived_from
9. external_expression 不得标记为 speaker quote
10. pending 卡不得进入正式 export
```

软提示：

- `speaker_confidence < 0.8`；
- 单条 evidence 时间跨度过长；
- quote 过长；
- prediction 无证伪条件；
- 候选卡无法关联主题；
- 同一视频候选卡过多；
- 全文摘要比例过高、洞见比例过低。

---

## 25. 评估标准

系统成功不以“处理多少小时视频”衡量，而以以下指标衡量。

### 25.1 证据质量

- 是否能快速回到原视频；
- 是否保留上下文；
- 是否正确区分说话人；
- 是否保留不确定性。

### 25.2 洞见质量

- 是否发现真正改变判断的信息；
- 是否能跨段落推导瓶颈迁移；
- 是否避免把普通观点包装成洞见；
- 是否区分人物观点和系统推论。

### 25.3 长期价值

- 是否能看到观点变化；
- 是否能连接论文和人物证据；
- 是否能更新已有 judgment；
- 是否能定期结算；
- 是否能公开修正错误；
- 是否形成信任复利。

### 25.4 成本

- 每条视频人工操作时间；
- API 成本；
- LLM Token 成本；
- 失败率；
- 每条正式洞见的平均成本。

---

## 26. 成本控制原则

1. 免费文字源优先；
2. 一个视频只选一个主文字稿；
3. 多版本只用于基准测试；
4. 不下载媒体；
5. 不保存可轻易重新获取的冗余文件；
6. 不默认对全文运行昂贵模型；
7. 先做主题地图，再精处理高价值片段；
8. 人工只核验高价值卡；
9. 被淘汰候选不进入长期库；
10. 真实使用规模出现后再建设数据库。

---

## 27. 安全与令牌

- 不在代码、Markdown、聊天记录或 Git 历史中保存 PAT；
- 使用 GitHub App、`gh auth`、SSH 或环境变量；
- `.env` 必须 gitignore；
- 任何暴露的令牌立即 revoke；
- 不使用主小红书账号参与自动采集；
- 不使用浏览器自动化模拟真人行为；
- 公开发布前检查隐私和第三方版权；
- 不公开完整第三方 transcript。

---

## 28. Codex 开发纪律

Codex 开发时必须遵守：

1. 先阅读本规格和 `read_papers/docs/` 相关文档；
2. 不擅自引入数据库、Whisper、音视频存储；
3. 不实现尚未进入当前 Phase 的功能；
4. 每个 Phase 单独提交；
5. 先写 schema 和 fixtures，再写处理代码；
6. 每个适配器失败必须可降级；
7. 所有失败信息必须落盘；
8. 不静默接受；
9. 不把 LLM 输出直接写入正式知识库；
10. 修改数据格式时同步修改 schema、测试和文档；
11. 保持纯文本、可审计、可 Git diff；
12. 每个重要设计选择在 `docs/DECISIONS.md` 记录；
13. 不覆盖人工修改；
14. 不删除历史判断，只通过 lifecycle 和 superseded 机制演进；
15. 优先形成最短可运行闭环。

---

## 29. MVP Definition of Done

MVP 完成必须同时满足：

1. 输入 Dario YouTube URL；
2. 使用 UseTranscribe 或手动 Markdown 导入文字稿；
3. 生成 manifest；
4. 生成带时间戳 evidence；
5. 生成候选 fact/claim/boundary；
6. 生成人工 review 文件；
7. 人工接受后生成 accepted cards；
8. 导出到 `read_papers` 可识别格式；
9. 将卡片关联到一个已有或新增主题；
10. 生成网站草稿；
11. 生成小红书草稿；
12. CI 验证证据引用；
13. “5x coding ≠ 5x company”被正确标为外部高密度表达，而非 Dario 原话；
14. 全流程不保存音频和视频；
15. 全流程不依赖 Whisper；
16. 重复执行不产生重复数据；
17. 所有步骤有明确日志和失败状态。

---

## 30. 第一轮建议任务拆分

### Task 1：仓库骨架

创建：

```text
docs/
config/
schemas/
prompts/
data/
pipeline/
adapters/
integrations/
tests/
```

### Task 2：数据契约

完成：

- manifest schema；
- evidence schema；
- candidate schema；
- export schema；
- 示例 fixtures。

### Task 3：手动 Markdown ingest

优先支持：

```bash
gather-insight ingest --url ... --transcript-file ...
```

暂不自动抓取网页。

### Task 4：Evidence builder

实现：

- 时间戳解析；
- 语义分块；
- evidence ID；
- YouTube 链接；
- JSONL 输出。

### Task 5：候选卡生成

先允许调用外部 LLM 或生成 prompt bundle，不要求第一版直接集成所有模型 API。

### Task 6：Review gate

实现：

- pending；
- accept；
- drop；
- edit；
- accepted export。

### Task 7：`read_papers` export

输出独立文件，由人工或已有脚本导入。

### Task 8：Dario golden test

完成固定样本的端到端验证。

### Task 9：uListen / UseTranscribe adapter

在手动流程稳定后再开发。

### Task 10：网站和小红书 draft

最后接入发布层。

---

## 31. 最终系统愿景

```text
论文、访谈、播客、演讲、官方博客、公司行动、现实反馈
                         ↓
                  统一证据命名空间
                         ↓
              可审核的事实、主张和边界
                         ↓
             人物、机构、主题和冲突关系
                         ↓
             可证伪的长期 judgment ledger
                         ↓
                后验更新、纠错和结算
                         ↓
          网站、小红书、邮件和 Agent 接口
```

最终核心产品不是字幕、摘要或文章，而是：

> **一个随着新证据持续演进、能够记录冲突、修正错误、发现瓶颈迁移并经受时间检验的前沿科技判断系统。**

---

## 32. 最重要的工程原则

> **先证明一条视频能够稳定地产生高质量、可追溯、可审核并能更新主题判断的知识，再扩大来源和自动化。**

> **任何不能提升洞见质量、证据可靠性、长期追踪能力或降低真实成本的功能，都不应进入当前版本。**
