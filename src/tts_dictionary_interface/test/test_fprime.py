import json

import pytest

from tts_dictionary_interface.contracts import ChannelContract
from tts_dictionary_interface.fprime import FprimeJsonDictionary
from tts_dictionary_interface.tree import TreeSemanticDictionary

pytestmark = pytest.mark.unreviewed_ai

FIXTURE_DOCUMENT = {
    'telemetryChannels': [
        {'id': 1, 'name': 'deployment.componentA.channelOne', 'type': {'name': 'U8'}},
        {'id': 2, 'name': 'deployment.componentA.channelTwo', 'type': {'name': 'F32'}},
    ],
}


class Channel(TreeSemanticDictionary, ChannelContract):
    ATTR_PATHS = {
        'channel_id': ('.', lambda node: node['id']),
        'channel_name': ('.', lambda node: node['name']),
        'opscat': ('.', lambda node: node['name'].split('.')[1]),
        'type': ('.', lambda node: node['type']['name']),
    }


class ChannelDictionary(FprimeJsonDictionary):
    ITEM_PATHS = ['telemetryChannels']
    ITEM_HUMAN_UNIQUE_IDS = ['name']
    ITEM_CLASSES = [Channel]
    DICTIONARY_FILENAME = 'topology.json'


def test_source_dict_is_used_directly():
    channels = ChannelDictionary(FIXTURE_DOCUMENT)
    assert len(channels) == 2
    assert channels['deployment.componentA.channelOne'].channel_id == 1


def test_source_file_path_is_loaded_as_json(tmp_path):
    doc_path = tmp_path / 'topology.json'
    doc_path.write_text(json.dumps(FIXTURE_DOCUMENT))
    channels = ChannelDictionary(str(doc_path))
    assert len(channels) == 2


def test_source_directory_path_uses_dictionary_filename(tmp_path):
    (tmp_path / 'topology.json').write_text(json.dumps(FIXTURE_DOCUMENT))
    channels = ChannelDictionary(str(tmp_path))
    assert len(channels) == 2


def test_channel_satisfies_channel_contract():
    channels = ChannelDictionary(FIXTURE_DOCUMENT)
    channel = channels['deployment.componentA.channelTwo']
    assert isinstance(channel, ChannelContract)
    assert channel.channel_id == 2
    assert channel.opscat == 'componentA'
    assert channel.type == 'F32'
    assert channel.module is None
    assert channel.measurement_id is None
