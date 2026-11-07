#!/usr/bin/env python3
"""
AST-based docstring coverage check for tts_dictionary_interface.

Prints coverage percentage and exits 0 iff >=80% and no previously-missing
symbols remain undocumented.
"""
import argparse
import ast
import sys
from pathlib import Path

SKIP_DIRS = {"test", "build", ".venv", "__pycache__"}
SKIP_FILES = {"sandbox.py", "conftest.py"}

PREVIOUSLY_MISSING = {
    "tts_dictionary_interface.base.SemanticDictionary.resolve_value",
    "tts_dictionary_interface.tree.TreeSemanticDictionary.resolve",
    "tts_dictionary_interface.contracts.ArgumentContract.name",
    "tts_dictionary_interface.contracts.ArgumentContract.length",
    "tts_dictionary_interface.contracts.ArgumentContract.units",
    "tts_dictionary_interface.contracts.ArgumentContract.min",
    "tts_dictionary_interface.contracts.ArgumentContract.max",
    "tts_dictionary_interface.contracts.CommandContract.stem",
    "tts_dictionary_interface.contracts.CommandContract.opcode",
    "tts_dictionary_interface.contracts.CommandContract.opscat",
    "tts_dictionary_interface.contracts.CommandContract.args",
    "tts_dictionary_interface.contracts.ChannelContract.measurement_id",
    "tts_dictionary_interface.contracts.ChannelContract.channel_id",
    "tts_dictionary_interface.contracts.ChannelContract.channel_name",
    "tts_dictionary_interface.contracts.ChannelContract.type",
    "tts_dictionary_interface.contracts.ChannelContract.module",
    "tts_dictionary_interface.contracts.EvrContract.message",
    "tts_dictionary_interface.contracts.EvrContract.severity",
}

def is_public(name):
    # Public if not private (single leading underscore). Dunder names are public.
    return not (name.startswith("_") and not name.startswith("__"))

def module_name_from_path(py_path, src_root):
    rel = py_path.relative_to(src_root)
    parts = list(rel.with_suffix("").parts)
    # strip leading src if present
    if parts[0] == "src":
        parts = parts[1:]
    return ".".join(parts)

def collect_symbols(src_root):
    symbols = []  # list of (fqname, node)
    documented = set()
    for py_path in src_root.rglob("*.py"):
        # skip
        if any(part in SKIP_DIRS for part in py_path.parts):
            continue
        if py_path.name in SKIP_FILES:
            continue
        # only src/tts_dictionary_interface
        if "tts_dictionary_interface" not in str(py_path):
            continue
        try:
            source = py_path.read_text(encoding="utf-8")
        except Exception:
            continue
        try:
            tree = ast.parse(source, filename=str(py_path))
        except SyntaxError:
            continue
        mod_name = module_name_from_path(py_path, src_root.parent if src_root.name == "src" else src_root)
        # fallback
        # walk
        for node in ast.walk(tree):
            # We need parent context to avoid double counting
            pass
    # Simpler: manual walk with stack
    symbols_info = []
    for py_path in src_root.rglob("*.py"):
        if any(part in SKIP_DIRS for part in py_path.parts):
            continue
        if py_path.name in SKIP_FILES:
            continue
        if "tts_dictionary_interface" not in str(py_path):
            continue
        try:
            source = py_path.read_text(encoding="utf-8")
        except Exception:
            continue
        try:
            tree = ast.parse(source, filename=str(py_path))
        except SyntaxError:
            continue
        mod_name = module_name_from_path(py_path, src_root.parent if src_root.name == "src" else src_root)
        # process module level nodes
        for node in tree.body:
            if isinstance(node, ast.ClassDef) and is_public(node.name):
                fq_class = f"{mod_name}.{node.name}"
                symbols_info.append((fq_class, node))
                # methods
                for item in node.body:
                    if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)) and is_public(item.name):
                        fq = f"{fq_class}.{item.name}"
                        symbols_info.append((fq, item))
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and is_public(node.name):
                fq = f"{mod_name}.{node.name}"
                symbols_info.append((fq, node))
    total = 0
    documented_set = set()
    for fq, node in symbols_info:
        total += 1
        if ast.get_docstring(node):
            documented_set.add(fq)
    return total, documented_set, symbols_info

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--strict-sentences', action='store_true', help='Enforce summary sentence ends with period')
    args = parser.parse_args()
    # repo root is parent of src
    repo_root = Path(__file__).resolve().parents[2]
    src_root = repo_root / "src"
    total, documented_set, symbols_info = collect_symbols(src_root)
    documented_count = len(documented_set)
    pct = (documented_count / total * 100) if total else 0.0
    print(f"Coverage: {documented_count}/{total} = {pct:.1f}%")
    # list symbols
    print("\nSymbols:")
    for fq, node in symbols_info:
        status = "DOC" if fq in documented_set else "MISSING"
        print(f"  {status} {fq}")
    # strict sentence check
    sentence_failures = []
    if args.strict_sentences:
        for fq, node in symbols_info:
            doc = ast.get_docstring(node)
            if not doc:
                continue
            first_line = doc.strip().splitlines()[0].strip()
            if not first_line.endswith('.'):
                sentence_failures.append((fq, first_line))
    # check previously missing
    missing_prev = []
    for sym in PREVIOUSLY_MISSING:
        # if symbol not found, we consider it not applicable
        found = any(fq == sym for fq, _ in symbols_info)
        if not found:
            continue
        if sym not in documented_set:
            missing_prev.append(sym)
    if pct < 80:
        print(f"\nFAIL: coverage {pct:.1f}% < 80%", file=sys.stderr)
        sys.exit(1)
    if sentence_failures:
        print("\nFAIL: docstring summary sentences must end with period:", file=sys.stderr)
        for fq, line in sentence_failures:
            print(f"  {fq}: {line}", file=sys.stderr)
        sys.exit(1)
    if missing_prev:
        print("\nFAIL: previously missing symbols still undocumented:", file=sys.stderr)
        for s in missing_prev:
            print(f"  {s}", file=sys.stderr)
        sys.exit(1)
    print("\nPASS")
    sys.exit(0)

if __name__ == "__main__":
    main()
