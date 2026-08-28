import pdb
from pathlib import Path
import os
from lxml import etree

try:
    # Python 3.9+ 
    from importlib.resources import files, as_file
except ImportError:
    # Backport for Python 3.6, 3.7, and 3.8
    from importlib_resources import files, as_file

from tts_utilities.logger import create_logger
logger = create_logger('semantic_dictionary')

#Requirements:
#    Commands
#        Every project needs to have a command dictioanry
#        Every command class needs a stem attr
#        Every command class needs an opcode attr
#        Every command class needs an opscat attr
#        Every command class needs an args attr that is an ArgumentList
#        Every command argument needs a name attr
#        Every command argument needs a units attr
#        Every command argument needs a way to understand length
#        Every command argument needs a min attr (is this true for all? or just for numeric?)
#        Every command argument needs a max attr (is this true for all? or just for numeric?)
#    Channels
#        Every project needs to have a channel dictioanary
#        Every channel class needs an measurement_id attr
#        Every channel class needs a channel_id attr
#        Every channel class needs a channel_name attr
#        Every channel class needs an opscat attr
#        Every channel class needs to have a type attr
#            Needs to be translated to chill type (e.g. naive dn/eu/status/dnString)

class SemanticDictionary:
    """
    A base reading AMPCS dictionaries (or really any XML file) more Pythonically.

    This class is a bit obtuse, so please take a look at DemoSat's implementation in
    tts-demosat/demosat_dictionary_interface for an example of how this looks when
    realized against an actual space mission.

    This class provides a dictionary-like interface to an XML tree. It allows retrieval of
    items via specific unique IDs defined in the subclass configuration, and dynamic
    attribute access via configured XPaths.

    Attributes:
        ITEM_XPATHS (list): A list of XPath strings used to find items. An item in this context is
        the primary human-parseable artifact in the XML. (e.g. for command.xml, it's a command). If
        you extend SemanticDictionary and do "for x in SemanticDictionaryExtension: x", you will
        iterate through these "items""
        ITEM_HUMAN_UNIQUE_IDS (list): The expected human-readable ID for items
        ITEM_CLASSES (list): The class to pass items ETREE elements to.
        ATTR_XPATHS (dict): A mapping of XML xpaths to Pyhton attributes
        DICTIONARY_MODULE (str): Package path containing dictionaries (e.g., "demosat_dict.dictionaries").
        DICTIONARY_FILENAME (str): Filename of the target XML (e.g., "command.xml").
    """
    ITEM_XPATHS = []
    ITEM_HUMAN_UNIQUE_IDS = []
    ITEM_CLASSES = []
    ATTR_XPATHS = {}

    # Configuration for auto-resolving packaged dictionaries
    DICTIONARY_MODULE = None
    DICTIONARY_FILENAME = None

    def __init__(self, source=None):
        """
        Initialize the SemanticDictionary.

        Args:
            source (str, os.PathLike, etree._ElementTree, or etree.Element): 
                The source of the XML data or a dictionary version string.
                - Version string (e.g., 'v1', 'v2', 'current'): Resolves the file from DICTIONARY_MODULE.
                - File path string or Path object: Parses the specified XML file on disk.
                - etree._ElementTree or etree.Element: Uses the pre-parsed XML node directly.

        Raises:
            ValueError: If source is None.
            FileNotFoundError: If a version string or file path fails to resolve.
        """
        if source is None:
            raise ValueError(
                f"Must explicitly specify a version (e.g., {self.__class__.__name__}('v1') "
                f"or {self.__class__.__name__}('current')), a file path, or an XML node."
            )

        # 1. Handle in-memory lxml ElementTree or Element nodes
        if not isinstance(source, (str, os.PathLike)):
            self.etree = source.getroot() if hasattr(source, 'getroot') else source
            return

        source_str = str(source)

        # 2. Check if source is a file path or a version tag (e.g., 'v1', 'v2', 'current')
        # All valid dictionary file paths end in '.xml'. If it doesn't, treat it as a version package.
        if not source_str.lower().endswith('.xml'):
            if not self.DICTIONARY_MODULE or not self.DICTIONARY_FILENAME:
                raise ValueError(
                    f"Attempted to resolve version '{source_str}', but {self.__class__.__name__} "
                    f"does not define DICTIONARY_MODULE and DICTIONARY_FILENAME."
                )

            package_target = f"{self.DICTIONARY_MODULE}.{source_str}"
            try:
                # Use importlib.resources backport to safely locate the file (works in zipped wheels too)
                traversable_path = files(package_target).joinpath(self.DICTIONARY_FILENAME)
                
                # Extract to a temporary file if zipped, or use direct path if on standard filesystem
                with as_file(traversable_path) as xml_path:
                    if not xml_path.exists():
                        raise FileNotFoundError(f"File '{self.DICTIONARY_FILENAME}' not found in package '{package_target}'.")
                    
                    # Parse the tree inside the context manager
                    tree = etree.parse(str(xml_path))
                    self.etree = tree.getroot()
                    return  # Successfully parsed the package resource, we are done
            except Exception as e:
                raise FileNotFoundError(
                    f"Failed to resolve version '{source_str}' for {self.__class__.__name__} "
                    f"in '{package_target}/{self.DICTIONARY_FILENAME}': {e}"
                )

        # 3. Parse the explicit local file path
        tree = etree.parse(source_str)
        self.etree = tree.getroot()

    def xpath(self, xpath):
        """
        Run a raw XPath query against the root element of this dictionary. Literally just
        a passthrough of etree.xpath so you can get to any part of the XML you want below
        this node.

        Args:
            xpath (str): The XPath query string to execute.

        Returns:
            list: A list of lxml elements or values matching the query.
        """
        return self.etree.xpath(xpath)

    def __getitem__(self, item):
        """
        Retrieve a specific item from the dictionary by its unique identifier.

        This iterates through the configured ITEM_XPATHS and ITEM_HUMAN_UNIQUE_IDS. It constructs
        an XPath query to find the element where the unique ID attribute matches the provided item.

        Args:
            item (str): The unique identifier value (e.g., a command stem or channel ID) to search for.

        Returns:
            object: An instance of the corresponding class from ITEM_CLASSES wrapping the found element.

        Raises:
            Exception: If no elements are found matching the identifier.
            Exception: If more than one element is found matching the identifier.
        """
        elements = []
        xpaths = []
        
        for itemxpath, itemid, itemclass in zip(self.ITEM_XPATHS, self.ITEM_HUMAN_UNIQUE_IDS, self.ITEM_CLASSES):
            # 1. Build the condition list (Handles keys like 'name|abbreviation')
            conditions = []
            for attr in itemid.split('|'):
                attr = attr.strip()
                
                # Special handling: Look at text content vs attributes
                if attr == 'text()':
                    conditions.append(f'text()="{item}"')
                else:
                    conditions.append(f'@{attr}="{item}"')
            
            # 2. Join with OR and wrap in brackets: [name="X" or abbreviation="X"]
            attr_def = '[' + ' or '.join(conditions) + ']'
            
            # 3. Execute Query
            xpath_query = f'{itemxpath}{attr_def}'
            xpaths.append(xpath_query)
            elements += [itemclass(x) for x in self.etree.xpath(xpath_query)]

        if len(elements) == 0:
            raise Exception(f'No elements found with value "{item}" on xpath(s): {xpaths}')
        if len(elements) > 1:
            raise Exception(f'More than one element found with value "{item}" on xpath(s): {xpaths}')
            
        return elements[0]

    def __getattr__(self, attr):
        """
        Retrieve a dynamic attribute or a standard XML attribute.

        If the attribute is defined in ATTR_XPATHS, the configured XPath is executed.
        Otherwise, it attempts to get the value as a standard attribute of the XML root.

        Args:
            attr (str): The name of the attribute to retrieve.

        Returns:
            Any: The wrapped object, text content, or raw element if defined in ATTR_XPATHS;
                 otherwise, the string value of the XML attribute on the root element.
        """
        if attr in self.ATTR_XPATHS.keys():
            config = self.ATTR_XPATHS[attr]
            xpath = config[0]
            is_text = config[1]
            attr_class = config[2]
            # Safely get the 4th argument, default to False
            return_list = config[3] if len(config) > 3 else False

            element_list = self.etree.xpath(xpath)

            # Helper to safely extract value/text from a single result
            def resolve_value(item):
                if attr_class is not None:
                    return attr_class(item)
                
                # If we asked for text, but got an Element, get .text
                if is_text and hasattr(item, 'text'):
                    return item.text
                
                # If we asked for text, but item is already a string (because xpath ended in /text()), return it
                if is_text and isinstance(item, str):
                    return item
                
                # Otherwise return the raw item (Element or String)
                return item

            # --- 1. Nothing Found ---
            if len(element_list) == 0:
                # If expecting a list, return empty list. Otherwise None.
                return [] if return_list else None

            # --- 2. List Requested ---
            if return_list:
                return [resolve_value(e) for e in element_list]

            # --- 3. Single Item Requested ---
            return resolve_value(element_list[0])

        else:
            return self.etree.get(attr)

    def __iter__(self):
        """
        Iterate over all configured items in the dictionary.

        This method chains together all elements found by the configured ITEM_XPATHS,
        wrapping them in their respective ITEM_CLASSES.

        Yields:
            object: Instances of the item classes defined in the configuration.
        """
        elements = []
        for itemxpath, itemclass in zip(self.ITEM_XPATHS, self.ITEM_CLASSES):
            elements += [itemclass(x) for x in self.etree.xpath(itemxpath)]
        for e in elements: yield e

    def __len__(self):
        # Return the number of items in the members list
        return len([x for x in self])

    def __contains__(self, key):
        """
        Enables 'if "KEY" in dictionary' syntax.

        Iterates through the configured ITEM_XPATHS and ITEM_HUMAN_UNIQUE_IDS
        to checks if an element with the given key exists.
        """
        # Zip together the XPath locations and the Attribute IDs defining "uniqueness"
        for itemxpath, itemid in zip(self.ITEM_XPATHS, self.ITEM_HUMAN_UNIQUE_IDS):
            
            # 1. Build the condition list (Handles keys like 'name|abbreviation')
            conditions = []
            for attr in itemid.split('|'):
                attr = attr.strip()
                
                # Special handling: Look at text content vs attributes
                if attr == 'text()':
                    conditions.append(f'text()="{key}"')
                else:
                    conditions.append(f'@{attr}="{key}"')
            
            # 2. Join with OR: [name="X" or abbreviation="X"]
            predicate = " or ".join(conditions)
            
            # 3. Construct full query: e.g. telemetry_definitions/telemetry[@name="X"]
            query = f"{itemxpath}[{predicate}]"
            
            # 4. Check existence (xpath returns a list; empty list is False)
            if self.etree.xpath(query):
                return True
                
        return False