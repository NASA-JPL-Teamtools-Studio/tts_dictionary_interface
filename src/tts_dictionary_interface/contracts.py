"""
Shared, format-agnostic attribute contracts for Command/Argument/Channel/EVR
objects, satisfied via multiple inheritance by any dictionary engine's
concrete classes (XML/AMPCS, JSON/F-Prime, YAML/AIT, ...).

Why this exists: without a shared contract, each engine's Command/Channel/EVR
classes could drift into incompatible shapes with nothing to stop it.

How "required but not yet implemented" works:

    A contract-required attribute that a concrete class doesn't actually
    implement must raise NotImplementedError -- but only when that specific
    attribute is accessed, never at class definition or instantiation time.

    For engines that implement attributes as *real* properties (e.g. a
    hand-written JSON engine), this falls out for free: Python's normal
    attribute lookup finds the concrete class's own property in its __dict__
    before it ever consults a mixin base class, so the contract's
    placeholder is simply never reached.

    For engines that resolve attributes *dynamically* (e.g. AMPCS's
    SemanticDictionary.__getattr__, which resolves attributes from
    ATTR_XPATHS at access time rather than declaring them as properties),
    there's nothing in the class's __dict__ to shadow the contract's
    placeholder property -- so the placeholder would normally win and raise
    immediately, without ever giving the dynamic resolver a chance. To avoid
    that, every contract placeholder explicitly defers to the instance's own
    __getattr__ (if it defines one) before concluding the attribute isn't
    implemented at all.
"""

_UNSET = object()


def _resolve_required(instance, name):
    """
    Resolve a contract-required attribute.

    1. If the concrete class exposes a declarative attribute-config dict
       (e.g. AMPCS's SemanticDictionary subclasses' ATTR_XPATHS, or the
       dict/list-tree analog ATTR_PATHS used by YAML/AIT-flavored
       engines) and the attribute isn't a key in it, the attribute is
       definitely not implemented -- raise NotImplementedError without
       even trying, since the dynamic __getattr__ would otherwise
       silently fall back to a raw attribute lookup and return None
       instead of signaling "unimplemented".
    2. Otherwise, if the concrete class defines a real __getattr__, try it
       explicitly.
    3. If that raises AttributeError (including DictionaryAttributeError)
       -- or there's no __getattr__ to try at all -- the attribute is not
       implemented; raise NotImplementedError.
    """
    for declarative_config_attr in ('ATTR_XPATHS', 'ATTR_PATHS'):
        config = getattr(type(instance), declarative_config_attr, None)
        if config is not None and name not in config:
            raise NotImplementedError(
                f"{type(instance).__name__} does not implement required "
                f"contract attribute '{name}'"
            )

    dynamic_getattr = getattr(type(instance), '__getattr__', None)
    if dynamic_getattr is not None:
        try:
            return dynamic_getattr(instance, name)
        except AttributeError as e:
            raise NotImplementedError(
                f"{type(instance).__name__} does not implement required "
                f"contract attribute '{name}'"
            ) from e
    raise NotImplementedError(
        f"{type(instance).__name__} does not implement required contract "
        f"attribute '{name}'"
    )


def _resolve_optional(instance, name):
    """
    Resolve a contract-optional attribute.

    Optional attributes represent concepts that some formats simply don't
    have (e.g. F-Prime has no per-channel packet ID). Unlike required
    attributes, an unimplemented optional attribute is not an error -- it
    just resolves to None.
    """
    dynamic_getattr = getattr(type(instance), '__getattr__', None)
    if dynamic_getattr is None:
        return None
    try:
        return dynamic_getattr(instance, name)
    except AttributeError:
        return None


class ArgumentContract:
    """
    Contract for a single Command argument.

    Required: name, length.
    Optional: units, min, max -- some argument types (enumerated, string,
    repeat-block arguments) have no native concept of engineering units or
    numeric range; those resolve to None rather than raising.
    """

    @property
    def name(self):
        """Return the argument name."""
        return _resolve_required(self, 'name')

    @property
    def length(self):
        """Return the argument length."""
        return _resolve_required(self, 'length')

    @property
    def units(self):
        """Return the argument units if defined."""
        return _resolve_optional(self, 'units')

    @property
    def min(self):
        """Return the minimum value if defined."""
        return _resolve_optional(self, 'min')

    @property
    def max(self):
        """Return the maximum value if defined."""
        return _resolve_optional(self, 'max')


class CommandContract:
    """
    Contract for a single Command definition.

    Required: stem (also usable as the dictionary's __getitem__ key),
    opcode, opscat, args (an iterable of ArgumentContract-satisfying
    objects).
    """

    @property
    def stem(self):
        """Return the command stem."""
        return _resolve_required(self, 'stem')

    @property
    def opcode(self):
        """Return the command opcode."""
        return _resolve_required(self, 'opcode')

    @property
    def opscat(self):
        """Return the command opscat."""
        return _resolve_required(self, 'opscat')

    @property
    def args(self):
        """Return the command arguments."""
        return _resolve_required(self, 'args')


class ChannelContract:
    """
    Contract for a single Channel (telemetry point) definition.

    Required: channel_id and/or channel_name (either usable as the
    dictionary's __getitem__ key), opscat, type.
    Optional: module, measurement_id -- not every format has a distinct
    module concept separate from opscat (F-Prime, AIT), or a per-channel
    packet/measurement ID (F-Prime); those resolve to None rather than
    raising.
    """

    @property
    def channel_id(self):
        """Return the channel ID."""
        return _resolve_required(self, 'channel_id')

    @property
    def channel_name(self):
        """Return the channel name."""
        return _resolve_required(self, 'channel_name')

    @property
    def opscat(self):
        """Return the channel opscat."""
        return _resolve_required(self, 'opscat')

    @property
    def type(self):
        """Return the channel type."""
        return _resolve_required(self, 'type')

    @property
    def module(self):
        """Return the channel module if defined."""
        return _resolve_optional(self, 'module')

    @property
    def measurement_id(self):
        """Return the measurement ID if defined."""
        return _resolve_optional(self, 'measurement_id')


class EvrContract:
    """
    Contract for a single EVR (event record) definition.

    Required: name, message, severity.

    severity is required at the contract level even though some formats
    (AIT) have no native severity concept at all -- severity is too
    important a concept on missions that do use it to quietly downgrade
    contract-wide. Formats without it are expected to explicitly implement
    `severity` returning None and document that as a known limitation,
    rather than being contractually exempted from having it.

    message returns the raw, unformatted template string for every format
    -- no parameter substitution against live telemetry values.
    """

    @property
    def name(self):
        """Return the EVR name."""
        return _resolve_required(self, 'name')

    @property
    def message(self):
        """Return the EVR message template."""
        return _resolve_required(self, 'message')

    @property
    def severity(self):
        """Return the EVR severity."""
        return _resolve_required(self, 'severity')
