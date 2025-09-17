import re
from typing import Iterable, List


def normalize_whitespace(text: str) -> str:
	text = text.replace("\u00a0", " ")
	text = re.sub(r"[ \t]+", " ", text)
	text = re.sub(r"\s*\n\s*", "\n", text)
	return text.strip()


def split_into_sentences(text: str) -> List[str]:
	candidate = re.sub(r"([.!?])\s+(?=[A-Z0-9])", r"\1\n", text)
	parts = [p.strip() for p in candidate.split("\n") if p.strip()]
	return parts


def chunk_text(text: str, max_tokens: int = 512) -> List[str]:
	"""Approximate token chunking by word count (1 token ~= 0.75 word typical)."""
	words = text.split()
	if not words:
		return []
	approx_words_per_chunk = max(50, int(max_tokens * 0.75))
	chunks: List[str] = []
	for i in range(0, len(words), approx_words_per_chunk):
		chunk = " ".join(words[i : i + approx_words_per_chunk]).strip()
		if chunk:
			chunks.append(chunk)
	return chunks


def batched(iterable: Iterable[str], batch_size: int) -> Iterable[List[str]]:
	batch: List[str] = []
	for item in iterable:
		batch.append(item)
		if len(batch) >= batch_size:
			yield batch
			batch = []
	if batch:
		yield batch
