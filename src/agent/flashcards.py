from typing import List, Tuple
import re

from .text_utils import split_into_sentences


def keyword_questions(text: str) -> List[Tuple[str, str]]:
	"""Generate basic Q/A from definitions and key phrases."""
	pairs: List[Tuple[str, str]] = []
	sents = split_into_sentences(text)
	for s in sents:
		m = re.search(r"^(.*?)\s+is\s+(.*)$", s, flags=re.IGNORECASE)
		if m:
			topic = m.group(1).strip().strip(" :.-")
			answer = m.group(2).strip().strip(" :.-")
			if len(topic.split()) <= 8 and len(answer.split()) >= 3:
				pairs.append((f"What is {topic}?", answer))
		continue
		# More rules can be added here
	return pairs


def merge_pairs(pairs: List[Tuple[str, str]], max_cards: int = 40) -> List[Tuple[str, str]]:
	seen = set()
	out: List[Tuple[str, str]] = []
	for q, a in pairs:
		key = (q.lower(), a.lower())
		if key in seen:
			continue
		seen.add(key)
		out.append((q, a))
		if len(out) >= max_cards:
			break
	return out
