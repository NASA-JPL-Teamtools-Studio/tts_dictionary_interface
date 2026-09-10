import inspect
import os
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

    def __getitem__(self, item):
        elements = []
        # Support both ITEM_PATHS and ITEM_XPATHS from the class
        item_paths = getattr(type(self), 'ITEM_PATHS', getattr(type(self), 'ITEM_XPATHS', []))
        item_ids = getattr(type(self), 'ITEM_HUMAN_UNIQUE_IDS', [])
        item_classes = getattr(type(self), 'ITEM_CLASSES', [])
        
        for path, id_spec, itemclass in zip(item_paths, item_ids, item_classes):
            identifiers = [id_.strip() for id_ in id_spec.split('|')]
            for id_attr in identifiers:
                matches = self.select(path, {id_attr: item})
                elements.extend([itemclass(node, document=self.document) for node in matches])

        # Deduplicate by node identity
        unique_elements = []
        seen_nodes = set()
        for e in elements:
            # We assume the wrapped item has a .node attribute or is the node itself
            node = getattr(e, 'node', e)
            if id(node) not in seen_nodes:
                unique_elements.append(e)
                seen_nodes.add(id(node))

        if not unique_elements:
            raise KeyError(f'No elements found with value "{item}"')
        if len(unique_elements) > 1:
            raise KeyError(f'More than one element found with value "{item}"')
        
        return unique_elements[0]

    def __getattr__(self, attr):
        # Support both ATTR_PATHS and ATTR_XPATHS from the class
        attr_configs = getattr(type(self), 'ATTR_PATHS', getattr(type(self), 'ATTR_XPATHS', {}))
        if attr not in attr_configs:
            # For XML, we might want to fall back to .get(attr)
            if hasattr(self.node, 'get') and attr in self.node:
                return self.node.get(attr)
            raise AttributeError(f"'{self.__class__.__name__}' has no attribute '{attr}'")

        config = attr_configs[attr]
        path = config[0]
        attr_class = config[1] if len(config) > 1 else None
        return_list = config[2] if len(config) > 2 else False

        matches = self.select(path)
        
        def resolve(m):
            return self.resolve_attr_value(m, attr_class, self)

        if not matches:
            if return_list:
                return []
            raise DictionaryAttributeError(f"Attribute '{attr}' (path '{path}') matched zero elements")

        if return_list:
            return [resolve(m) for m in matches]
        return resolve(matches[0])

    def __iter__(self):
        elements = []
        # Use type(self) to avoid triggering __getattr__
        item_paths = getattr(type(self), 'ITEM_PATHS', getattr(type(self), 'ITEM_XPATHS', []))
        item_classes = getattr(type(self), 'ITEM_CLASSES', [])
        for path, itemclass in zip(item_paths, item_classes):
            matches = self.select(path)
            elements.extend([itemclass(node, document=self.document) for node in matches])
        for e in elements:
            yield e

    def __len__(self):
        return sum(1 for _ in self)

    def __contains__(self, key):
        for path, id_spec in zip(self.ITEM_PATHS, self.ITEM_HUMAN_UNIQUE_IDS):
            identifiers = [id_.strip() for id_ in id_spec.split('|')]
            for id_attr in identifiers:
                if self.select(path, {id_attr: key}):
                    return True
        return False

class XMLSemanticDictionary(BaseSemanticDictionary):
    """
    XML implementation of the Semantic Interface.
    """
    @property
    def etree(self):
        return self.node

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
