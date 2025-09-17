import os
from typing import List, Tuple, Dict

from transformers import AutoModelForSeq2SeqLM, AutoTokenizer, AutoModelForCausalLM, pipeline


class Summarizer:
	def __init__(self, model_name: str = "t5-small") -> None:
		self.tokenizer = AutoTokenizer.from_pretrained(model_name)
		self.model = AutoModelForSeq2SeqLM.from_pretrained(model_name)
		self.pipe = pipeline("summarization", model=self.model, tokenizer=self.tokenizer)

	def summarize_chunks(self, chunks: List[str], max_length: int = 180, min_length: int = 60) -> List[str]:
		outputs: List[str] = []
		for ch in chunks:
			text = ch.strip()
			if not text:
				continue
			res = self.pipe(text, truncation=True, max_length=max_length, min_length=min_length)
			outputs.append(res[0]["summary_text"].strip())
		return outputs


class SimpleGenerator:
	def __init__(self, model_name: str = "distilgpt2") -> None:
		self.tokenizer = AutoTokenizer.from_pretrained(model_name)
		self.model = AutoModelForCausalLM.from_pretrained(model_name)

	def generate(self, prompt: str, max_new_tokens: int = 128) -> str:
		inputs = self.tokenizer(prompt, return_tensors="pt")
		outputs = self.model.generate(**inputs, max_new_tokens=max_new_tokens, do_sample=False)
		return self.tokenizer.decode(outputs[0], skip_special_tokens=True)


# Optional cloud providers
class GeminiClient:
	def __init__(self, model_name: str = "gemini-1.5-flash", api_key: str | None = None) -> None:
		key = api_key or os.getenv("GEMINI_API_KEY")
		if not key:
			raise RuntimeError("Gemini API key missing")
		import google.generativeai as genai  # type: ignore
		genai.configure(api_key=key)
		self.model = genai.GenerativeModel(model_name)

	def summarize(self, text: str) -> str:
		prompt = (
			"You are a precise academic summarizer. Summarize the following lecture notes in 5-10 bullet points. "
			"Be concise, keep terminology, and avoid hallucinations.\n\n" + text
		)
		resp = self.model.generate_content(prompt)
		return (resp.text or "").strip()

	def flashcards(self, text: str, num_cards: int = 15) -> List[Tuple[str, str]]:
		prompt = (
			"Generate strictly "
			f"{num_cards} question-answer flashcards from the lecture text. "
			"Return as lines formatted exactly as: Q: <question>\nA: <answer>. "
			"Do not include extra commentary.\n\n" + text
		)
		resp = self.model.generate_content(prompt)
		raw = (resp.text or "").strip()
		pairs: List[Tuple[str, str]] = []
		q, a = None, None
		for line in raw.splitlines():
			line = line.strip()
			if line.lower().startswith("q:"):
				q = line[2:].strip()
			elif line.lower().startswith("a:"):
				a = line[2:].strip()
				if q:
					pairs.append((q, a))
					q, a = None, None
		return pairs

	def formulas(self, text: str) -> List[Tuple[str, Dict[str, str]]]:
		"""Ask Gemini to extract equations and variable definitions.

		Returns list of tuples: (equation_latex_or_plain, {symbol: description}).
		"""
		prompt = (
			"From the lecture text, extract important formulas. For each formula, also list its variables.\n"
			"Output strictly in this format (no extra commentary):\n"
			"E: <equation in LaTeX or plain>\n"
			"V: <symbol> - <short description>\n"
			"V: <symbol> - <short description>\n"
			"-- (blank line between formulas)\n\n" + text
		)
		resp = self.model.generate_content(prompt)
		raw = (resp.text or "").strip()
		items: List[Tuple[str, Dict[str, str]]] = []
		eq: str | None = None
		vars_map: Dict[str, str] = {}
		for line in raw.splitlines():
			line = line.strip()
			if not line:
				if eq:
					items.append((eq, vars_map))
					eq, vars_map = None, {}
				continue
			if line.lower().startswith("e:"):
				if eq:
					items.append((eq, vars_map))
					eq, vars_map = None, {}
				eq = line[2:].strip()
			elif line.lower().startswith("v:"):
				rest = line[2:].strip()
				# split by first hyphen
				parts = rest.split("-", 1)
				if len(parts) == 2:
					sym = parts[0].strip().strip(":")
					desc = parts[1].strip()
					if sym:
						vars_map[sym] = desc
		# flush
		if eq:
			items.append((eq, vars_map))
		return items


class PerplexityClient:
	def __init__(self, model_name: str = "llama-3.1-sonar-small-128k-online") -> None:
		self.api_key = os.getenv("PERPLEXITY_API_KEY")
		if not self.api_key:
			raise RuntimeError("PERPLEXITY_API_KEY is not set")
		self.model_name = model_name

	def _chat(self, system: str, user: str) -> str:
		import requests  # type: ignore
		url = "https://api.perplexity.ai/chat/completions"
		payload = {
			"model": self.model_name,
			"messages": [
				{"role": "system", "content": system},
				{"role": "user", "content": user},
			],
			"temperature": 0.2,
		}
		r = requests.post(url, headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}, json=payload, timeout=120)
		r.raise_for_status()
		data = r.json()
		return data.get("choices", [{}])[0].get("message", {}).get("content", "").strip()

	def summarize(self, text: str) -> str:
		return self._chat(
			"You are a precise academic summarizer.",
			"Summarize the following lecture notes in 5-10 bullet points. Be concise and faithful.\n\n" + text,
		)

	def flashcards(self, text: str, num_cards: int = 15) -> List[Tuple[str, str]]:
		raw = self._chat(
			"You generate flashcards.",
			(
				"Create strictly "
				f"{num_cards} question-answer flashcards from the lecture text. "
				"Return lines formatted exactly as 'Q: <question>' then next line 'A: <answer>'. "
				"No extra commentary.\n\n" + text
			),
		)
		pairs: List[Tuple[str, str]] = []
		q, a = None, None
		for line in raw.splitlines():
			line = line.strip()
			if line.lower().startswith("q:"):
				q = line[2:].strip()
			elif line.lower().startswith("a:"):
				a = line[2:].strip()
				if q:
					pairs.append((q, a))
					q, a = None, None
		return pairs


def get_provider(provider: str, model_name: str = ""):
	p = (provider or "local").lower()
	if p == "gemini":
		return GeminiClient(model_name or "gemini-1.5-flash")
	if p == "perplexity":
		return PerplexityClient(model_name or "llama-3.1-sonar-small-128k-online")
	return None  # local
