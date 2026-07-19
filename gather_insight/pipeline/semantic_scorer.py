from __future__ import annotations

import hashlib
import json
import math
import os
import re
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable


class SemanticBackendUnavailable(RuntimeError):
    pass


def l2_normalize(vector: list[float]) -> list[float]:
    norm = math.sqrt(sum(value * value for value in vector)) or 1.0
    return [value / norm for value in vector]


def cosine(left: list[float], right: list[float]) -> float:
    return max(-1.0, min(1.0, sum(a * b for a, b in zip(left, right))))


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


@dataclass
class ScorerStats:
    embedding_api_call_count: int = 0
    embedding_cache_hit_count: int = 0
    embedding_text_count: int = 0
    embedding_seconds: float = 0.0

    def as_dict(self) -> dict[str, int | float]:
        return {
            "embedding_api_call_count": self.embedding_api_call_count,
            "embedding_cache_hit_count": self.embedding_cache_hit_count,
            "embedding_text_count": self.embedding_text_count,
            "embedding_seconds": round(self.embedding_seconds, 3),
        }


class HashCache:
    def __init__(self, path: Path | None):
        self.path = path
        self.values: dict[str, dict[str, Any]] = {}
        if path and path.exists():
            for line in path.read_text(encoding="utf-8").splitlines():
                try:
                    item = json.loads(line)
                    if item.get("key"):
                        self.values[str(item["key"])] = item
                except json.JSONDecodeError:
                    continue

    def get(self, key: str) -> dict[str, Any] | None:
        return self.values.get(key)

    def put(self, key: str, value: dict[str, Any]) -> None:
        self.values[key] = {"key": key, **value}

    def save(self) -> None:
        if not self.path:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = "".join(json.dumps(value, ensure_ascii=False) + "\n" for value in self.values.values())
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        temporary.write_text(payload, encoding="utf-8")
        temporary.replace(self.path)


@dataclass
class SemanticScorer:
    provider: str
    model: str
    normalize: bool
    semantic_unit_version: str
    alignment_text_version: str
    stats: ScorerStats = field(default_factory=ScorerStats)
    degraded: bool = False

    def embed(self, texts: list[str]) -> list[list[float]]:
        raise NotImplementedError

    def similarity(self, left: str, right: str) -> float:
        vectors = self.embed([left, right])
        return round(cosine(vectors[0], vectors[1]), 6)

    def score_pairs(self, pairs: list[tuple[str, str]]) -> list[float]:
        if not pairs:
            return []
        texts = list(dict.fromkeys(text for pair in pairs for text in pair))
        vectors = self.embed(texts)
        by_text = dict(zip(texts, vectors))
        return [round(max(0.0, cosine(by_text[left], by_text[right])), 6) for left, right in pairs]

    def metadata(self) -> dict[str, object]:
        return {
            "semantic_backend": self.provider,
            "embedding_model": self.model,
            "embedding_model_digest": None,
            "embedding_normalize": self.normalize,
            "semantic_alignment_degraded": self.degraded,
            **self.stats.as_dict(),
        }


class OllamaEmbeddingScorer(SemanticScorer):
    def __init__(self, *, base_url: str, model: str, normalize: bool, dim: int, batch_size: int, cache_path: Path | None, semantic_unit_version: str, alignment_text_version: str):
        super().__init__("ollama", model, normalize, semantic_unit_version, alignment_text_version)
        self.base_url = base_url.rstrip("/")
        self.dim = dim
        self.batch_size = batch_size
        self.cache = HashCache(cache_path)
        self.cache_path = cache_path
        self._model_digest: str | None = None
        self._check_model()

    def _check_model(self) -> None:
        try:
            request = urllib.request.Request(self.base_url + "/api/tags")
            with urllib.request.urlopen(request, timeout=10) as response:
                models = json.loads(response.read()).get("models", [])
            match = next((item for item in models if item.get("name") == self.model or item.get("model") == self.model), None)
            if not match:
                raise SemanticBackendUnavailable(f"Ollama embedding model is not installed: {self.model}")
            self._model_digest = match.get("digest")
        except (OSError, urllib.error.URLError, json.JSONDecodeError) as exc:
            raise SemanticBackendUnavailable(f"Ollama embedding backend unavailable: {exc}") from exc

    def _key(self, text: str) -> str:
        config = json.dumps({
            "text_sha256": sha256_text(text),
            "model": self.model,
            "model_digest": self._model_digest,
            "normalize": self.normalize,
            "dim": self.dim,
            "semantic_unit_version": self.semantic_unit_version,
            "alignment_text_version": self.alignment_text_version,
        }, sort_keys=True)
        return sha256_text(config)

    def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        output: list[list[float] | None] = [None] * len(texts)
        pending: list[tuple[int, str, str]] = []
        for index, text in enumerate(texts):
            key = self._key(text)
            cached = self.cache.get(key)
            if cached:
                output[index] = [float(value) for value in cached["vector"]]
                self.stats.embedding_cache_hit_count += 1
            else:
                pending.append((index, text, key))
        self.stats.embedding_text_count += len(texts)
        for offset in range(0, len(pending), self.batch_size):
            batch = pending[offset:offset + self.batch_size]
            body = json.dumps({"model": self.model, "input": [item[1] for item in batch]}).encode("utf-8")
            request = urllib.request.Request(self.base_url + "/api/embed", data=body, headers={"Content-Type": "application/json"})
            started = time.monotonic()
            try:
                with urllib.request.urlopen(request, timeout=180) as response:
                    data = json.loads(response.read())
            except (OSError, urllib.error.URLError, json.JSONDecodeError) as exc:
                raise SemanticBackendUnavailable(f"Ollama /api/embed failed: {exc}") from exc
            vectors = data.get("embeddings")
            if not isinstance(vectors, list) or len(vectors) != len(batch):
                raise SemanticBackendUnavailable("Ollama /api/embed returned an unexpected embedding batch")
            self.stats.embedding_api_call_count += 1
            self.stats.embedding_seconds += time.monotonic() - started
            for (index, _text, key), vector in zip(batch, vectors):
                values = [float(value) for value in vector]
                if self.dim and len(values) != self.dim:
                    raise SemanticBackendUnavailable(f"Ollama embedding dimension mismatch: expected {self.dim}, got {len(values)}")
                if self.normalize:
                    values = l2_normalize(values)
                output[index] = values
                self.cache.put(key, {"vector": values, "model": self.model, "model_digest": self._model_digest})
            self.cache.save()
        return [vector or [] for vector in output]

    def metadata(self) -> dict[str, object]:
        value = super().metadata()
        value.update({"embedding_model_digest": self._model_digest, "embedding_base_url": self.base_url, "embedding_cache_path": str(self.cache_path) if self.cache_path else None})
        return value


class DeterministicTestScorer(SemanticScorer):
    def __init__(self, *, semantic_unit_version: str, alignment_text_version: str):
        super().__init__("deterministic_test_scorer", "fake-v1", True, semantic_unit_version, alignment_text_version)

    def embed(self, texts: list[str]) -> list[list[float]]:
        vectors: list[list[float]] = []
        for text in texts:
            values = [0.0] * 128
            synonyms = {"purchase": "buy", "purchased": "buy", "automobile": "car", "rapid": "fast", "quick": "fast", "decrease": "reduce", "decreased": "reduce", "thanks": "thank", "welcomes": "welcome"}
            tokens = [synonyms.get(token, token) for token in re.findall(r"[a-z0-9]+", text.lower())]
            for token in tokens:
                digest = hashlib.sha256(token.encode("utf-8")).digest()
                index = int.from_bytes(digest[:2], "big") % len(values)
                values[index] += 1.0 if digest[2] % 2 else -1.0
            vectors.append(l2_normalize(values))
        return vectors


class LexicalSemanticScorer(DeterministicTestScorer):
    def __init__(self, *, semantic_unit_version: str, alignment_text_version: str):
        super().__init__(semantic_unit_version=semantic_unit_version, alignment_text_version=alignment_text_version)
        self.provider = "degraded_lexical"
        self.model = "deterministic-lexical-v1"
        self.degraded = True

    def similarity(self, left: str, right: str) -> float:
        from difflib import SequenceMatcher
        normalized_left = re.sub(r"[^a-z0-9]+", "", left.lower())
        normalized_right = re.sub(r"[^a-z0-9]+", "", right.lower())
        if not normalized_left or not normalized_right:
            return 0.0
        return round(SequenceMatcher(None, normalized_left, normalized_right, autojunk=False).ratio(), 6)

    def score_pairs(self, pairs: list[tuple[str, str]]) -> list[float]:
        return [self.similarity(left, right) for left, right in pairs]


def build_scorer(*, backend: str, embedding: dict[str, Any], semantic_unit_version: str, alignment_text_version: str, cache_root: Path | None = None) -> SemanticScorer:
    if backend in {"mock_semantic", "mock"}:
        return DeterministicTestScorer(semantic_unit_version=semantic_unit_version, alignment_text_version=alignment_text_version)
    if backend == "lexical_only":
        return LexicalSemanticScorer(semantic_unit_version=semantic_unit_version, alignment_text_version=alignment_text_version)
    if backend not in {"local_semantic", "hybrid_semantic"}:
        raise ValueError(f"unsupported semantic backend: {backend}")
    cache_path = Path(embedding.get("cache_path") or ".embcache/semantic_alignment.embeddings.jsonl")
    if not cache_path.is_absolute() and cache_root:
        cache_path = cache_root / cache_path
    return OllamaEmbeddingScorer(
        base_url=str(embedding.get("base_url", "http://localhost:11434")),
        model=str(embedding.get("model", "bge-m3:latest")),
        normalize=bool(embedding.get("normalize", True)),
        dim=int(embedding.get("dim", 1024)),
        batch_size=int(embedding.get("batch_size", 64)),
        cache_path=cache_path,
        semantic_unit_version=semantic_unit_version,
        alignment_text_version=alignment_text_version,
    )


@dataclass
class JudgeStats:
    call_count: int = 0
    cache_hit_count: int = 0
    abstain_count: int = 0
    escalation_count: int = 0
    api_seconds: float = 0.0
    prompt_tokens: int = 0
    completion_tokens: int = 0

    def as_dict(self) -> dict[str, int | float]:
        return {
            "judge_call_count": self.call_count,
            "judge_cache_hit_count": self.cache_hit_count,
            "judge_abstain_count": self.abstain_count,
            "judge_escalation_count": self.escalation_count,
            "judge_api_seconds": round(self.api_seconds, 3),
            "judge_prompt_tokens": self.prompt_tokens,
            "judge_completion_tokens": self.completion_tokens,
            "judge_cost_usd": None,
        }


class DeepSeekJudge:
    def __init__(self, *, config: dict[str, Any], cache_path: Path | None):
        llm = config.get("llm", {})
        self.base_url = str(llm.get("deepseek_base_url", "https://api.deepseek.com")).rstrip("/")
        self.flash_model = str(llm.get("deepseek_model", "deepseek-v4-flash"))
        self.pro_model = str(llm.get("escalation_model", "deepseek-v4-pro"))
        self.thinking = bool(llm.get("deepseek_thinking", True))
        self.temperature = float(llm.get("temperature", 0.0))
        self.timeout = int(llm.get("deepseek_timeout", 120))
        self.margin_threshold = float(llm.get("candidate_margin_threshold", 0.08))
        self.key = os.environ.get("DEEPSEEK_API_KEY", "").strip()
        self.cache = HashCache(cache_path)
        self.cache_path = cache_path
        self.stats = JudgeStats()

    @property
    def available(self) -> bool:
        return bool(self.key)

    def _cache_key(self, payload: dict[str, Any], model: str) -> str:
        return sha256_text(json.dumps({"model": model, "thinking": self.thinking, "payload": payload}, sort_keys=True, ensure_ascii=False))

    def _request(self, payload: dict[str, Any], model: str) -> dict[str, Any]:
        system = (
            "You are a constrained transcript boundary judge. Choose only one supplied candidate or abstain. "
            "Never rewrite transcript text. Return strict JSON object with decision, confidence, "
            "boundary_start_unit, boundary_end_unit, speaker_boundary_safe, conflicts, reason."
        )
        body = {
            "model": model,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": json.dumps(payload, ensure_ascii=False)}],
            "temperature": self.temperature,
            "max_tokens": 1200,
            "thinking": {"type": "enabled" if self.thinking else "disabled"},
            "response_format": {"type": "json_object"},
        }
        request = urllib.request.Request(self.base_url + "/chat/completions", data=json.dumps(body).encode("utf-8"), headers={"Content-Type": "application/json", "Authorization": f"Bearer {self.key}"})
        started = time.monotonic()
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                data = json.loads(response.read())
        except (OSError, urllib.error.URLError, json.JSONDecodeError) as exc:
            raise SemanticBackendUnavailable(f"DeepSeek judge request failed: {exc}") from exc
        self.stats.api_seconds += time.monotonic() - started
        usage = data.get("usage", {})
        self.stats.prompt_tokens += int(usage.get("prompt_tokens", 0) or 0)
        self.stats.completion_tokens += int(usage.get("completion_tokens", 0) or 0)
        content = str(data.get("choices", [{}])[0].get("message", {}).get("content", ""))
        start, end = content.find("{"), content.rfind("}")
        if start < 0 or end < start:
            raise ValueError("DeepSeek judge returned no JSON object")
        verdict = json.loads(content[start:end + 1])
        if verdict.get("decision") != "abstain" and not re.match(r"^candidate_[0-9]+$", str(verdict.get("decision", ""))):
            raise ValueError("DeepSeek judge returned an invalid candidate decision")
        return verdict

    def judge(self, payload: dict[str, Any]) -> dict[str, Any] | None:
        if not self.available:
            self.stats.abstain_count += 1
            return None
        model = self.flash_model
        key = self._cache_key(payload, model)
        cached = self.cache.get(key)
        if cached:
            self.stats.cache_hit_count += 1
            verdict = dict(cached["verdict"])
        else:
            self.stats.call_count += 1
            try:
                verdict = self._request(payload, model)
            except (ValueError, SemanticBackendUnavailable):
                verdict = {"decision": "abstain", "confidence": 0.0, "boundary_start_unit": None, "boundary_end_unit": None, "speaker_boundary_safe": False, "conflicts": [], "reason": "flash_invalid_or_unavailable"}
            self.cache.put(key, {"model": model, "verdict": verdict})
        if verdict is None or verdict.get("decision") == "abstain":
            self.stats.abstain_count += 1
            if self.pro_model and self.pro_model != model:
                self.stats.escalation_count += 1
                pro_key = self._cache_key(payload, self.pro_model)
                pro_cached = self.cache.get(pro_key)
                if pro_cached:
                    self.stats.cache_hit_count += 1
                    verdict = dict(pro_cached["verdict"])
                else:
                    self.stats.call_count += 1
                    try:
                        verdict = self._request(payload, self.pro_model)
                    except (ValueError, SemanticBackendUnavailable):
                        verdict = {"decision": "abstain", "confidence": 0.0, "boundary_start_unit": None, "boundary_end_unit": None, "speaker_boundary_safe": False, "conflicts": [], "reason": "pro_invalid_or_unavailable"}
                    self.cache.put(pro_key, {"model": self.pro_model, "verdict": verdict})
        self.cache.save()
        return verdict

    def metadata(self) -> dict[str, object]:
        return {"judge_backend": "deepseek" if self.available else "unavailable", "judge_model": self.flash_model, "judge_escalation_model": self.pro_model, **self.stats.as_dict()}


class MockJudge:
    def __init__(self):
        self.stats = JudgeStats()

    def judge(self, payload: dict[str, Any]) -> dict[str, Any]:
        self.stats.call_count += 1
        candidates = payload.get("candidates", [])
        if not candidates:
            self.stats.abstain_count += 1
            return {"decision": "abstain", "confidence": 0.0, "boundary_start_unit": None, "boundary_end_unit": None, "speaker_boundary_safe": False, "conflicts": [], "reason": "no_candidates"}
        return {"decision": "candidate_1", "confidence": 0.9, "boundary_start_unit": candidates[0].get("unit_ids", [None])[0], "boundary_end_unit": candidates[0].get("unit_ids", [None])[-1], "speaker_boundary_safe": True, "conflicts": [], "reason": "deterministic_mock"}

    def metadata(self) -> dict[str, object]:
        return {"judge_backend": "mock", "judge_model": "fake-judge-v1", **self.stats.as_dict()}
