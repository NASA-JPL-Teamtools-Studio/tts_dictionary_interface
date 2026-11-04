import inspect
import os
from collections import OrderedDict
from lxml import etree

try:
    from importlib.resources import files, as_file
except ImportError:
    from importlib_resources import files, as_file

from tts_utilities.logger import create_logger
logger = create_logger('semantic_dictionary')

class DictionaryAttributeError(AttributeError):
    """
    Raised when a single-valued attribute configured in ATTR_PATHS resolves
    to zero elements against the underlying dictionary.
    """
    pass

def _accepts_document_arg(func):
    """
    Whether `func` is written to accept a second positional argument -- the 
    constructed item itself, which exposes `.document`.
    """
    try:
        signature = inspect.signature(func)
    except (TypeError, ValueError):
        return False

    parameters = list(signature.parameters.values())
    if any(p.kind == inspect.Parameter.VAR_POSITIONAL for p in parameters):
        return True

    positional = [
        p for p in parameters
        if p.kind in (inspect.Parameter.POSITIONAL_ONLY, inspect.Parameter.POSITIONAL_OR_KEYWORD)
    ]
    return len(positional) >= 2

class BaseSemanticDictionary:
    """
    A generic base for reading structured dictionaries (XML, YAML, JSON)
    using a declarative mapping of paths to attributes and items.
    """
    ITEM_PATHS = []
    ITEM_HUMAN_UNIQUE_IDS = []
    ITEM_CLASSES = []
    ATTR_PATHS = {}

    DICTIONARY_MODULE = None
    DICTIONARY_FILENAME = None
    CACHE_CAPACITY = 100

    def __init__(self, source=None, document=None):
        """
        Args:
            source: Version string, file path, or pre-parsed node.
            document: Root node of the parent document (for cross-document resolution).
        """
        if source is None:
            raise ValueError(f"Must specify a source for {self.__class__.__name__}")
        
        # Load the root node
        self.node = self._load_source(source)
        # The document is the root node. If we are an item of another dictionary, 
        # we are passed the root of that dictionary.
        self.document = document if document is not None else self.node
        self._cache = OrderedDict()
        self._node_cache = OrderedDict()
        self._item_count = None

    _CACHE_MISS = object()

    def _cache_get(self, key):
        value = self._cache.get(key, self._CACHE_MISS)
        if value is not self._CACHE_MISS:
            self._cache.move_to_end(key)
        return value

    def _cache_put(self, key, value):
        self._cache[key] = value
        self._cache.move_to_end(key)
        while len(self._cache) > self.CACHE_CAPACITY:
            self._cache.popitem(last=False)
        return value

    def _node_cache_get(self, node):
        key = id(node)
        value = self._node_cache.get(key, self._CACHE_MISS)
        if value is not self._CACHE_MISS:
            self._node_cache.move_to_end(key)
        return value

    def _node_cache_put(self, node, value):
        key = id(node)
        self._node_cache[key] = value
        self._node_cache.move_to_end(key)
        while len(self._node_cache) > self.CACHE_CAPACITY:
            self._node_cache.popitem(last=False)
        return value

    def _item_cache_key(self, node, id_spec):
        for identifier in id_spec.split('|'):
            identifier = identifier.strip()
            if hasattr(node, 'get'):
                value = node.get(identifier)
            elif isinstance(node, dict):
                value = node.get(identifier)
            else:
                value = None
            if value is not None:
                return ('getitem', value)
        return None

    def _wrap_item(self, node, itemclass, id_spec=None, lookup_key=None):
        if lookup_key is not None:
            cached = self._cache_get(('getitem', lookup_key))
            if cached is not self._CACHE_MISS:
                return cached

        item = self._node_cache_get(node)
        if item is self._CACHE_MISS:
            item = itemclass(node, document=self.document)
            self._node_cache_put(node, item)

        if lookup_key is not None:
            self._cache_put(('getitem', lookup_key), item)
        else:
            key = self._item_cache_key(node, id_spec) if id_spec else None
            if key is not None:
                existing = self._cache.get(key, self._CACHE_MISS)
                if existing is self._CACHE_MISS:
                    self._cache_put(key, item)
                elif getattr(existing, 'node', existing) is not getattr(item, 'node', item):
                    # An identifier shared by multiple nodes is ambiguous and
                    # must remain discoverable by __getitem__.
                    self._cache.pop(key, None)
        return item

    def _load_source(self, source):
        """Load the source into self.node. Implemented by subclasses."""
        raise NotImplementedError()

    def select(self, path, filters=None):
        """
        Return a list of nodes matching the path and optional filters.
        filters: {attr_name: value}
        """
        raise NotImplementedError()

    def resolve_attr_value(self, value, attr_class, item_instance):
        """
        Convert a raw node/value into the final attribute value.
        """
        if attr_class is None:
            return value
        if _accepts_document_arg(attr_class):
            return attr_class(value, item_instance)
        return attr_class(value)

    def _effective_item_paths(self):
        """Return ITEM_PATHS if non-empty, else fall back to legacy ITEM_XPATHS."""
        return getattr(type(self), 'ITEM_PATHS', None) or getattr(type(self), 'ITEM_XPATHS', [])

    def __getitem__(self, item):
        cached = self._cache_get(('getitem', item))
        if cached is not self._CACHE_MISS:
            return cached

        elements = []
        item_paths = self._effective_item_paths()
        item_ids = getattr(type(self), 'ITEM_HUMAN_UNIQUE_IDS', [])
        item_classes = getattr(type(self), 'ITEM_CLASSES', [])
        
        for path, id_spec, itemclass in zip(item_paths, item_ids, item_classes):
            identifiers = [id_.strip() for id_ in id_spec.split('|')]
            for id_attr in identifiers:
                matches = self.select(path, {id_attr: item})
                elements.extend([
                    (node, itemclass, id_spec) for node in matches
                ])

        # Deduplicate by node identity
        unique_elements = []
        seen_nodes = set()
        for node, itemclass, id_spec in elements:
            if id(node) not in seen_nodes:
                unique_elements.append((node, itemclass, id_spec))
                seen_nodes.add(id(node))

        if not unique_elements:
            raise KeyError(f'No elements found with value "{item}"')
        if len(unique_elements) > 1:
            raise KeyError(f'More than one element found with value "{item}"')
        
        node, itemclass, id_spec = unique_elements[0]
        return self._wrap_item(node, itemclass, id_spec, lookup_key=item)

    def __getattr__(self, attr):
        cached = self._cache_get(('getattr', attr))
        if cached is not self._CACHE_MISS:
            return cached

        # Try ATTR_PATHS (new 3-tuple: path, attr_class, return_list) first,
        # then fall back to legacy ATTR_XPATHS (4-tuple: xpath, is_text, attr_class, return_list).
        attr_paths = getattr(type(self), 'ATTR_PATHS', None)
        if attr_paths and attr in attr_paths:
            config = attr_paths[attr]
            path = config[0]
            attr_class = config[1] if len(config) > 1 else None
            return_list = config[2] if len(config) > 2 else False
            is_text = False
        else:
            attr_xpaths = getattr(type(self), 'ATTR_XPATHS', None)
            if not attr_xpaths or attr not in attr_xpaths:
                # Fall back to root XML attribute (returns None if not present,
                # matching the legacy SemanticDictionary behavior)
                if hasattr(self.node, 'get'):
                    value = self.node.get(attr)
                    return self._cache_put(('getattr', attr), value)
                raise AttributeError(f"'{self.__class__.__name__}' has no attribute '{attr}'")
            config = attr_xpaths[attr]
            path = config[0]
            is_text = config[1] if len(config) > 1 else False
            attr_class = config[2] if len(config) > 2 else None
            return_list = config[3] if len(config) > 3 else False

        matches = self.select(path)
        
        def resolve(m):
            if is_text and hasattr(m, 'text'):
                m = m.text
            return self.resolve_attr_value(m, attr_class, self)

        if not matches:
            if return_list:
                return []
            raise DictionaryAttributeError(f"Attribute '{attr}' (path '{path}') matched zero elements")

        if return_list:
            value = [resolve(m) for m in matches]
        else:
            value = resolve(matches[0])
        return self._cache_put(('getattr', attr), value)

    def __iter__(self):
        # Use type(self) to avoid triggering __getattr__
        item_paths = self._effective_item_paths()
        item_classes = getattr(type(self), 'ITEM_CLASSES', [])
        item_ids = getattr(type(self), 'ITEM_HUMAN_UNIQUE_IDS', [])
        count = 0
        for index, (path, itemclass) in enumerate(zip(item_paths, item_classes)):
            id_spec = item_ids[index] if index < len(item_ids) else None
            matches = self.select(path)
            for node in matches:
                count += 1
                yield self._wrap_item(node, itemclass, id_spec)
        self._item_count = count

    def __len__(self):
        if self._item_count is None:
            for _ in self:
                pass
        return self._item_count

    def __contains__(self, key):
        cached = self._cache_get(('getitem', key))
        if cached is not self._CACHE_MISS:
            return True

        item_paths = self._effective_item_paths()
        for path, id_spec, itemclass in zip(
            item_paths, self.ITEM_HUMAN_UNIQUE_IDS, self.ITEM_CLASSES
        ):
            identifiers = [id_.strip() for id_ in id_spec.split('|')]
            for id_attr in identifiers:
                matches = self.select(path, {id_attr: key})
                if matches:
                    if len(matches) == 1:
                        self._wrap_item(matches[0], itemclass, id_spec, lookup_key=key)
                    # Preserve the existing boolean semantics for ambiguous
                    # identifiers; __getitem__ remains responsible for
                    # rejecting multiple matches.
                    return True
        return False

class XMLSemanticDictionary(BaseSemanticDictionary):
    """
    XML implementation of the Semantic Interface.
    """
    @property
    def etree(self):
        return self.node

    def xpath(self, xpath):
        """
        Run a raw XPath query against the root element of the dictionary.
        A passthrough to ``self.node.xpath()``.
        """
        return self.node.xpath(xpath)

    def _load_source(self, source):
        if not isinstance(source, (str, os.PathLike)):
            return source.getroot() if hasattr(source, 'getroot') else source
        
        source_str = str(source)
        if not source_str.lower().endswith('.xml'):
            if not self.DICTIONARY_MODULE or not self.DICTIONARY_FILENAME:
                raise ValueError("XMLSemanticDictionary requires DICTIONARY_MODULE/FILENAME for versioned loading")
            package_target = f"{self.DICTIONARY_MODULE}.{source_str}"
            try:
                traversable_path = files(package_target).joinpath(self.DICTIONARY_FILENAME)
                with as_file(traversable_path) as xml_path:
                    return etree.parse(str(xml_path)).getroot()
            except Exception as e:
                raise FileNotFoundError(f"Failed to resolve {source_str}: {e}")
        
        return etree.parse(source_str).getroot()

    def select(self, path, filters=None):
        if filters:
            # Build XPath predicate: [ @attr1="val1" or @attr2="val2" ]
            preds = []
            for attr, val in filters.items():
                if attr == 'text()':
                    preds.append(f'text()="{val}"')
                else:
                    preds.append(f'@{attr}="{val}"')
            
            xpath = f"{path}[{' or '.join(preds)}]"
        else:
            xpath = path
            
        return self.node.xpath(xpath)

# Alias for backward compatibility
SemanticDictionary = XMLSemanticDictionary
