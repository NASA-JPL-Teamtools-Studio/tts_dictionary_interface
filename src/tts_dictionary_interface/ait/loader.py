"""
PyYAML loading support for AIT-core-style dictionaries (`!Packet`/`!Field`/
`!Command`/`!Argument`/`!EVR`, and similar mission-specific tags such as
`!Fixed`).

Two responsibilities, per design decisions made while grilling issue #21:

1. Every AIT-core tag is treated as a no-op: a tagged mapping/sequence/
   scalar loads as a plain dict/list/str, ignoring AIT-core's own Python
   tag semantics entirely. This keeps the engine free of any dependency
   on the `ait-core` package.

2. `!include <relative-path>` is a real, resolved directive: the
   referenced file is loaded (relative to the *including* file's own
   directory, never a shared root or the process's cwd) and spliced in
   as if its contents had been written inline. This mirrors the real
   oco3mos dictionaries, where each FSW-version directory's `tlm.yaml` is
   just a manifest of `!include` pointers at its own sibling files.
   Includes may nest to any depth -- resolution is always relative to
   whichever file directly contains the `!include`.
"""
import os

import yaml


class IncludeLoader(yaml.SafeLoader):
    """
    A yaml.SafeLoader that resolves `!include` relative to the directory
    of the file currently being loaded, and treats every other custom
    tag as a no-op (plain dict/list/scalar).
    """

    def __init__(self, stream):
        stream_name = getattr(stream, 'name', None)
        self._root_dir = os.path.dirname(stream_name) if stream_name else '.'
        super().__init__(stream)


def _construct_include(loader, node):
    relative_path = loader.construct_scalar(node)
    path = os.path.join(loader._root_dir, relative_path)
    with open(path, 'r') as f:
        return yaml.load(f, IncludeLoader)


def _construct_ignore_tag(loader, node):
    """
    Load any tagged node as if it were untagged, per its underlying YAML
    kind (mapping/sequence/scalar) -- ignores the tag itself.
    """
    if isinstance(node, yaml.MappingNode):
        return loader.construct_mapping(node, deep=True)
    if isinstance(node, yaml.SequenceNode):
        return loader.construct_sequence(node, deep=True)
    return loader.construct_scalar(node)


IncludeLoader.add_constructor('!include', _construct_include)
# `None` registers a fallback constructor for any tag with no exact or
# multi-constructor match -- i.e. every AIT-core tag except `!include`.
IncludeLoader.add_constructor(None, _construct_ignore_tag)


def load_yaml(path):
    """
    Load an AIT-core-style YAML dictionary file, resolving any `!include`
    directives (recursively, relative to each including file's own
    directory) and ignoring all other custom tags.
    """
    with open(path, 'r') as f:
        return yaml.load(f, IncludeLoader)
