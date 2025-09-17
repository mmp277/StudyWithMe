from typing import List, Tuple, Dict
import re

MATH_INLINE = re.compile(r"\$(.+?)\$")
MATH_BLOCK = re.compile(r"\\\[(.+?)\\\]", re.DOTALL)
EQUATION = re.compile(r"([A-Za-z0-9_]+)\s*=\s*([^\n]+)")
FRAC = re.compile(r"\b([A-Za-z][A-Za-z0-9_]*)\s*/\s*([A-Za-z][A-Za-z0-9_]*)\b")
SYMBOL = re.compile(r"\\?[A-Za-z][A-Za-z0-9_]*|\\[a-zA-Z]+")


def extract_equations(text: str) -> List[str]:
	blocks = MATH_BLOCK.findall(text)
	inlines = MATH_INLINE.findall(text)
	explicit = []
	for line in text.splitlines():
		m = EQUATION.search(line)
		if m:
			explicit.append(line.strip())
		else:
			if FRAC.search(line):
				explicit.append(line.strip())
	# de-duplicate and drop empties
	return list(dict.fromkeys([e for e in (blocks + inlines + explicit) if e]))


def guess_symbol_definitions(context: str, equation: str) -> Dict[str, str]:
	"""Heuristic: look for patterns like 'where X is ...' or 'X: ...' near the equation."""
	definitions: Dict[str, str] = {}
	symbols = [s for s in SYMBOL.findall(equation) if not s.isdigit()]
	window_lines = context.splitlines()
	context_text = "\n".join(window_lines)
	for sym in symbols:
		pattern_is = re.compile(rf"\b{re.escape(sym)}\b\s+(is|denotes|represents)\s+([^\.;\n]+)", re.IGNORECASE)
		pattern_colon = re.compile(rf"\b{re.escape(sym)}\b\s*:\s*([^\.;\n]+)")
		m1 = pattern_is.search(context_text)
		m2 = pattern_colon.search(context_text) if not m1 else None
		if m1:
			definitions[sym] = m1.group(2).strip()
		elif m2:
			definitions[sym] = m2.group(1).strip()
	return definitions


def format_equation_latex(equation: str) -> str:
	return f"$ {equation} $"
