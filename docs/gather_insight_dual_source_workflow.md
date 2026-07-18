# GatherInsight：uListen + UseTranscribe 双源采集、融合与测试流程

> 用途：交给 Codex 实现第一版 `dual_source_transcript_fuser`。  
> 样本：YC Paper Club，YouTube video ID `wE1ZgJdt4uM`。  
> 原则：人工选择与复制，程序完成解析、对齐、异常报告和证据生成。

---

## 1. 为什么使用双源

### uListen 负责结构

人工从 YouTube 页面里的 uListen `Every Spoken Word` 面板复制全文。

uListen 提供：

- 章节标题；
- 章节起止时间；
- 真实说话人姓名；
- 说话人切换；
- 发言时间戳；
- 相关论文链接。

主要缺陷：

- 浏览器复制后英文单词可能粘连；
- uListen 页面后缀不一定等于 YouTube video ID。

### UseTranscribe 负责可读正文

从 UseTranscribe 页面点击 `.md` 下载，原样保存。

UseTranscribe 提供：

- 正常英文空格；
- 可读标点和断句；
- 时间戳；
- 连续完整正文。

主要缺陷：

- 可能没有真实说话人姓名；
- 分段粒度和 uListen 不同；
- 时间可能有少量偏差。

最终原则：

```text
uListen = 结构权威源
UseTranscribe = 正文权威源
YouTube 原视频 = 冲突裁决源
```

---

## 2. 人工采集步骤

### 2.1 保存 uListen

1. 打开目标 YouTube 视频。
2. 确认 uListen 插件已显示完整内容。
3. 打开 `Every Spoken Word`。
4. 全选并复制完整面板内容。
5. 保存为：

```text
source_ulisten_raw.md
```

不得手工清理空格、改写姓名或删除时间戳。

### 2.2 保存 UseTranscribe

1. 打开对应 UseTranscribe 页面。
2. 点击页面上的 `.md` 下载。
3. 保存为：

```text
source_usetranscribe_raw.md
```

不得把摘要替代 Transcript，也不得只复制 Section Insights。

### 2.3 建立输入目录

```text
data/media/yt_wE1ZgJdt4uM/
├── source_ulisten_raw.md
├── source_usetranscribe_raw.md
└── manifest.yaml
```

---

## 3. 主键规则

唯一主键来自 YouTube：

```text
media_id = yt_{youtube_video_id}
```

本样本：

```text
media_id = yt_wE1ZgJdt4uM
```

uListen URL 中的 `gSNFJbgoaHI` 只保存为：

```yaml
provider_ids:
  ulisten: gSNFJbgoaHI
```

不得用它生成 `media_id`。

---

## 4. 解析 uListen

### 4.1 章节范围

匹配：

```regex
^(\d{1,2}:\d{2}(?::\d{2})?)\s*-\s*(\d{1,2}:\d{2}(?::\d{2})?)$
```

### 4.2 章节标题

匹配：

```regex
^####\s+(.+)$
```

标题末尾可能带论文链接，应拆为：

```json
{
  "chapter_title": "Guangyao (Stannis) Zhou — Diffusion-MPC",
  "reference_url": "https://arxiv.org/abs/2410.05364"
}
```

### 4.3 说话人与时间戳

从行尾反向匹配时间：

```regex
^(.+?)(\d{1,2}:\d{2}(?::\d{2})?)$
```

剩余前缀作为 speaker。

### 4.4 发言结束时间

- 同章节内：下一发言块的开始时间；
- 章节最后一段：章节结束时间；
- 不得根据文本长度猜测。

---

## 5. 解析 UseTranscribe

至少输出：

```json
{
  "start_seconds": 348,
  "end_seconds": 372,
  "text": "So the claim I'm going to make..."
}
```

若来源只有每段开始时间：

- `end_seconds` 取下一段开始时间；
- 最后一段取视频总时长；
- 不制造 speaker 姓名。

---

## 6. 融合算法

对每个 uListen 发言块：

1. 取时间窗口 `[start_seconds, end_seconds)`；
2. 在第二源中查找重叠字幕；
3. 默认允许时间偏差 `±3 秒`；
4. 拼接重叠的第二源正文；
5. 比较 uListen 原文去空格版本与第二源正文去空格版本；
6. 同时计算时间重叠和文本相似度；
7. 达标后：
   - 章节、speaker、边界使用 uListen；
   - 正文使用 UseTranscribe；
8. 不达标则保留两份文本并进入 review。

建议评分：

```text
alignment_score =
    0.55 × normalized_text_similarity
  + 0.35 × time_overlap_score
  + 0.10 × chapter_consistency
```

建议阈值：

```text
>= 0.85  自动接受
0.65–0.85  保留并标记复核
< 0.65  不融合，进入 review
```

---

## 7. 标准输出

```json
{
  "segment_id": "yt_wE1ZgJdt4uM.seg_0017",
  "speaker": "Tanishq Kumar",
  "chapter": "Speculative Speculative Decoding",
  "start_seconds": 348,
  "end_seconds": 398,
  "text": "So the claim I'm going to make...",
  "text_ulisten_raw": "SotheclaimI'mgonnamake...",
  "structure_source": "ulisten_manual_browser_copy",
  "text_source": "usetranscribe_manual_export",
  "alignment_method": "timestamp_plus_normalized_text",
  "alignment_confidence": 0.97,
  "needs_review": false
}
```

---

## 8. 冲突处理

### 直接采用第二源

- 只有空格不同；
- 常规标点不同；
- `uh / um` 等填充词缺失。

### 必须进入 review

- 数字不同；
- 模型名不同；
- 人名不同；
- 论文标题不同；
- 否定词不同；
- 时间表和概率词不同；
- 关键结论只存在于一源；
- 相似度低但时间重合。

原视频是最终裁决源。

---

## 9. 文件产物

```text
source_ulisten_raw.md
source_usetranscribe_raw.md
transcript_fused.jsonl
transcript_fused.md
alignment_report.md
review_queue.md
```

原始文件永久保留，不覆盖。

---

## 10. Codex 第一阶段任务

1. 实现 uListen Markdown parser；
2. 实现 UseTranscribe Markdown parser；
3. 实现时间戳统一；
4. 实现双源对齐；
5. 实现相似度评分；
6. 实现冲突报告；
7. 实现 JSONL 和 Markdown 导出；
8. 使用本测试包做回归测试。

禁止：

- 下载音频和视频；
- 引入 Whisper；
- 建立数据库；
- 自动抓取 uListen 内部 API；
- 未审核就生成正式知识卡。

---

## 11. 测试与验收

### 单元测试

- 两位数分钟和一小时以上时间戳；
- 带括号的 speaker；
- 章节末尾论文 URL；
- 多 speaker 连续切换；
- 空正文；
- 重复时间戳；
- provider ID 与 YouTube ID 不一致。

### 集成测试

输入本目录两份 raw 文件，输出融合文件和报告。

### 验收指标

- 章节保留率：100%；
- speaker 保留率：100%；
- YouTube 跳转链接成功率：100%；
- 正常断词正文覆盖率：>95%；
- 低置信度片段进入 review：100%；
- 数字和专有名词冲突不静默覆盖；
- 重复运行不生成重复 ID；
- 没有 UseTranscribe 文件时明确降级，不伪造双源置信度。

---

## 12. 当前测试包说明

本测试包中的 `transcript_fused_fixture.*` 是预备夹具：

- uListen 结构是真实导入的；
- 可读正文是自动断词恢复层；
- `alignment_confidence` 全部为 `null`；
- 目的是让 Codex先开发和测试数据结构、解析器和导出器；
- 加入真实 `source_usetranscribe_raw.md` 后，必须重新生成正式融合结果。
