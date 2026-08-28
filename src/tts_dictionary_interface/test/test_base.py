import sys
import pytest
from unittest.mock import MagicMock, patch
from lxml import etree

# --- MOCKING EXTERNAL DEPENDENCIES ---
# We mock tts_utilities before importing the module to avoid ModuleNotFoundError
sys.modules['tts_utilities'] = MagicMock()
sys.modules['tts_utilities.logger'] = MagicMock()

# Assuming the user's code is in a file named `semantic_dictionary.py`
# If you are pasting this into a single file, put the class definition above this line.
from tts_dictionary_interface.base import SemanticDictionary, DictionaryAttributeError

# --- FIXTURES AND SETUP ---

@pytest.fixture
def sample_xml():
    """Creates a temporary sample XML string for testing."""
    return b"""
    <Project name="TestProject" version="1.0">
        <Commands>
            <Command stem="CMD_A" opcode="0x01" opscat="flight">
                <Args>
                    <Arg name="arg1" units="sec" min="0" max="10"/>
                </Args>
            </Command>
            <Command stem="CMD_B" opcode="0x02" opscat="ground">
                <Args>
                    <Arg name="arg2" units="m/s"/>
                </Args>
            </Command>
             <Command stem="CMD_DUP" opcode="0x03" />
            <Command stem="CMD_DUP" opcode="0x04" />
        </Commands>
        <Channels>
            <Channel id="100" name="ChanA" type="float"/>
        </Channels>
        <Metadata>
            <Description>A test dictionary</Description>
        </Metadata>
    </Project>
    """

class CommandWrapper:
    """A dummy wrapper class to test ITEM_CLASSES instantiation."""
    def __init__(self, element):
        self.element = element
        self.stem = element.get('stem')

class ConcreteDictionary(SemanticDictionary):
    """
    A concrete implementation of the base class.
    We must populate the configuration constants to test the logic.
    """
    # Look for Commands, identify them by 'stem' or 'opcode', wrap them in CommandWrapper
    ITEM_XPATHS = ['.//Command']
    ITEM_HUMAN_UNIQUE_IDS = ['stem|opcode'] 
    ITEM_CLASSES = [CommandWrapper]
    
    # Map 'description' to the text of the Description tag
    # Map 'project_name' to the 'name' attribute of the root (via fallback or XPath)
    ATTR_XPATHS = {
        'description': ('.//Description', True, None),  # (xpath, is_text, class)
        'all_args': ('.//Arg', False, None) # Return raw element list (or first element)
    }

@pytest.fixture
def concrete_dict(tmp_path, sample_xml):
    """Creates an instance of the ConcreteDictionary using a temporary file."""
    f = tmp_path / "test_dict.xml"
    f.write_bytes(sample_xml)
    return ConcreteDictionary(str(f))

# --- TEST CASES ---

class TestInitialization:
    def test_init_with_path(self, tmp_path, sample_xml):
        f = tmp_path / "test.xml"
        f.write_bytes(sample_xml)
        sd = SemanticDictionary(str(f))
        assert isinstance(sd.etree, etree._Element)

    def test_init_with_element(self, sample_xml):
        root = etree.fromstring(sample_xml)
        sd = SemanticDictionary(root)
        assert sd.etree == root

    def test_init_invalid_path(self):
        with pytest.raises(OSError):
            SemanticDictionary("non_existent_file.xml")

class TestGetItem:
    """Tests for __getitem__ (e.g., dict['key'])"""
    
    def test_get_item_by_stem_success(self, concrete_dict):
        # Should find CMD_A using the 'stem' attribute defined in ITEM_HUMAN_UNIQUE_IDS
        item = concrete_dict['CMD_A']
        assert isinstance(item, CommandWrapper)
        assert item.element.get('opcode') == '0x01'

    def test_get_item_by_opcode_success(self, concrete_dict):
        # Should find CMD_B using the 'opcode' attribute (second part of the split)
        item = concrete_dict['0x02']
        assert item.stem == 'CMD_B'

    def test_get_item_not_found(self, concrete_dict):
        with pytest.raises(Exception) as excinfo:
            _ = concrete_dict['NON_EXISTENT']
        assert "No elements found" in str(excinfo.value)

    def test_get_item_multiple_found(self, concrete_dict):
        # CMD_DUP exists twice in the XML
        with pytest.raises(Exception) as excinfo:
            _ = concrete_dict['CMD_DUP']
        assert "More than one element found" in str(excinfo.value)

class TestGetAttr:
    """Tests for __getattr__ (e.g., dict.attr)"""

    def test_getattr_configured_xpath_text(self, concrete_dict):
        # 'description' is mapped to .//Description text
        assert concrete_dict.description == "A test dictionary"

    def test_getattr_configured_xpath_element(self, concrete_dict):
        # 'all_args' is mapped to .//Arg, is_text=False
        # It should return the first matching element
        arg = concrete_dict.all_args
        assert isinstance(arg, etree._Element)
        assert arg.get('name') == 'arg1'

    def test_getattr_fallback_to_root_attr(self, concrete_dict):
        # 'version' is NOT in ATTR_XPATHS, so it should look at root attributes
        assert concrete_dict.version == "1.0"

    def test_getattr_not_found_in_config(self, concrete_dict):
        # If xpath exists in config but finds nothing in XML
        # We need to temporarily modify the ATTR_XPATHS for this specific instance/class test
        # or rely on a specific test case.
        # Let's try accessing a root attribute that doesn't exist
        assert concrete_dict.non_existent_attr is None

    def test_getattr_xpath_no_elements_raises(self, concrete_dict):
        # A configured single-valued attribute that matches zero elements
        # must raise DictionaryAttributeError instead of silently returning
        # None (see #3).
        ConcreteDictionary.ATTR_XPATHS['broken'] = ('.//NonExistentTag', True, None)

        with pytest.raises(DictionaryAttributeError):
            concrete_dict.broken

    def test_getattr_xpath_no_elements_is_attribute_error(self, concrete_dict):
        # DictionaryAttributeError must subclass AttributeError so hasattr()
        # and getattr(obj, name, default) remain valid escape hatches.
        ConcreteDictionary.ATTR_XPATHS['broken'] = ('.//NonExistentTag', True, None)

        assert hasattr(concrete_dict, 'broken') is False
        assert getattr(concrete_dict, 'broken', 'default') == 'default'

    def test_getattr_return_list_no_elements_returns_empty_list(self, concrete_dict):
        # A configured list-valued attribute (return_list=True) that matches
        # zero elements should still return [], not raise.
        ConcreteDictionary.ATTR_XPATHS['broken_list'] = ('.//NonExistentTag', True, None, True)

        assert concrete_dict.broken_list == []

class TestIteration:
    """Tests for __iter__"""

    def test_iter_yields_wrappers(self, concrete_dict):
        items = list(concrete_dict)
        # We expect 4 commands total in the sample XML (CMD_A, CMD_B, and 2x CMD_DUP)
        assert len(items) == 4
        assert all(isinstance(x, CommandWrapper) for x in items)
        
        stems = [x.stem for x in items]
        assert "CMD_A" in stems
        assert "CMD_B" in stems

class TestXPathHelper:
    def test_xpath_method(self, concrete_dict):
        # Testing the wrapper method .xpath()
        results = concrete_dict.xpath('.//Command')
        assert len(results) == 4
        assert isinstance(results[0], etree._Element)