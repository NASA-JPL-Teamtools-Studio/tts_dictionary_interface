"""
JSON loading support for F-Prime topology dictionaries.

Unlike AIT-flavored YAML (see `tts_dictionary_interface.ait`), F-Prime's
topology dictionary is already a single flat JSON document -- there's no
`!include`-style splicing to resolve, so this mixin is a much thinner
`_load_file()` than `AitYamlDictionary`'s.
"""
import json
import os

from tts_dictionary_interface.tree import TreeSemanticDictionary


class FprimeJsonDictionary(TreeSemanticDictionary):
    """
    A `TreeSemanticDictionary` sourced from a single F-Prime JSON topology
    dictionary file. Concrete subclasses set `DICTIONARY_FILENAME` (e.g.
    the real dictionary's `<deployment>TopologyDictionary.json`) so that
    `source=<a directory>` or `source=<a version string>` (resolved
    against `DICTIONARY_MODULE`) both know which file to load.
    """

    @classmethod
    def _load_file(cls, path):
        if os.path.isdir(path):
            if not cls.DICTIONARY_FILENAME:
                raise ValueError(
                    f"{cls.__name__} must define DICTIONARY_FILENAME to load from a directory."
                )
            path = os.path.join(path, cls.DICTIONARY_FILENAME)
        with open(path) as f:
            return json.load(f)
