import json
import os

import pytest

from tts_dictionary_interface.contracts import ChannelContract, EvrContract
from tts_dictionary_interface.tree import TreeSemanticDictionary, select

pytestmark = pytest.mark.unreviewed_ai

# A deliberately generic, non-AIT-specific fixture: any dict/list-tree
# dictionary with the same rough shape (a flat list of "packets", each
# with a name and a list of "fields") should work identically.
GENERIC_DOCUMENT = [
    {
        'name': 'PACKET_A',
        'fields': [
            {'name': 'field_one', 'kind': 'U8'},
            {'name': 'field_two', 'kind': 'MSB_U16'},
        ],
    },
    {
        'name': 'PACKET_B',
        'fields': [
            {'name': 'field_three', 'kind': 'U8'},
        ],
    },
]


def test_select_self_returns_top_level_list_items():
    assert select(GENERIC_DOCUMENT, '.') == GENERIC_DOCUMENT


def test_select_descends_into_key():
    fields = select(GENERIC_DOCUMENT, '.[name="PACKET_A"]/fields')
    assert [f['name'] for f in fields] == ['field_one', 'field_two']


def test_select_filters_by_equality():
    matches = select(GENERIC_DOCUMENT, '.[name="PACKET_B"]')
    assert len(matches) == 1
    assert matches[0]['name'] == 'PACKET_B'


def test_select_flattens_nested_lists_like_ait_includes():
    nested = [[GENERIC_DOCUMENT[0]], GENERIC_DOCUMENT[1]]
    assert select(nested, '.') == GENERIC_DOCUMENT


class GenericField(TreeSemanticDictionary):
    ATTR_PATHS = {
        'name': ('.', lambda node: node['name']),
        'kind': ('.', lambda node: node['kind']),
    }


class GenericPacket(TreeSemanticDictionary):
    ATTR_PATHS = {
        'name': ('.', lambda node: node['name']),
    }
    ITEM_PATHS = ['fields']
    ITEM_HUMAN_UNIQUE_IDS = ['name']
    ITEM_CLASSES = [GenericField]


class GenericDocument(TreeSemanticDictionary):
    ITEM_PATHS = ['.']
    ITEM_HUMAN_UNIQUE_IDS = ['name']
    ITEM_CLASSES = [GenericPacket]


def test_tree_semantic_dictionary_iterates_items():
    doc = GenericDocument(GENERIC_DOCUMENT)
    names = [p.name for p in doc]
    assert names == ['PACKET_A', 'PACKET_B']


def test_tree_semantic_dictionary_getitem_by_unique_id():
    doc = GenericDocument(GENERIC_DOCUMENT)
    packet = doc['PACKET_A']
    assert packet.name == 'PACKET_A'
    assert [f.name for f in packet] == ['field_one', 'field_two']


def test_tree_semantic_dictionary_getitem_raises_key_error_when_missing():
    doc = GenericDocument(GENERIC_DOCUMENT)
    with pytest.raises(KeyError):
        doc['NOT_A_REAL_PACKET']


def test_tree_semantic_dictionary_contains():
    doc = GenericDocument(GENERIC_DOCUMENT)
    assert 'PACKET_A' in doc
    assert 'NOT_A_REAL_PACKET' not in doc


def test_tree_semantic_dictionary_len():
    doc = GenericDocument(GENERIC_DOCUMENT)
    assert len(doc) == 2


class GenericChannel(TreeSemanticDictionary, ChannelContract):
    ATTR_PATHS = {
        'channel_id': ('.', lambda node: node['name']),
        'channel_name': ('.', lambda node: node['name']),
        'opscat': ('.', lambda node: node['kind']),
        'type': ('.', lambda node: node['kind']),
    }


def test_generic_tree_class_satisfies_channel_contract():
    channel = GenericChannel(GENERIC_DOCUMENT[0]['fields'][0])
    assert isinstance(channel, ChannelContract)
    assert channel.channel_name == 'field_one'
    assert channel.module is None
    assert channel.measurement_id is None


class GenericEvr(TreeSemanticDictionary, EvrContract):
    ATTR_PATHS = {
        'name': ('.', lambda node: node['name']),
        'message': ('.', lambda node: node.get('desc')),
        'severity': ('.', lambda node: None),
    }


def test_generic_tree_class_satisfies_evr_contract():
    evr = GenericEvr({'name': 'SOME_EVENT', 'desc': 'Something happened.'})
    assert isinstance(evr, EvrContract)
    assert evr.name == 'SOME_EVENT'
    assert evr.message == 'Something happened.'
    assert evr.severity is None


class JsonTreeDocument(TreeSemanticDictionary):
    """A trivial format-specific mixin, just to test the source=path/
    version resolution machinery without depending on any real
    packaged mission dictionary."""
    DICTIONARY_FILENAME = 'doc.json'

    @classmethod
    def _load_file(cls, path):
        if os.path.isdir(path):
            path = os.path.join(path, cls.DICTIONARY_FILENAME)
        with open(path) as f:
            return json.load(f)


def test_source_none_raises_value_error():
    with pytest.raises(ValueError):
        TreeSemanticDictionary(None)


def test_source_dict_or_list_is_used_directly():
    doc = JsonTreeDocument(GENERIC_DOCUMENT)
    assert doc.node == GENERIC_DOCUMENT


def test_source_file_path_is_loaded_via_load_file(tmp_path):
    doc_path = tmp_path / 'doc.json'
    doc_path.write_text(json.dumps(GENERIC_DOCUMENT))
    doc = JsonTreeDocument(str(doc_path))
    assert doc.node == GENERIC_DOCUMENT


def test_source_directory_path_is_loaded_via_dictionary_filename(tmp_path):
    (tmp_path / JsonTreeDocument.DICTIONARY_FILENAME).write_text(json.dumps(GENERIC_DOCUMENT))
    doc = JsonTreeDocument(str(tmp_path))
    assert doc.node == GENERIC_DOCUMENT


def test_source_version_string_without_dictionary_module_raises():
    with pytest.raises(ValueError):
        JsonTreeDocument('v1')


def test_base_tree_class_without_load_file_override_rejects_path_source(tmp_path):
    doc_path = tmp_path / 'doc.json'
    doc_path.write_text(json.dumps(GENERIC_DOCUMENT))
    with pytest.raises(NotImplementedError):
        TreeSemanticDictionary(str(doc_path))
