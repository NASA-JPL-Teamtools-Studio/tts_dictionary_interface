"""
A generic base for reading any dict/list-tree-shaped dictionary format
(YAML, and in principle JSON) the same way `base.SemanticDictionary` reads
XML: declarative `ATTR_PATHS`/`ITEM_PATHS`/`ITEM_CLASSES`/
`ITEM_HUMAN_UNIQUE_IDS` configuration, resolved at attribute-access time
against a small path-query language instead of XPath.

This class is not specific to any one mission or dictionary flavor (AIT,
FSS, or otherwise) -- exactly like `SemanticDictionary` works for any XML
document regardless of where its nodes live, `TreeSemanticDictionary`
works for any dict/list document regardless of where its keys live. All
mission-specific knowledge (what the packets/fields/commands are actually
called) belongs in a concrete subclass's `ATTR_PATHS`/`ITEM_PATHS`
configuration, not in this module.

Path language (deliberately small, mirrors the subset of XPath that
`SemanticDictionary` actually uses):

    "a/b"            -- descend into key "a", then key "b"
    "a[k=\"v\"]"      -- descend into key "a", keep only items where
                          item["k"] == "v" (compared as strings)
    "."              -- the current node's own list elements (or the node
                          itself, if it isn't a list) -- used when items
                          live directly at the root of a document (e.g. a
                          flat top-level list of EVRs), which has no
                          XPath equivalent since XML documents always have
                          a single root element to descend from.

Every step, and the path as a whole, always resolves to a list, exactly
like XPath -- callers can't tell from the return type alone whether zero,
one, or many things matched.

Cross-document resolution:

    An item constructed by `TreeSemanticDictionary.__getitem__`/
    `__iter__` is handed a `.document` attribute -- the root node of the
    top-level document it was ultimately constructed from, regardless of
    how many `ITEM_PATHS` levels deep it was nested. This is what lets an
    `ATTR_PATHS` value-transform callable resolve a query against some
    *other* top-level section of the document, not just the node it
    itself was matched from -- the general primitive any "type table" /
    "lookup table" tree format needs (e.g. F-Prime's per-field `type`
    indirecting into a separate top-level `typeDefinitions` array by
    `qualifiedName`, rather than embedding the full type definition
    inline).

    Calling convention: an `ATTR_PATHS` entry's value-transform callable
    (`config[1]`, historically written as a single-argument
    `lambda node: ...`) may optionally accept a second positional
    argument -- the constructed item itself (`self`) -- in which case
    it's called as `func(value, item)` instead of `func(value)`. Use
    `item.document` inside the callable to run a fresh `select()` (or any
    other lookup) against the whole document. Whether a given callable
    opts in is detected automatically via `_accepts_document_arg`
    (signature introspection) -- no explicit flag is needed in
    `ATTR_PATHS` itself, and every pre-existing single-argument callable
    keeps working completely unchanged.
"""
import json
import os
import re

import yaml

try:
    from importlib.resources import files, as_file
except ImportError:
    from importlib_resources import files, as_file

from tts_dictionary_interface.base import BaseSemanticDictionary

_SEGMENT_RE = re.compile(r'^([^\[]*)(?:\[(.*)\])?$')


def _parse_segment(segment):
    match = _SEGMENT_RE.match(segment)
    key = match.group(1)
    filter_str = match.group(2)
    filters = {}
    if filter_str:
        for condition in filter_str.split(' and '):
            attr, _, value = condition.partition('=')
            filters[attr.strip().lstrip('@')] = value.strip().strip('"\'')
    return key, filters


def _flatten(items):
    """
    Recursively flattens lists-of-lists (but never dicts) into a single
    flat list. This is what lets a document built from nested
    `!include`s (a list containing sub-lists containing more sub-lists)
    behave exactly like a single flat list of items.
    """
    flat = []
    for item in items:
        if isinstance(item, list):
            flat.extend(_flatten(item))
        else:
            flat.append(item)
    return flat


def _descend_one(node, key):
    if key == '.' or key == '':
        if isinstance(node, list):
            return node
        return [node]
    if isinstance(node, dict):
        if key not in node:
            return []
        value = node[key]
        return value if isinstance(value, list) else [value]
    if isinstance(node, list):
        results = []
        for item in node:
            results.extend(_descend_one(item, key))
        return results
    return []


def select(node, path):
    """
    Resolve a path (see module docstring) against a dict/list tree,
    always returning a list of matches.
    """
    current = _flatten([node])
    for segment in [s for s in path.split('/') if s != '']:
        key, filters = _parse_segment(segment)
        current = _flatten([_descend_one(n, key) for n in current])
        if filters:
            current = [
                item for item in current
                if isinstance(item, dict)
                and all(str(item.get(attr)) == value for attr, value in filters.items())
            ]
    return current


class TreeSemanticDictionary(BaseSemanticDictionary):
    """
    The dict/list-tree analog of `SemanticDictionary`. See module
    docstring for the path language, and `SemanticDictionary` for the
    concepts (`ATTR_PATHS`/`ITEM_PATHS`/`ITEM_CLASSES`/
    `ITEM_HUMAN_UNIQUE_IDS`) this mirrors.
    """
    # These are defined in BaseSemanticDictionary

    def _load_source(self, source):
        if isinstance(source, (dict, list)):
            return source

        source_str = str(source)

        if os.path.exists(source_str):
            return self._load_file(source_str)

        if not self.DICTIONARY_MODULE:
            raise ValueError(
                f"Attempted to resolve version '{source_str}', but {self.__class__.__name__} "
                f"does not define DICTIONARY_MODULE."
            )

        package_target = f"{self.DICTIONARY_MODULE}.{source_str}"
        try:
            traversable_path = files(package_target)
            with as_file(traversable_path) as resolved_path:
                if not resolved_path.exists():
                    raise FileNotFoundError(f"Package '{package_target}' does not exist.")
                return self._load_file(str(resolved_path))
        except Exception as e:
            raise FileNotFoundError(
                f"Failed to resolve version '{source_str}' for {self.__class__.__name__} "
                f"in '{package_target}': {e}"
            )

    @classmethod
    def _load_file(cls, path):
        """
        Turn a resolved file or directory path into this dictionary's
        node.
        """
        if os.path.isdir(path):
            if not cls.DICTIONARY_FILENAME:
                raise ValueError(
                    f"{cls.__name__} must define DICTIONARY_FILENAME to load from a directory."
                )
            path = os.path.join(path, cls.DICTIONARY_FILENAME)

        extension = os.path.splitext(path)[1].lower()
        with open(path) as f:
            if extension == '.json':
                return json.load(f)
            if extension in ('.yaml', '.yml'):
                return yaml.safe_load(f)

        raise ValueError(
            f"{cls.__name__} doesn't know how to load '{path}' -- unrecognized extension "
            f"'{extension}'. Override _load_file() to support this format."
        )

    def select(self, path, filters=None):
        """
        Resolve a path against a dict/list tree.
        """
        if filters:
            # For TreeSemanticDictionary, we append the filter to the path.
            # Note: we use ' and ' as per the original implementation, 
            # but BaseSemanticDictionary calls select() in a loop for OR.
            filter_str = ' and '.join(f'{attr.strip()}="{val}"' for attr, val in filters.items())
            path = f"{path}[{filter_str}]"
        
        return select(self.node, path)

    def path(self, path):
        """Run a raw path query against this node. See module docstring."""
        return select(self.node, path)
