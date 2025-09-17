import argparse
import os
from typing import List, Tuple, Dict

from .loaders import load_documents_from_dir
from .text_utils import normalize_whitespace, chunk_text
from .nlp import GeminiClient, Summarizer
from .flashcards import merge_pairs, keyword_questions  # kept for possible post-processing/dedup
from .formulas import extract_equations, guess_symbol_definitions, format_equation_latex
from .output import write_summary_docx, write_flashcards_docx, write_formula_sheet_docx
import os


GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
# When set truthy, do not fall back to local models if Gemini fails
GEMINI_STRICT = os.getenv("GEMINI_STRICT", "").strip().lower() in {"1", "true", "yes", "on"}


def process_directory(input_dir: str, outputs_dir: str | None) -> None:
	if outputs_dir is None or outputs_dir.strip() == "":
		outputs_dir = input_dir
	os.makedirs(outputs_dir, exist_ok=True)

	print(f"[INFO] Using input directory: {input_dir}")
	print(f"[INFO] Writing outputs to: {outputs_dir}")

	client = None
	local_summarizer = None
	if GEMINI_API_KEY:
		try:
			client = GeminiClient(model_name="gemini-1.5-flash", api_key=GEMINI_API_KEY)
		except Exception as e:
			print(f"[WARN] Failed to initialize Gemini client: {e}")
			if not GEMINI_STRICT:
				print("[INFO] Falling back to local summarizer (t5-small). Set GEMINI_STRICT=1 to disable fallback.")
				local_summarizer = Summarizer(model_name="t5-small")
			else:
				print("[INFO] GEMINI_STRICT enabled; continuing without local fallback.")
	else:
		print("[WARN] GEMINI_API_KEY not set. Falling back to local summarizer (t5-small).")
		local_summarizer = Summarizer(model_name="t5-small")

	docs = load_documents_from_dir(input_dir)
	print(f"[INFO] Found {len(docs)} file(s) to process.")

	file_summaries: List[Tuple[str, List[str]]] = []
	flashcards_by_file: List[Tuple[str, List[Tuple[str, str]]]] = []
	formulas_by_file: List[Tuple[str, List[Tuple[str, Dict[str, str]]]]] = []

	for path, text in docs:
		try:
			print(f"[INFO] Processing: {path}")
			clean = normalize_whitespace(text)
			chunks = chunk_text(clean, max_tokens=512)
			joined = "\n\n".join(chunks[:6]) if chunks else clean

			# Summaries with Gemini, fallback to local if allowed
			partial_summaries: List[str] = []
			if client is not None:
				try:
					summary_text = client.summarize(joined)
					partial_summaries = [summary_text] if summary_text else []
				except Exception as e:
					print(f"[WARN] Gemini summarize failed: {e}")
					if not GEMINI_STRICT:
						if local_summarizer is None:
							print("[INFO] Initializing local summarizer (t5-small) due to Gemini error.")
							local_summarizer = Summarizer(model_name="t5-small")
						chunks = chunk_text(clean, max_tokens=256)
						partial_summaries = local_summarizer.summarize_chunks(chunks[:4]) if local_summarizer else []
			if not partial_summaries and local_summarizer is not None and not GEMINI_STRICT:
				chunks = chunk_text(clean, max_tokens=256)
				partial_summaries = local_summarizer.summarize_chunks(chunks[:4]) if local_summarizer else []
			display_name = os.path.basename(path)
			file_summaries.append((display_name, partial_summaries))

			# Flashcards with fallback
			cards: List[Tuple[str, str]] = []
			if client is not None:
				try:
					cards = client.flashcards(clean, num_cards=20)
				except Exception as e:
					print(f"[WARN] Gemini flashcards failed: {e}")
					if not GEMINI_STRICT:
						cards = keyword_questions(clean)
			else:
				cards = keyword_questions(clean)
			# Fallbacks when model yields nothing
			if not cards:
				cards = keyword_questions(clean)
			if not cards and partial_summaries:
				# Derive simple Q/A from the summary bullets
				derived: List[Tuple[str, str]] = []
				for s in partial_summaries[:10]:
					q = (s.split(". ")[0] or s).strip()
					if len(q) > 80:
						q = q[:77] + "..."
					derived.append((f"What is meant by: {q}?", s.strip()))
				cards = derived
			cards = merge_pairs(cards, max_cards=40)
			flashcards_by_file.append((display_name, cards))

			# Formulas via Gemini if available; otherwise local heuristic
			items: List[Tuple[str, Dict[str, str]]] = []
			if client is not None:
				try:
					items = client.formulas(clean)
				except Exception:
					items = []
			if not items:
				eqs = extract_equations(clean)
				for eq in eqs:
					defs = guess_symbol_definitions(clean, eq)
					items.append((format_equation_latex(eq), defs))
			formulas_by_file.append((display_name, items))

			# Per-file outputs
			base = os.path.splitext(os.path.basename(path))[0]
			safe = base.replace(" ", "_").replace("/", "_").replace("\\", "_")
			sum_one = os.path.join(outputs_dir, f"{safe}_summary.docx")
			fc_one = os.path.join(outputs_dir, f"{safe}_flashcards.docx")
			fs_one = os.path.join(outputs_dir, f"{safe}_formula.docx")
			try:
				write_summary_docx(sum_one, [(base, partial_summaries)])
			except Exception:
				pass
			try:
				write_flashcards_docx(fc_one, [(base, cards)])
			except Exception:
				pass
			try:
				write_formula_sheet_docx(fs_one, [(base, items)])
			except Exception:
				pass

		except Exception as e:
			print(f"[ERROR] Failed processing {path}: {e}")
			# Still append empty results to maintain visibility
			file_summaries.append((path, []))
			flashcards_by_file.append((path, []))
			formulas_by_file.append((path, []))

	# Write outputs
	sum_path = os.path.join(outputs_dir, "summaries.docx")
	fc_path = os.path.join(outputs_dir, "flashcards.docx")
	fs_path = os.path.join(outputs_dir, "formula_sheet.docx")
	print(f"[INFO] Writing: {sum_path}")
	write_summary_docx(sum_path, file_summaries)
	print(f"[INFO] Writing: {fc_path}")
	write_flashcards_docx(fc_path, flashcards_by_file)
	print(f"[INFO] Writing: {fs_path}")
	write_formula_sheet_docx(fs_path, formulas_by_file)
	print("[INFO] Done.")



def main() -> None:
	parser = argparse.ArgumentParser(description="AI Lecture Agent (Gemini)")
	parser.add_argument("input_dir", help="Directory containing lecture notes (.pdf, .txt, .docx)")
	parser.add_argument("--out", dest="outputs_dir", default=None, help="Output directory (defaults to input directory)")
	args = parser.parse_args()

	process_directory(args.input_dir, args.outputs_dir)


if __name__ == "__main__":
	main()
