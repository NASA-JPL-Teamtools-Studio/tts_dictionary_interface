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
"""
import json
import os
import re

import yaml

try:
    from importlib.resources import files, as_file
except ImportError:
    from importlib_resources import files, as_file

from tts_dictionary_interface.base import DictionaryAttributeError

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


class TreeSemanticDictionary:
    """
    The dict/list-tree analog of `SemanticDictionary`. See module
    docstring for the path language, and `SemanticDictionary` for the
    concepts (`ATTR_PATHS`/`ITEM_PATHS`/`ITEM_CLASSES`/
    `ITEM_HUMAN_UNIQUE_IDS`) this mirrors.
    """
    ITEM_PATHS = []
    ITEM_HUMAN_UNIQUE_IDS = []
    ITEM_CLASSES = []
    ATTR_PATHS = {}

    # Configuration for auto-resolving packaged dictionaries, mirroring
    # SemanticDictionary's DICTIONARY_MODULE/DICTIONARY_FILENAME.
    DICTIONARY_MODULE = None
    DICTIONARY_FILENAME = None

    def __init__(self, source=None):
        """
        Args:
            source (dict, list, str, or os.PathLike):
                - dict or list: a pre-parsed node, used directly.
                - File or directory path: passed to `_load_file()`.
                - Version string (e.g. 'v1', 'current'): resolves a file
                  or directory named DICTIONARY_FILENAME (if any) inside
                  the `DICTIONARY_MODULE.<source>` package, then passes
                  it to `_load_file()`.

        Raises:
            ValueError: If source is None, or if resolving a version
                string is attempted without DICTIONARY_MODULE set.
            FileNotFoundError: If a version string or file path fails to
                resolve.
        """
        if source is None:
            raise ValueError(
                f"Must explicitly specify a version (e.g., {self.__class__.__name__}('v1') "
                f"or {self.__class__.__name__}('current')), a file/directory path, or a "
                f"pre-parsed node (dict/list)."
            )

        if isinstance(source, (dict, list)):
            self.node = source
            return

        source_str = str(source)

        if os.path.exists(source_str):
            self.node = self._load_file(source_str)
            return

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
                self.node = self._load_file(str(resolved_path))
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

        Autodetects plain JSON and plain YAML by extension -- this covers
        any dict/list format with no format-specific loading quirks of
        its own (e.g. F-Prime's JSON topology dictionaries). Formats that
        need something more (AIT-flavored YAML's `!include` resolution,
        say) should override this method entirely rather than fight it;
        see `tts_dictionary_interface.ait.AitYamlDictionary` for an
        example.
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

    def path(self, path):
        """Run a raw path query against this node. See module docstring."""
        return select(self.node, path)

    def __getattr__(self, attr):
        if attr not in self.ATTR_PATHS:
            raise AttributeError(
                f"'{self.__class__.__name__}' object has no attribute '{attr}'"
            )

        config = self.ATTR_PATHS[attr]
        path_str = config[0]
        attr_class = config[1] if len(config) > 1 else None
        return_list = config[2] if len(config) > 2 else False

        matches = select(self.node, path_str)

        def resolve(value):
            return attr_class(value) if attr_class is not None else value

        if len(matches) == 0:
            if return_list:
                return []
            raise DictionaryAttributeError(
                f"'{self.__class__.__name__}' object has no value for "
                f"attribute '{attr}' (path '{path_str}' matched zero elements)"
            )

        if return_list:
            return [resolve(m) for m in matches]
        return resolve(matches[0])

    def __getitem__(self, item):
        elements = []
        paths = []
        for itempath, itemid, itemclass in zip(self.ITEM_PATHS, self.ITEM_HUMAN_UNIQUE_IDS, self.ITEM_CLASSES):
            conditions = ' and '.join(f'{attr.strip()}="{item}"' for attr in itemid.split('|'))
            full_path = f'{itempath}[{conditions}]'
            paths.append(full_path)
            elements += [itemclass(x) for x in select(self.node, full_path)]

        if len(elements) == 0:
            raise KeyError(f'No elements found with value "{item}" on path(s): {paths}')
        if len(elements) > 1:
            raise KeyError(f'More than one element found with value "{item}" on path(s): {paths}')
        return elements[0]

    def __iter__(self):
        elements = []
        for itempath, itemclass in zip(self.ITEM_PATHS, self.ITEM_CLASSES):
            elements += [itemclass(x) for x in select(self.node, itempath)]
        for e in elements:
            yield e

    def __len__(self):
        # A list comprehension, not list(self) -- list() calls len() as a
        # sizing hint before iterating, which would recurse right back
        # into this method.
        return len([x for x in self])

    def __contains__(self, key):
        for itempath, itemid in zip(self.ITEM_PATHS, self.ITEM_HUMAN_UNIQUE_IDS):
            conditions = ' and '.join(f'{attr.strip()}="{key}"' for attr in itemid.split('|'))
            if select(self.node, f'{itempath}[{conditions}]'):
                return True
        return False
