Semantic Dictionary Interface Narrative
=======================================

Purpose
-------

The ``tts_dictionary_interface`` package provides a format-agnostic interoperability layer for spacecraft dictionary data. It defines a small set of contracts and two core engine base classes – ``SemanticDictionary`` for XML/AMPCS dictionaries and ``TreeSemanticDictionary`` for dict/list-tree dictionaries such as AIT YAML – so that downstream Teamtools libraries can assume a common way to look up commands, telemetry channels, and event records.

The package does not implement mission-specific knowledge. Mission teams subclass the base classes and declare ``ITEM_PATHS``, ``ITEM_CLASSES``, ``ITEM_HUMAN_UNIQUE_IDS`` and ``ATTR_PATHS`` to map their dictionary schema onto the shared contracts.

Architecture Overview
--------------------

ASCII class inheritance diagram::

    SemanticDictionary
        |
        +-- MissionXMLDictionary (e.g., DemoSat command dict)
    
    TreeSemanticDictionary
        |
        +-- AitYamlDictionary
              |
              +-- MissionAITDictionary

Contracts
    ArgumentContract
    CommandContract
    ChannelContract
    EvrContract

Module Guide
------------

``tts_dictionary_interface.base``
    ``SemanticDictionary`` – dictionary-like wrapper around lxml trees.
    ``DictionaryAttributeError`` – raised when a single-valued attribute resolves to zero elements.

``tts_dictionary_interface.tree``
    ``TreeSemanticDictionary`` – analog of ``SemanticDictionary`` for dict/list trees.
    ``select`` – path query helper used by ``TreeSemanticDictionary``.

``tts_dictionary_interface.contracts``
    Format-agnostic contracts for arguments, commands, channels, and EVRs. Concrete classes inherit from these contracts via multiple inheritance.

``tts_dictionary_interface.ait.loader``
    ``AitYamlDictionary`` – ``TreeSemanticDictionary`` subclass that loads AIT-flavored YAML with ``!include`` resolution.
    ``IncludeLoader`` – PyYAML loader that resolves ``!include`` relative to the including file and ignores other custom tags.
    ``load_yaml`` – public helper to load AIT YAML files.

Key Classes
-----------

``SemanticDictionary``
    Provides ``__getitem__``, ``__iter__``, ``__len__``, ``__contains__`` and dynamic attribute access via ``ATTR_XPATHS``. Subclasses configure ``ITEM_XPATHS``, ``ITEM_HUMAN_UNIQUE_IDS``, ``ITEM_CLASSES`` and ``ATTR_XPATHS``.

``TreeSemanticDictionary``
    Same concepts as ``SemanticDictionary`` but for dict/list trees. Uses a small path language ``a/b[k="v"]`` and supports cross-document resolution via the ``.document`` attribute.

``ArgumentContract``, ``CommandContract``, ``ChannelContract``, ``EvrContract``
    Define the required and optional attributes that mission classes must expose. Required attributes raise ``NotImplementedError`` if missing; optional attributes resolve to ``None``.

Extension Guide
---------------

To add a mission-specific dictionary interface:

1. Subclass ``SemanticDictionary`` for XML or ``TreeSemanticDictionary`` for YAML/JSON.
2. Set ``DICTIONARY_MODULE`` and ``DICTIONARY_FILENAME`` for versioned package loading.
3. Declare ``ITEM_PATHS`` / ``ITEM_XPATHS``, ``ITEM_HUMAN_UNIQUE_IDS``, ``ITEM_CLASSES`` and ``ATTR_PATHS`` / ``ATTR_XPATHS``.
4. Make item classes inherit from the appropriate contract, e.g.:

   .. code-block:: python

      class CommandItem(SemanticDictionary, CommandContract):
          pass

See ``demosat_dictionary_interface`` for a concrete example of how a mission plugs in.

Usage Example
-------------

Load a command dictionary and inspect a command:

.. code-block:: python

   from my_mission_dict import CommandDictionary

   cmd_dict = CommandDictionary('current')
   cmd = cmd_dict['MY_CMD']
   print(cmd.stem)          # command stem
   print(cmd.opcode)        # command opcode
   print([a.name for a in cmd.args])  # argument names

The same pattern works for ``TreeSemanticDictionary``-based YAML dictionaries via ``AitYamlDictionary``.

Relationships
-------------

The package uses ``tts_utilities.logger.create_logger`` for consistent logging. No other runtime dependencies are required beyond ``lxml``, ``PyYAML`` and ``importlib_resources`` for Python 3.6 compatibility.
