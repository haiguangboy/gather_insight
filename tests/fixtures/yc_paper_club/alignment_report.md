# Alignment / Fixture Report

## 当前状态

- uListen 原始稿：已导入。
- uListen 章节：已解析。
- uListen 说话人：已解析。
- uListen 时间戳：已解析。
- UseTranscribe 完整 Markdown：本测试包中尚未导入。
- 可读正文层：使用确定性断词恢复生成，仅供 Codex 流程测试。

## 统计

- 章节数：7
- 发言片段数：115
- 说话人数：6
- 自动双源时间对齐：待加入 `source_usetranscribe_raw.md` 后执行。
- `alignment_confidence`：当前全部为 `null`，不得伪造。

## 必须测试的异常

1. uListen provider ID 与 YouTube video ID 不一致。
2. uListen 文本复制后英文单词粘连。
3. 专有名词可能被通用断词器错误拆分。
4. 第二源和 uListen 时间戳可能存在 1–3 秒偏差。
5. 两源对数字、模型名或论文名识别不一致时必须进入 review。

## 生产验收

- 导入 UseTranscribe Markdown 后，正常断词正文覆盖率应超过 95%。
- 章节保留率 100%。
- 说话人保留率 100%。
- 每个片段能跳回 YouTube。
- 低置信度片段全部进入 review。
- 不得把 fixture 文本当作最终逐字证据。
