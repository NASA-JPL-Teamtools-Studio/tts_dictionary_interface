from lxml import etree

from tts_dictionary_interface.base import SemanticDictionary
from tts_dictionary_interface.tree import TreeSemanticDictionary


class CachedItem(TreeSemanticDictionary):
    ATTR_PATHS = {
        'name': ('.', lambda node: node['name']),
    }


class CachedDocument(TreeSemanticDictionary):
    ITEM_PATHS = ['.']
    ITEM_HUMAN_UNIQUE_IDS = ['name']
    ITEM_CLASSES = [CachedItem]


def test_xml_contains_populates_the_same_item_cache():
    class XMLItem(SemanticDictionary):
        pass

    class XMLDocument(SemanticDictionary):
        ITEM_XPATHS = ['.//Item']
        ITEM_HUMAN_UNIQUE_IDS = ['name']
        ITEM_CLASSES = [XMLItem]

    document = XMLDocument(etree.fromstring(b'<Root><Item name="one"/></Root>'))

    assert 'one' in document
    first = document['one']
    assert document['one'] is first


def test_xml_alternate_identifier_reuses_the_wrapped_node():
    class XMLItem(SemanticDictionary):
        pass

    class XMLDocument(SemanticDictionary):
        ITEM_XPATHS = ['.//Item']
        ITEM_HUMAN_UNIQUE_IDS = ['name|opcode']
        ITEM_CLASSES = [XMLItem]

    document = XMLDocument(
        etree.fromstring(b'<Root><Item name="one" opcode="0x1"/></Root>')
    )

    first = document['one']
    assert document['0x1'] is first


def test_xml_getattr_caches_resolved_values():
    calls = []

    def count_value(value):
        calls.append(value)
        return value

    class XMLDocument(SemanticDictionary):
        ATTR_XPATHS = {
            'description': ('.//Description', True, count_value),
        }

    document = XMLDocument(
        etree.fromstring(b'<Root><Description>cached</Description></Root>')
    )

    assert document.description == 'cached'
    assert document.description == 'cached'
    assert calls == ['cached']


def test_xml_iteration_populates_getitem_cache_and_preserves_document():
    class XMLItem(SemanticDictionary):
        pass

    class XMLDocument(SemanticDictionary):
        ITEM_XPATHS = ['.//Item']
        ITEM_HUMAN_UNIQUE_IDS = ['name']
        ITEM_CLASSES = [XMLItem]

    root = etree.fromstring(
        b'<Root><Item name="one"/><Item name="two"/></Root>'
    )
    document = XMLDocument(root)

    items = list(document)

    assert len(document) == 2
    assert document['one'] is items[0]
    assert all(item.document is root for item in items)


def test_getitem_returns_the_cached_wrapped_item():
    document = CachedDocument([{'name': 'one'}])

    first = document['one']
    second = document['one']

    assert second is first


def test_contains_populates_the_same_item_cache():
    document = CachedDocument([{'name': 'one'}])

    assert 'one' in document
    first = document['one']
    assert document['one'] is first


def test_iteration_reuses_wrapped_items_and_len_is_not_lru_size():
    document = CachedDocument([{'name': str(i)} for i in range(3)])

    first_iteration = list(document)
    second_iteration = list(document)

    assert len(document) == 3
    assert second_iteration == first_iteration
    assert all(left is right for left, right in zip(first_iteration, second_iteration))

    large_document = CachedDocument([{'name': str(i)} for i in range(101)])
    list(large_document)
    assert len(large_document) == 101


def test_iteration_wraps_items_as_the_iterator_advances():
    class CountingDocument(CachedDocument):
        def __init__(self, source):
            super().__init__(source)
            self.selected = 0

        def select(self, path, filters=None):
            self.selected += 1
            return super().select(path, filters)

    document = CountingDocument([{'name': str(i)} for i in range(3)])
    iterator = iter(document)

    assert document.selected == 0
    next(iterator)
    assert document.selected == 1


def test_lru_eviction_rebuilds_the_oldest_item():
    document = CachedDocument([{'name': str(i)} for i in range(101)])

    first = document['0']
    for i in range(1, 101):
        document[str(i)]

    assert document['0'] is not first


def test_getattr_returns_the_cached_value():
    calls = []

    class CountingItem(TreeSemanticDictionary):
        ATTR_PATHS = {
            'value': ('.', lambda node: calls.append(node['value']) or node['value']),
        }

    item = CountingItem({'value': 'cached'})

    assert item.value == 'cached'
    assert item.value == 'cached'
    assert calls == ['cached']
