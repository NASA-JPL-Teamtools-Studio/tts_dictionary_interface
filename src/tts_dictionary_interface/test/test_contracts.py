import sys
import pytest
from unittest.mock import MagicMock

sys.modules['tts_utilities'] = MagicMock()
sys.modules['tts_utilities.logger'] = MagicMock()

from lxml import etree

from tts_dictionary_interface.base import SemanticDictionary
from tts_dictionary_interface.contracts import (
    ChannelContract,
    CommandContract,
    ArgumentContract,
    EvrContract,
)

pytestmark = pytest.mark.unreviewed_ai


@pytest.fixture
def channel_xml():
    return etree.fromstring(
        b'<telemetry abbreviation="ABC-0001" name="BATTERY_VOLTAGE" type="float">'
        b'<categories><ops_category>EPS</ops_category></categories>'
        b'</telemetry>'
    )


class CompleteChannel(SemanticDictionary, ChannelContract):
    ATTR_XPATHS = {
        'channel_id': ('@abbreviation', False, None),
        'channel_name': ('@name', False, None),
        'opscat': ('categories/ops_category', True, None),
        'type': ('@type', False, None),
    }


class IncompleteChannel(SemanticDictionary, ChannelContract):
    # Deliberately missing 'type' configuration.
    ATTR_XPATHS = {
        'channel_id': ('@abbreviation', False, None),
        'channel_name': ('@name', False, None),
        'opscat': ('categories/ops_category', True, None),
    }


def test_complete_channel_satisfies_contract(channel_xml):
    chan = CompleteChannel(channel_xml)
    assert chan.channel_id == 'ABC-0001'
    assert chan.channel_name == 'BATTERY_VOLTAGE'
    assert chan.opscat == 'EPS'
    assert chan.type == 'float'


def test_complete_channel_optional_attrs_default_to_none(channel_xml):
    chan = CompleteChannel(channel_xml)
    assert chan.module is None
    assert chan.measurement_id is None


def test_incomplete_channel_raises_only_for_missing_attr(channel_xml):
    chan = IncompleteChannel(channel_xml)

    # Implemented attributes still resolve normally.
    assert chan.channel_id == 'ABC-0001'
    assert chan.opscat == 'EPS'

    # The unimplemented required attribute raises NotImplementedError,
    # not at class definition/instantiation time, but only on access.
    with pytest.raises(NotImplementedError):
        chan.type


def test_incomplete_channel_class_definition_does_not_raise():
    # Defining and instantiating IncompleteChannel must not raise, even
    # though it's missing a required contract attribute.
    chan = IncompleteChannel(
        etree.fromstring(b'<telemetry abbreviation="X" name="Y"/>')
    )
    assert chan is not None


class MinimalArgument(ArgumentContract):
    def __init__(self, name, length):
        self._name = name
        self._length = length

    @property
    def name(self):
        return self._name

    @property
    def length(self):
        return self._length


def test_argument_contract_optional_attrs_default_to_none():
    arg = MinimalArgument('vcdu_number', 8)
    assert arg.name == 'vcdu_number'
    assert arg.length == 8
    assert arg.units is None
    assert arg.min is None
    assert arg.max is None


class MinimalCommand(CommandContract):
    @property
    def stem(self):
        return 'NO_OP'

    @property
    def opcode(self):
        return '0x0001'

    @property
    def opscat(self):
        return 'CORE'

    @property
    def args(self):
        return []


def test_command_contract_real_property_overrides_win():
    cmd = MinimalCommand()
    assert cmd.stem == 'NO_OP'
    assert cmd.opcode == '0x0001'
    assert cmd.opscat == 'CORE'
    assert cmd.args == []


class MinimalEvr(EvrContract):
    @property
    def name(self):
        return 'EVR_1'

    @property
    def message(self):
        return 'The first evr'

    @property
    def severity(self):
        return None  # e.g. AIT, which has no native severity concept


def test_evr_contract_allows_concrete_class_to_return_none_severity():
    evr = MinimalEvr()
    assert evr.name == 'EVR_1'
    assert evr.message == 'The first evr'
    assert evr.severity is None


class IncompleteEvr(EvrContract):
    @property
    def name(self):
        return 'EVR_1'
    # message and severity deliberately unimplemented


def test_incomplete_evr_raises_only_for_missing_attrs():
    evr = IncompleteEvr()
    assert evr.name == 'EVR_1'
    with pytest.raises(NotImplementedError):
        evr.message
    with pytest.raises(NotImplementedError):
        evr.severity
