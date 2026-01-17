from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path

import numpy as np
import torch
import torch.nn.functional as F
from PIL import Image
from transformers import CLIPModel, CLIPProcessor

from app.domain.entities import AnimeCandidate
from app.domain.ports.vision import VisionRecognizer

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ClipConfig:
    model_path: str
    device: str
    use_fp16: bool
    concurrency: int
    index_path: str | None
    build_index_on_startup: bool
    text_batch_size: int


class ClipAnimeRecognizer(VisionRecognizer):
    def __init__(
        self,
        *,
        model: CLIPModel,
        processor: CLIPProcessor,
        device: torch.device,
        dtype: torch.dtype,
        semaphore: asyncio.Semaphore,
        index_path: str | None,
        text_batch_size: int,
    ) -> None:
        self._model = model
        self._processor = processor
        self._device = device
        self._dtype = dtype
        self._semaphore = semaphore
        self._index_path = index_path
        self._text_batch_size = int(text_batch_size)

        self._titles: list[str] = []
        self._text_embeddings: torch.Tensor | None = None

    @classmethod
    async def create(cls, *, cfg: ClipConfig) -> "ClipAnimeRecognizer":
        device = _select_device(cfg.device)
        dtype = _select_dtype(device=device, use_fp16=cfg.use_fp16)

        model = await asyncio.to_thread(
            CLIPModel.from_pretrained,
            cfg.model_path,
            local_files_only=True,
            torch_dtype=dtype,
        )
        processor = await asyncio.to_thread(CLIPProcessor.from_pretrained, cfg.model_path, local_files_only=True)

        model.eval()
        model.to(device)

        sem = asyncio.Semaphore(max(1, int(cfg.concurrency)))

        recognizer = cls(
            model=model,
            processor=processor,
            device=device,
            dtype=dtype,
            semaphore=sem,
            index_path=cfg.index_path,
            text_batch_size=cfg.text_batch_size,
        )

        if cfg.build_index_on_startup and cfg.index_path:
            Path(cfg.index_path).parent.mkdir(parents=True, exist_ok=True)

        return recognizer

    async def initialize_index(self, *, titles: list[str], rebuild: bool) -> None:
        normalized_titles = [t.strip() for t in titles if isinstance(t, str) and t.strip()]
        if not normalized_titles:
            raise RuntimeError("no titles available for CLIP index")

        normalized_titles = _dedupe_preserve_order(normalized_titles)

        if not rebuild and self._index_path:
            loaded = await asyncio.to_thread(_load_index, self._index_path)
            if loaded is not None:
                loaded_titles, loaded_embeds = loaded
                if loaded_titles == normalized_titles:
                    self._titles = loaded_titles
                    self._text_embeddings = torch.from_numpy(loaded_embeds).to(self._device, dtype=self._dtype)
                    return

        embeds = await asyncio.to_thread(self._build_text_embeddings_sync, normalized_titles)
        self._titles = normalized_titles
        self._text_embeddings = embeds

        if self._index_path:
            await asyncio.to_thread(_save_index, self._index_path, normalized_titles, embeds.detach().cpu().numpy())

    async def recognize(self, image_bytes: bytes, *, top_k: int) -> list[AnimeCandidate]:
        if self._text_embeddings is None or not self._titles:
            raise RuntimeError("CLIP index not initialized")

        k = max(1, int(top_k))
        async with self._semaphore:
            return await asyncio.to_thread(self._recognize_sync, image_bytes, k)

    def _build_text_embeddings_sync(self, titles: list[str]) -> torch.Tensor:
        batch_size = max(1, self._text_batch_size)
        all_embeds: list[torch.Tensor] = []

        with torch.inference_mode():
            for i in range(0, len(titles), batch_size):
                batch = titles[i : i + batch_size]
                inputs = self._processor(text=batch, padding=True, truncation=True, return_tensors="pt")
                input_ids = inputs["input_ids"].to(self._device)
                attention_mask = inputs["attention_mask"].to(self._device)

                text_features = self._model.get_text_features(input_ids=input_ids, attention_mask=attention_mask)
                text_features = F.normalize(text_features, p=2, dim=-1)
                if self._dtype == torch.float16:
                    text_features = text_features.to(dtype=torch.float16)
                all_embeds.append(text_features.detach())

        embeds = torch.cat(all_embeds, dim=0)
        return embeds

    def _recognize_sync(self, image_bytes: bytes, top_k: int) -> list[AnimeCandidate]:
        with Image.open(BytesIO(image_bytes)) as img:
            image = img.convert("RGB")

        with torch.inference_mode():
            inputs = self._processor(images=image, return_tensors="pt")
            pixel_values = inputs["pixel_values"].to(self._device)
            if self._dtype == torch.float16:
                pixel_values = pixel_values.to(dtype=torch.float16)

            image_features = self._model.get_image_features(pixel_values=pixel_values)
            image_features = F.normalize(image_features, p=2, dim=-1)

            text_embeddings = self._text_embeddings
            if text_embeddings is None:
                raise RuntimeError("CLIP index not initialized")

            sims = (image_features @ text_embeddings.T).squeeze(0)
            values, indices = torch.topk(sims, k=min(top_k, sims.shape[0]))
            probs = torch.softmax(values, dim=0)

            out: list[AnimeCandidate] = []
            for idx, p in zip(indices.tolist(), probs.tolist(), strict=False):
                title = self._titles[int(idx)]
                out.append(AnimeCandidate(title=title, confidence=float(p)))

            out.sort(key=lambda x: x.confidence, reverse=True)
            return out


def _select_device(configured: str) -> torch.device:
    cfg = (configured or "").strip().lower()
    if cfg.startswith("cuda") and torch.cuda.is_available():
        return torch.device("cuda")
    if cfg.startswith("mps") and torch.backends.mps.is_available():
        return torch.device("mps")
    return torch.device("cpu")


def _select_dtype(*, device: torch.device, use_fp16: bool) -> torch.dtype:
    if use_fp16 and device.type == "cuda":
        return torch.float16
    return torch.float32


def _dedupe_preserve_order(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for it in items:
        key = it.strip()
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(key)
    return out


def _load_index(path: str) -> tuple[list[str], np.ndarray] | None:
    p = Path(path)
    if not p.exists() or not p.is_file():
        return None
    try:
        with np.load(p, allow_pickle=False) as data:
            titles_arr = data["titles"]
            embeds = data["embeddings"]
            titles = [str(t) for t in titles_arr.tolist()]
            if not isinstance(embeds, np.ndarray):
                return None
            if embeds.ndim != 2:
                return None
            return titles, embeds.astype(np.float32, copy=False)
    except Exception:  # noqa: BLE001
        return None


def _save_index(path: str, titles: list[str], embeddings: np.ndarray) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)

    embeds = embeddings
    if embeds.dtype != np.float32:
        embeds = embeds.astype(np.float32, copy=False)

    np.savez_compressed(p, titles=np.array(titles, dtype=np.str_), embeddings=embeds)
