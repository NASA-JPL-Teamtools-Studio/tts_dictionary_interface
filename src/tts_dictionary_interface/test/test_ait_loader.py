import os

from tts_dictionary_interface.ait.loader import load_yaml

FIXTURES_DIR = os.path.join(os.path.dirname(__file__), 'fixtures', 'ait_yaml')


def test_top_level_include_is_resolved():
    data = load_yaml(os.path.join(FIXTURES_DIR, 'generic_includes', 'top.yaml'))
    names = [packet['name'] for packet in _flatten(data)]
    assert 'TOP_LEVEL_PACKET' in names


def test_nested_include_resolves_relative_to_including_file_not_cwd():
    """
    mid.yaml's `!include leaf/leaf.yaml` is relative to mid.yaml's own
    directory (generic_includes/mid/), not the top-level fixture
    directory and not the process cwd -- both of which lack a `leaf/`
    subdirectory.
    """
    data = load_yaml(os.path.join(FIXTURES_DIR, 'generic_includes', 'top.yaml'))
    names = [packet['name'] for packet in _flatten(data)]
    assert 'MID_LEVEL_PACKET' in names
    assert 'LEAF_LEVEL_PACKET' in names


def test_recursive_includes_are_all_flattened_in_document_order():
    data = load_yaml(os.path.join(FIXTURES_DIR, 'generic_includes', 'top.yaml'))
    names = [packet['name'] for packet in _flatten(data)]
    assert names == ['LEAF_LEVEL_PACKET', 'MID_LEVEL_PACKET', 'TOP_LEVEL_PACKET']


def test_unknown_tags_load_as_plain_dicts_and_lists():
    data = load_yaml(os.path.join(FIXTURES_DIR, 'generic_includes', 'top.yaml'))
    packet = _flatten(data)[-1]
    assert isinstance(packet, dict)
    assert isinstance(packet['fields'], list)
    assert isinstance(packet['fields'][0], dict)


def test_demosat_flavored_includes():
    data = load_yaml(os.path.join(FIXTURES_DIR, 'demosat_includes', 'tlm.yaml'))
    names = [packet['name'] for packet in _flatten(data)]
    assert names == ['CCSDS_HEADER', 'DEMOSAT_HK']

    hk_fields = {f['name']: f for f in _flatten(data)[1]['fields']}
    assert hk_fields['battery_voltage']['units'] == 'Volts'
    assert hk_fields['heater_state']['enum'] == {0: 'OFF', 1: 'ON'}


def _flatten(nested):
    """Test helper: each `!include` splices in a list-of-packets in place
    of a single list item, and includes may nest, so the loaded document
    is arbitrarily deeply nested lists of plain packet dicts; flatten it
    fully for assertions."""
    flat = []
    for item in nested:
        if isinstance(item, list):
            flat.extend(_flatten(item))
        else:
            flat.append(item)
    return flat
