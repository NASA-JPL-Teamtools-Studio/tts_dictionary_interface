import json
import os

import pytest

from tts_dictionary_interface.contracts import ChannelContract, EvrContract
from tts_dictionary_interface.tree import TreeSemanticDictionary, _accepts_document_arg, select

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
    """
    No `_load_file` override at all -- exercises the base class's own
    autodetected-by-extension loading directly.
    """
    DICTIONARY_FILENAME = 'doc.json'


def test_source_none_raises_value_error():
    with pytest.raises(ValueError):
        TreeSemanticDictionary(None)


def test_source_dict_or_list_is_used_directly():
    doc = JsonTreeDocument(GENERIC_DOCUMENT)
    assert doc.node == GENERIC_DOCUMENT


def test_source_json_file_path_is_autodetected(tmp_path):
    doc_path = tmp_path / 'doc.json'
    doc_path.write_text(json.dumps(GENERIC_DOCUMENT))
    doc = JsonTreeDocument(str(doc_path))
    assert doc.node == GENERIC_DOCUMENT


def test_source_yaml_file_path_is_autodetected(tmp_path):
    doc_path = tmp_path / 'doc.yaml'
    doc_path.write_text('- name: PACKET_A\n  fields: []\n')
    doc = TreeSemanticDictionary(str(doc_path))
    assert doc.node == [{'name': 'PACKET_A', 'fields': []}]


def test_source_directory_path_is_loaded_via_dictionary_filename(tmp_path):
    (tmp_path / JsonTreeDocument.DICTIONARY_FILENAME).write_text(json.dumps(GENERIC_DOCUMENT))
    doc = JsonTreeDocument(str(tmp_path))
    assert doc.node == GENERIC_DOCUMENT


def test_source_version_string_without_dictionary_module_raises():
    with pytest.raises(ValueError):
        JsonTreeDocument('v1')


def test_source_unrecognized_extension_raises_value_error(tmp_path):
    doc_path = tmp_path / 'doc.xml'
    doc_path.write_text('<not-a-tree-format/>')
    with pytest.raises(ValueError):
        TreeSemanticDictionary(str(doc_path))


def test_directory_source_without_dictionary_filename_raises(tmp_path):
    with pytest.raises(ValueError):
        TreeSemanticDictionary(str(tmp_path))


# --- Cross-document resolution (issue #31) ---
#
# A deliberately generic, non-F-Prime-specific fixture mirroring the
# abstract shape of a "type table" / "lookup table" tree format: a flat
# list of items, each indirecting into a separate top-level lookup array
# by a ref/id key rather than embedding the full definition inline
# (F-Prime's per-field `type` -> top-level `typeDefinitions` by
# `qualifiedName` is one concrete example of this shape).
GENERIC_LOOKUP_DOCUMENT = {
    'items': [
        {'name': 'itemA', 'kindRef': 'refX'},
        {'name': 'itemB', 'kindRef': 'refY'},
    ],
    'kindDefinitions': [
        {'kindRef': 'refX', 'kindName': 'KindX', 'size': 4},
        {'kindRef': 'refY', 'kindName': 'KindY', 'size': 8},
    ],
}


class LookupItem(TreeSemanticDictionary):
    ATTR_PATHS = {
        'name': ('.', lambda node: node['name']),
        'kind_ref': ('.', lambda node: node['kindRef']),
        # A two-argument value-transform: resolves `kind_name` by
        # looking up this item's own `kindRef` against the *parent
        # document's* top-level `kindDefinitions` section -- a section
        # this item was never itself matched from.
        'kind_name': (
            '.',
            lambda node, item: select(
                item.document, f'kindDefinitions[kindRef="{node["kindRef"]}"]/kindName'
            )[0],
        ),
    }


class LookupDocument(TreeSemanticDictionary):
    ITEM_PATHS = ['items']
    ITEM_HUMAN_UNIQUE_IDS = ['name']
    ITEM_CLASSES = [LookupItem]


def test_attr_paths_callable_resolves_against_parent_document_via_getitem():
    doc = LookupDocument(GENERIC_LOOKUP_DOCUMENT)
    item = doc['itemA']
    assert item.kind_ref == 'refX'
    assert item.kind_name == 'KindX'


def test_attr_paths_callable_resolves_against_parent_document_via_iter():
    doc = LookupDocument(GENERIC_LOOKUP_DOCUMENT)
    kind_names = {p.name: p.kind_name for p in doc}
    assert kind_names == {'itemA': 'KindX', 'itemB': 'KindY'}


def test_accepts_document_arg_detects_two_positional_arg_callables():
    assert _accepts_document_arg(lambda node, item: None) is True
    assert _accepts_document_arg(lambda node: None) is False


def test_single_argument_attr_paths_callable_is_unaffected_by_document_support():
    # The pre-existing, single-argument `lambda node: ...` convention
    # must keep resolving against only the item's own node, unchanged,
    # even though every TreeSemanticDictionary instance now always has a
    # `.document`.
    class SingleArgItem(TreeSemanticDictionary):
        ATTR_PATHS = {'name': ('.', lambda node: node['name'])}

    item = SingleArgItem({'name': 'field_one'})
    assert item.name == 'field_one'
    assert item.document == item.node


def test_top_level_document_is_its_own_document_by_default():
    doc = LookupDocument(GENERIC_LOOKUP_DOCUMENT)
    assert doc.document is doc.node


def test_nested_item_document_propagates_past_its_own_item_path():
    # Nested two ITEM_PATHS levels deep (document -> packet -> field), a
    # field's `.document` must still be the *root* document, not its
    # immediate parent packet's own (much smaller) node -- proving
    # `.document` propagates all the way down regardless of nesting
    # depth, not just one level.
    nested_document = {
        'packets': [
            {
                'name': 'PACKET_A',
                'fields': [{'name': 'field_one', 'kindRef': 'refX'}],
            },
        ],
        'kindDefinitions': [
            {'kindRef': 'refX', 'kindName': 'KindX'},
        ],
    }

    class NestedField(TreeSemanticDictionary):
        ATTR_PATHS = {
            'name': ('.', lambda node: node['name']),
            'kind_name': (
                '.',
                lambda node, item: select(
                    item.document, f'kindDefinitions[kindRef="{node["kindRef"]}"]/kindName'
                )[0],
            ),
        }

    class NestedPacket(TreeSemanticDictionary):
        ATTR_PATHS = {'name': ('.', lambda node: node['name'])}
        ITEM_PATHS = ['fields']
        ITEM_HUMAN_UNIQUE_IDS = ['name']
        ITEM_CLASSES = [NestedField]

    class NestedDocument(TreeSemanticDictionary):
        ITEM_PATHS = ['packets']
        ITEM_HUMAN_UNIQUE_IDS = ['name']
        ITEM_CLASSES = [NestedPacket]

    doc = NestedDocument(nested_document)
    field = doc['PACKET_A']['field_one']
    assert field.document is doc.node
    assert field.kind_name == 'KindX'


def test_ait_yaml_dictionary_construction_is_unaffected_by_document_kwarg():
    # AitYamlDictionary and its consumers pass no `document` kwarg
    # explicitly and need no cross-document resolution -- the
    # generalized __init__ signature (and itemclass(x, document=...)
    # construction) must not break that.
    from tts_dictionary_interface.ait.loader import AitYamlDictionary

    class SimpleAitDictionary(AitYamlDictionary):
        ITEM_PATHS = ['.']
        ITEM_HUMAN_UNIQUE_IDS = ['name']
        ITEM_CLASSES = [GenericPacket]

    doc = SimpleAitDictionary(GENERIC_DOCUMENT)
    assert doc.document is doc.node
    assert [p.name for p in doc] == ['PACKET_A', 'PACKET_B']
