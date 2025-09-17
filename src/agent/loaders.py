import os
from typing import List, Tuple

from pypdf import PdfReader
try:
	from pdfminer.high_level import extract_text as pdfminer_extract_text  # type: ignore
except Exception:
	pdfminer_extract_text = None  # type: ignore
from docx import Document
try:
	from pdf2image import convert_from_path  # type: ignore
	import pytesseract  # type: ignore
except Exception:
	convert_from_path = None  # type: ignore
	pytesseract = None  # type: ignore


def read_txt(file_path: str) -> str:
	with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
		return f.read()


def read_pdf(file_path: str) -> str:
	# Try PyPDF first
	try:
		reader = PdfReader(file_path)
		texts: List[str] = []
		for page in reader.pages:
			texts.append(page.extract_text() or "")
		joined = "\n".join(texts).strip()
		if joined:
			return joined
	except Exception:
		pass

	# Fallback to pdfminer for tricky PDFs if available
	if pdfminer_extract_text is not None:
		try:
			fallback = pdfminer_extract_text(file_path) or ""
			return fallback.strip()
		except Exception:
			return ""

	# OCR last resort (first 5 pages) if dependencies available
	if convert_from_path is not None and pytesseract is not None:
		try:
			imgs = convert_from_path(file_path, first_page=1, last_page=5, dpi=200)
			ocr_parts: List[str] = []
			for im in imgs:
				ocr_parts.append(pytesseract.image_to_string(im))
			ocr_text = "\n".join(ocr_parts).strip()
			if ocr_text:
				return ocr_text
		except Exception:
			pass
	return ""


def read_docx(file_path: str) -> str:
	doc = Document(file_path)
	paras: List[str] = []
	for p in doc.paragraphs:
		text = p.text.strip()
		if text:
			paras.append(text)
	return "\n".join(paras)


def load_documents_from_dir(directory: str) -> List[Tuple[str, str]]:
	"""
	Return list of (filename, text) for supported file types.
	"""
	results: List[Tuple[str, str]] = []
	for root, _, files in os.walk(directory):
		for name in files:
			path = os.path.join(root, name)
			lower = name.lower()
			try:
				if lower.endswith(".txt"):
					results.append((path, read_txt(path)))
				elif lower.endswith(".pdf"):
					results.append((path, read_pdf(path)))
				elif lower.endswith(".docx"):
					results.append((path, read_docx(path)))
				else:
					# Unsupported format; skip silently
					pass
			except Exception as e:
				# Skip files that fail to parse; collect empty string to note presence
				results.append((path, f""))
	return results
