__all__ = (
    "Balance",
    "FuelTank",
    "CurrentState",
    "LiquidSensor",
    "TrackingEvent",
    "TrackingPoint",
    "WsTrack",
    "WsTrackPoint",
)

import logging
from abc import ABC
from collections import ChainMap
from time import time
from types import MappingProxyType
from typing import (
    Mapping,
    Any,
    TypeVar,
    SupportsFloat,
    SupportsInt,
    MutableMapping,
    Final,
    Callable,
    Sequence,
    SupportsRound,
)

import attr

from pandora_cas.enums import PrimaryEventID, BitStatus

_LOGGER: Final = logging.getLogger(__name__)

_T = TypeVar("_T")
_TKwargs = TypeVar("_TKwargs", bound=MutableMapping[str, Any])
_S: Final = "source_value_identifier"
_A: Final = "timestamp_source_attribute"
_TFieldName = str | tuple[str, ...]

DEFAULT_TIMESTAMP_SOURCE: Final = "state_timestamp_utc"
IGNORED_ATTRIBUTES: Final[dict[type["_BaseGetDictArgs"], set[str]]] = {}


@attr.s(kw_only=True, frozen=True, slots=True)
class _BaseGetDictArgs(attr.AttrsInstance, ABC):
    @classmethod
    def get_dict_args(cls, data: Mapping[str, Any], **kwargs) -> _TKwargs:
        all_keys = set(data.keys())
        name = cls.__name__
        # noinspection PyTypeChecker
        for attrib in attr.fields(cls):
            try:
                keys = attrib.metadata[_S]
            except KeyError:
                continue
            all_keys.difference_update(keys)
            init_name = attrib.alias
            if init_name in kwargs:
                continue
            for key in keys:
                if key in data:
                    kwargs[init_name] = data[key]
                    break

        if all_keys:
            if cls in IGNORED_ATTRIBUTES:
                # noinspection PyTypeChecker
                all_keys.difference_update(IGNORED_ATTRIBUTES[cls])
            if all_keys:
                _LOGGER.info(
                    f"[{name}] New attributes detected! Please, report this to the developer."
                )
                # noinspection PyTypeChecker
                for key in sorted(all_keys, key=str.lower):
                    _LOGGER.info(
                        f"[{name}]  {key} ({type(data[key])}) = {repr(data[key])}"
                    )

        return kwargs

    @classmethod
    def from_dict(cls, data: Mapping[str, Any], **kwargs):
        kwargs.update(cls.get_dict_args(data, **kwargs))
        # noinspection PyArgumentList
        return cls(**kwargs)

    @classmethod
    def conv(cls, x: Any):
        return x if isinstance(x, cls) else cls.from_dict(x)


# noinspection PyTypeHints
def field(
    field_name: _TFieldName,
    converter: Callable[[Any], Any] | None = None,
    timestamp_source: str | None = DEFAULT_TIMESTAMP_SOURCE,
    **kwargs,
):
    if isinstance(field_name, str):
        field_name = (field_name,)
    return attr.field(
        metadata={_S: field_name, _A: timestamp_source},
        converter=converter,
        **kwargs,
    )


# noinspection PyTypeHints
def field_opt(
    field_name: _TFieldName,
    converter: type[_BaseGetDictArgs] | Callable[[Any], Any] | None = None,
    timestamp_source: str | None = DEFAULT_TIMESTAMP_SOURCE,
    **kwargs,
):
    kwargs.setdefault("default", None)
    if isinstance(converter, type) and issubclass(converter, _BaseGetDictArgs):
        # kwargs.setdefault("type", Sequence[converter])
        converter = converter.conv
    if converter is not None:
        kwargs["converter"] = lambda x: kwargs["default"] if x is None else converter(x)
    kwargs["timestamp_source"] = timestamp_source
    return field(field_name, **kwargs)


def field_list(
    field_name: _TFieldName,
    converter: type[_BaseGetDictArgs] | Callable[[Any], Any] | None = None,
    timestamp_source: str | None = DEFAULT_TIMESTAMP_SOURCE,
    **kwargs,
):
    kwargs.setdefault("default", ())
    if isinstance(converter, type) and issubclass(converter, _BaseGetDictArgs):
        # kwargs.setdefault("type", Sequence[converter])
        converter = converter.conv
    if converter is not None:
        kwargs["converter"] = lambda x: tuple(map(converter, x))
    kwargs["timestamp_source"] = timestamp_source
    return field(field_name, **kwargs)


def field_emp(
    field_name: _TFieldName,
    converter: type[_BaseGetDictArgs] | Callable[[Any], Any] | None = None,
    timestamp_source: str | None = DEFAULT_TIMESTAMP_SOURCE,
    **kwargs,
):
    kwargs.setdefault("default", None)
    if isinstance(converter, type) and issubclass(converter, _BaseGetDictArgs):
        # kwargs.setdefault("type", Sequence[converter])
        converter = converter.conv
    if converter is not None:
        kwargs["converter"] = lambda x: converter(x) if x else None
    kwargs["timestamp_source"] = timestamp_source
    return field(field_name, **kwargs)


def bool_or_none(x: Any) -> bool | None:
    return None if x is None else bool(x)


def field_bool(
    field_name: _TFieldName,
    timestamp_source: str | None = DEFAULT_TIMESTAMP_SOURCE,
    **kwargs,
):
    return field_opt(field_name, bool_or_none, timestamp_source, **kwargs)


def int_or_none(x: SupportsInt | None) -> int | None:
    try:
        return None if x is None else int(x)
    except (TypeError, ValueError):
        _LOGGER.warning(f"Could not convert value '{x}' to int, returning None")
        return None


def field_int(
    field_name: _TFieldName,
    timestamp_source: str | None = DEFAULT_TIMESTAMP_SOURCE,
    **kwargs,
):
    return field_opt(field_name, int_or_none, timestamp_source, **kwargs)


def float_or_none(x: SupportsFloat | None) -> float | None:
    try:
        return None if x is None else float(x)
    except (TypeError, ValueError):
        _LOGGER.warning(f"Could not convert value '{x}' to float, returning None")
        return None


def field_float(
    field_name: _TFieldName,
    timestamp_source: str | None = DEFAULT_TIMESTAMP_SOURCE,
    **kwargs,
):
    return field_opt(field_name, float_or_none, timestamp_source, **kwargs)


@attr.s(kw_only=True, frozen=True, slots=True)
class _FloatValue(_BaseGetDictArgs, SupportsInt, SupportsFloat, SupportsRound, ABC):
    value: float | None = field_float("value")

    def __float__(self) -> float:
        return float(self.value)

    def __int__(self) -> int:
        return int(self.value)

    def __round__(self, __ndigits: int | None = None):
        return round(self.value, __ndigits)


@attr.s(kw_only=True, frozen=True, slots=True)
class Balance(_FloatValue):
    currency: str | None = field_emp("cur")


@attr.s(kw_only=True, frozen=True, slots=True)
class FuelTank(_FloatValue):
    id: int = field("id", int, default=0)
    ras: float | None = field_float("")
    ras_t: float | None = field_float("")


IGNORED_ATTRIBUTES[FuelTank] = {"m", "ras", "ras_a", "ras_t", "ras_z", "val"}


def _degrees_to_direction(degrees: float):
    sides = (
        "N",
        "NNE",
        "NE",
        "ENE",
        "E",
        "ESE",
        "SE",
        "SSE",
        "S",
        "SSW",
        "SW",
        "WSW",
        "W",
        "WNW",
        "NW",
        "NNW",
    )
    return sides[round(degrees / (360 / len(sides))) % len(sides)]


@attr.s(kw_only=True, frozen=True, slots=True)
class SimCard(_BaseGetDictArgs):
    phone: str = field("phoneNumber")
    is_active: bool = field("isActive", bool)
    balance: Balance | None = field_emp("balance", Balance)


@attr.s(kw_only=True, frozen=True, slots=True)
class LiquidSensor(_BaseGetDictArgs):
    identifier: int = field("num", int)
    level: float | None = field_float("level")
    temperature: float | None = field_float("temp")
    unit: int | None = field_int("unit")
    voltage: float | None = field_float("voltage")

    @property
    def is_percentage(self) -> bool:
        return self.unit == 1

    @property
    def is_liters(self) -> bool:
        return self.unit == 2


def lock_lat_lng_conv(x: Any):
    return float(x) / 1000000


@attr.s(kw_only=True, frozen=True, slots=True)
class WsTrackPoint(_BaseGetDictArgs):
    timestamp: int = field("dtime", int)
    latitude: float = field("x", float)
    longitude: float = field("y", float)
    fuel: int | None = field_int("fuel")
    speed: int | None = field_int("speed")
    flags: int | None = field_int("flags")


@attr.s(kw_only=True, frozen=True, slots=True)
class WsTrack(_BaseGetDictArgs):
    track_id: int = field("id", int)
    length: float = field("length", float)
    speed: int = field("speed", int)
    points: Sequence[WsTrackPoint] = field_list("points", WsTrackPoint)


# noinspection SpellCheckingInspection
@attr.s(kw_only=True, frozen=True, slots=True)
class CurrentState(_BaseGetDictArgs):
    identifier: int = field(("dev_id", "id"), int, None)

    active_sim: int | None = field_int("active_sim")
    balance: Balance | None = field_emp("balance", Balance)
    balance_other: Balance | None = field_emp("balance1", Balance)
    bit_state: BitStatus | None = field_opt("bit_state_1", lambda x: BitStatus(int(x)))
    can_mileage: float | None = field_float("mileage_CAN")
    engine_rpm: int | None = field_int("engine_rpm")
    engine_temperature: float | None = field_float("engine_temp")
    exterior_temperature: float | None = field_float("out_temp")
    fuel: float | None = field_float("fuel")
    gsm_level: int | None = field_int("gsm_level")
    imei: int | None = field_int("")
    interior_temperature: float | None = field_float("cabin_temp")
    is_evacuating: bool | None = field_bool("evaq")
    is_moving: bool | None = field_bool("move")
    is_online: bool | None = field_bool("online_mode", None)
    key_number: int | None = field_int("brelok")
    latitude: float | None = field_float("x")
    lock_latitude: float | None = field_opt("lock_x", lock_lat_lng_conv)
    lock_longitude: float | None = field_opt("lock_y", lock_lat_lng_conv)
    longitude: float | None = field_float("y")
    mileage: float | None = field_float("mileage")
    phone: str | None = field_emp("phone")
    phone_other: str | None = field_emp("phone1")
    relay: int | None = field_int("relay")
    rotation: float | None = field_float("rot")
    speed: float | None = field_float("speed")
    tag_number: int | None = field_int("metka")
    tracking_remaining: float | None = field_float("track_remains")
    voltage: float | None = field_float("voltage")
    internal_voltage: float | None = field_float("internal_power")
    gear: str | None = field_emp("gear")
    battery_warm_up: bool | None = field_bool("battery_warm_up")
    lbs_coords: bool | None = field_bool("Lbs_coords")

    can_belt_back_center: bool | None = field_bool("CAN_back_center_belt")
    can_belt_back_left: bool | None = field_bool("CAN_back_left_belt")
    can_belt_back_right: bool | None = field_bool("CAN_back_right_belt")
    can_belt_driver: bool | None = field_bool("CAN_driver_belt")
    can_belt_passenger: bool | None = field_bool("CAN_passenger_belt")

    can_glass_back_left: bool | None = field_bool("CAN_back_left_glass")
    can_glass_back_right: bool | None = field_bool("CAN_back_right_glass")
    can_glass_driver: bool | None = field_bool("CAN_driver_glass")
    can_glass_passenger: bool | None = field_bool("CAN_passenger_glass")

    can_tpms_back_left: float | None = field_float("CAN_TMPS_forvard_left")
    can_tpms_back_right: float | None = field_float("CAN_TMPS_forvard_right")
    can_tpms_front_left: float | None = field_float("CAN_TMPS_back_left")
    can_tpms_front_right: float | None = field_float("CAN_TMPS_back_right")
    can_tpms_reserve: float | None = field_float("CAN_TMPS_reserve")

    climate_firmware: int | None = field_int("fw_climate")
    can_climate: bool | None = field_bool("CAN_climate")
    can_climate_ac: bool | None = field_bool("CAN_climate_ac")
    can_climate_defroster: bool | None = field_bool("CAN_climate_defroster")
    can_climate_evb_heat: bool | None = field_bool("CAN_climate_evb_heat")
    can_climate_glass_heat: bool | None = field_bool("CAN_climate_glass_heat")
    can_climate_seat_heat_level: int | None = field_int("CAN_climate_seat_heat_lvl")
    can_climate_seat_vent_level: int | None = field_int("CAN_climate_seat_vent_lvl")
    can_climate_steering_heat: bool | None = field_bool("CAN_climate_steering_heat")
    can_climate_temperature: int | None = field_int("CAN_climate_temp")

    heater_errors: Sequence[int] = field_list("heater_errors", int)
    heater_flame: bool | None = field_bool("heater_flame")
    heater_power: bool | None = field_bool("heater_power")
    heater_temperature: float | None = field_float("heater_temperature")
    heater_voltage: float | None = field_float("heater_voltage")

    can_average_speed: float | None = field_float("CAN_average_speed")
    can_consumption: float | None = field_float("CAN_consumption")
    can_consumption_after: float | None = field_float("CAN_consumption_after")
    can_days_to_maintenance: int | None = field_int("CAN_days_to_maintenance")
    can_low_liquid: bool | None = field_bool("CAN_low_liquid")
    can_mileage_by_battery: float | None = field_float("CAN_mileage_by_battery")
    can_mileage_to_empty: float | None = field_float("CAN_mileage_to_empty")
    can_mileage_to_maintenance: float | None = field_float("CAN_mileage_to_maintenance")
    can_need_pads_exchange: bool | None = field_bool("CAN_need_pads_exchange")
    can_seat_taken: bool | None = field_bool("CAN_seat_taken")

    ev_state_of_charge: float | None = field_float("SOC")
    ev_state_of_health: float | None = field_float("SOH")
    ev_charging_connected: bool | None = field_bool("charging_connect")
    ev_charging_slow: bool | None = field_bool("charging_slow")
    ev_charging_fast: bool | None = field_bool("charging_fast")
    ev_status_ready: bool | None = field_bool("ev_status_ready")
    battery_temperature: int | None = field_int("battery_temperature")

    # undecoded parameters
    # smeter: int | None = field_int("smeter")
    # tconsum: int | None = field_int("tconsum")
    # loadaxis: Any = attr.ib(default=None, metadata={_S: "loadaxis"})
    # land: int | None = field_int("land")
    liquid_sensors: Sequence[LiquidSensor] = field_list("liquid_sensor", LiquidSensor)
    bunker: int | None = field_int("bunker")
    ex_status: int | None = field_int("ex_status")
    fuel_tanks: Sequence[FuelTank] = field_list("tanks", FuelTank)
    sims: Sequence[SimCard] = field_list("sims", SimCard)

    state_timestamp: int | None = field_int("state", None)
    state_timestamp_utc: int | None = field_int("state_utc", None)
    online_timestamp: int | None = field_int("online", None)
    online_timestamp_utc: int | None = field_int("online_utc", None)
    settings_timestamp_utc: int | None = field_int("setting_utc", None)
    command_timestamp_utc: int | None = field_int("command_utc", None)
    track: WsTrack | None = field_emp("track", WsTrack)

    _last_updated: dict[str, int] = attr.ib(factory=dict, converter=lambda x: dict(x))

    def __attrs_post_init__(self):
        last_updated = {}
        for a in attr.fields(self.__class__):
            if (timestamp_key := a.metadata.get(_A)) is None:
                continue
            last_updated[a.name] = getattr(self, timestamp_key, None) or -1
        object.__setattr__(self, "_last_updated", last_updated)

    @property
    def last_updated(self) -> Mapping[str, int]:
        return MappingProxyType(self._last_updated)

    @property
    def direction(self) -> str:
        """Textual interpretation of rotation."""
        return _degrees_to_direction(self.rotation or 0.0)

    @classmethod
    def get_ws_state_args(cls, data: Mapping[str, Any], **kwargs) -> _TKwargs:
        return cls.get_dict_args(data, **kwargs)

    @classmethod
    def get_http_state_args(cls, data: Mapping[str, Any], **kwargs) -> _TKwargs:
        if can := data.get("can"):
            # noinspection PyTypeChecker
            data = ChainMap(can, data)
        return cls.get_dict_args(data, **kwargs)

    @classmethod
    def get_ws_point_args(cls, data: Mapping[str, Any], **kwargs) -> dict[str, Any]:
        return cls.get_dict_args(data, **kwargs)

    def evolve_args(self, silence_warnings: bool = True, **changes) -> dict[str, Any]:
        assert attr.has(cls := self.__class__)
        attributes = {a.alias: a for a in attr.fields(cls)}
        warn_updates_per_key = {}
        skip_updates_per_key = {}

        new_updates = {}
        last_updated = self._last_updated
        init_args = {}
        for attribute, value in changes.items():
            if attribute not in attributes:
                raise ValueError(f"Unknown attribute: {attribute}")
            timestamp_key = attributes[attribute].metadata.get(_A)
            if timestamp_key is not None:
                timestamp_value = changes.get(timestamp_key)
                if timestamp_value is None:
                    if not silence_warnings:
                        warn_updates_per_key.setdefault(timestamp_key, set()).add(
                            attribute
                        )
                elif last_updated[attribute] > timestamp_value:
                    skip_updates_per_key.setdefault(timestamp_key, set()).add(attribute)
                    continue
                else:
                    new_updates[attribute] = timestamp_value
            init_args[attribute] = value

        if warn_updates_per_key:
            for timestamp_key, attributes in warn_updates_per_key.items():
                _LOGGER.warning(
                    f"Updating attributes {', '.join(sorted(attributes))} "
                    f"without timestamp provided at {timestamp_key}"
                )
        if skip_updates_per_key:
            for timestamp_key, attributes in warn_updates_per_key.items():
                _LOGGER.debug(
                    f"Skipping attributes {', '.join(sorted(attributes))} "
                    f"update due to timestamp {timestamp_key} deviation"
                )
        if init_args:
            init_args["last_updated"] = MappingProxyType(
                {**self._last_updated, **new_updates}
            )
        return init_args

    def evolve(
        self,
        return_new_object_on_empty_data: bool = False,
        silence_warnings: bool = True,
        **changes,
    ):
        evolve_args = self.evolve_args(silence_warnings, **changes)
        return (
            attr.evolve(self, **evolve_args)
            if return_new_object_on_empty_data or evolve_args
            else self
        )


# noinspection SpellCheckingInspection
IGNORED_ATTRIBUTES[CurrentState] = {
    # Unparsed, and likely unneeded attributes
    "benish_mode",
    "cmd_code",
    "cmd_result",
    "counter1",
    "counter2",
    "engine_remains",
    "gps_ready",
    "imei",
    "land",
    # From track, supposedly
    "length",
    "max_speed",
    "timezone",
    "track_id",
    "dtime",
    "flags",
    "tconsum",
    "props",
}


@attr.s(kw_only=True, frozen=True, slots=True)
class TrackingEvent:
    identifier: int = attr.ib(metadata={_S: "identifier"})
    device_id: int = attr.ib(metadata={_S: "device_id"})
    bit_state: BitStatus = attr.ib(metadata={_S: "bit_state"})
    cabin_temperature: float = attr.ib(metadata={_S: "cabin_temperature"})
    engine_rpm: float = attr.ib(metadata={_S: "engine_rpm"})
    engine_temperature: float = attr.ib(metadata={_S: "engine_temperature"})
    event_id_primary: int = attr.ib(metadata={_S: "event_id_primary"})
    event_id_secondary: int = attr.ib(metadata={_S: "event_id_secondary"})
    fuel: int = attr.ib(metadata={_S: "fuel"})
    gsm_level: int = attr.ib(metadata={_S: "gsm_level"})
    exterior_temperature: int = attr.ib(metadata={_S: "exterior_temperature"})
    voltage: float = attr.ib(metadata={_S: "voltage"})
    latitude: float = attr.ib(metadata={_S: "latitude"})
    longitude: float = attr.ib(metadata={_S: "longitude"})
    timestamp: int = attr.ib(metadata={_S: "timestamp"})
    recorded_timestamp: int = attr.ib(metadata={_S: "recorded_timestamp"})

    @property
    def primary_event_enum(self) -> PrimaryEventID:
        return PrimaryEventID(self.event_id_primary)

    @classmethod
    def get_dict_args(cls, data: Mapping[str, Any], **kwargs):
        if "identifier" not in kwargs:
            kwargs["identifier"] = int(data["id"])
        if "device_id" not in kwargs:
            kwargs["device_id"] = int(data["dev_id"])
        if "bit_state" not in kwargs:
            kwargs["bit_state"] = BitStatus(int(data["bit_state_1"]))
        if "cabin_temperature" not in kwargs:
            kwargs["cabin_temperature"] = data["cabin_temp"]
        if "engine_rpm" not in kwargs:
            kwargs["engine_rpm"] = data["engine_rpm"]
        if "engine_temperature" not in kwargs:
            kwargs["engine_temperature"] = data["engine_temp"]
        if "event_id_primary" not in kwargs:
            kwargs["event_id_primary"] = data["eventid1"]
        if "event_id_secondary" not in kwargs:
            kwargs["event_id_secondary"] = data["eventid2"]
        if "fuel" not in kwargs:
            kwargs["fuel"] = data["fuel"]
        if "gsm_level" not in kwargs:
            kwargs["gsm_level"] = data["gsm_level"]
        if "exterior_temperature" not in kwargs:
            kwargs["exterior_temperature"] = data["out_temp"]
        if "timestamp" not in kwargs:
            try:
                timestamp = data["dtime"]
            except KeyError:
                timestamp = data["time"]
            kwargs["timestamp"] = timestamp
        if "recorded_timestamp" not in kwargs:
            kwargs["recorded_timestamp"] = data["dtime_rec"]
        if "voltage" not in kwargs:
            kwargs["voltage"] = data["voltage"]
        if "latitude" not in kwargs:
            kwargs["latitude"] = data["x"]
        if "longitude" not in kwargs:
            kwargs["longitude"] = data["y"]
        return kwargs

    @classmethod
    def from_dict(cls, data: Mapping[str, Any], **kwargs):
        return cls(**cls.get_dict_args(data, **kwargs))


@attr.s(kw_only=True, frozen=True, slots=True)
class TrackingPoint:
    device_id: int = attr.ib(metadata={_S: "device_id"})
    latitude: float = attr.ib(metadata={_S: "latitude"})
    longitude: float = attr.ib(metadata={_S: "longitude"})
    track_id: int | None = field_int("")
    timestamp: float = attr.ib(default=time, metadata={_S: "timestamp"})
    fuel: int | None = field_int("")
    speed: float | None = field_float("")
    max_speed: float | None = field_float("")
    length: float | None = field_float("")
