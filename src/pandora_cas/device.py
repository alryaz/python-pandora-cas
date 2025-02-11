__all__ = ("PandoraOnlineDevice", "DEFAULT_CONTROL_TIMEOUT")

import asyncio
import logging
from datetime import datetime
from types import MappingProxyType
from typing import Mapping, Any, Final, TYPE_CHECKING

from pandora_cas.data import CurrentState, TrackingPoint, TrackingEvent, HTTPTrack
from pandora_cas.enums import CommandID, Features
from pandora_cas.errors import PandoraOnlineException

if TYPE_CHECKING:
    from pandora_cas.account import PandoraOnlineAccount

_LOGGER: Final = logging.getLogger(__name__)

DEFAULT_CONTROL_TIMEOUT: Final = 30.0


def _max_none(args):
    try:
        return max(a for a in args if a is not None)
    except TypeError:
        return None


class PandoraOnlineDevice:
    """Models state and remote services of one vehicle.

    :param account: ConnectedDrive account this vehicle belongs to
    :param attributes: attributes of the vehicle as provided by the server
    """

    def __init__(
        self,
        account: "PandoraOnlineAccount",
        attributes: Mapping[str, Any],
        current_state: CurrentState | None = None,
        control_timeout: float = DEFAULT_CONTROL_TIMEOUT,
        utc_offset: int | None = None,
        system_info: Mapping[str, Any] | None = None,
        *,
        silence_update_warnings: bool = True,
        logger: logging.Logger | logging.LoggerAdapter = _LOGGER,
    ) -> None:
        """
        Instantiate vehicle object.
        :param account:
        """
        self._account = account
        self._control_future: asyncio.Future | None = None
        self._features = None
        self._attributes = attributes
        self._system_info = system_info
        self._current_state = current_state
        self._last_point: TrackingPoint | None = None
        self._last_event: TrackingEvent | None = None
        self._utc_offset = utc_offset

        # Control timeout setting
        self.control_timeout = control_timeout

        self.silence_update_warnings = silence_update_warnings
        self.logger = logger

    def __repr__(self):
        return "<" + str(self) + ">"

    def __str__(self) -> str:
        """Use the name as identifier for the vehicle."""
        return (
            f"{self.__class__.__name__}["
            f"id={self.device_id}, "
            f'name="{self.name}", '
            f"account={self._account}, "
            f"features={self.features}"
            "]"
        )

    # State management
    @property
    def utc_offset(self) -> int:
        return self.account.utc_offset if self._utc_offset is None else self._utc_offset

    @utc_offset.setter
    def utc_offset(self, value: int | None) -> None:
        self._utc_offset = value

    @property
    def state(self) -> CurrentState | None:
        return self._current_state

    @state.setter
    def state(self, value: CurrentState) -> None:
        old_state = self._current_state

        if old_state is None:
            if self.control_busy:
                self._control_future.set_result(True)
                self._control_future = None
        else:
            if (
                self.control_busy
                and old_state.command_timestamp_utc < value.command_timestamp_utc
            ):
                self._control_future.set_result(True)
                self._control_future = None

        self._current_state = value

    @property
    def last_point(self) -> TrackingPoint | None:
        return self._last_point

    @last_point.setter
    def last_point(self, value: TrackingPoint | None) -> None:
        if value is None:
            self._last_point = None
            return

        if value.device_id != self.device_id:
            raise ValueError("Point does not belong to device identifier")

        timestamp = value.timestamp
        current_state = self._current_state
        if current_state is not None and (
            timestamp is None or current_state.state_timestamp < timestamp
        ):
            evolve_args = {}

            fuel = value.fuel
            if fuel is not None:
                evolve_args["fuel"] = fuel

            speed = value.speed
            if speed is not None:
                evolve_args["speed"] = speed

            evolve_args["latitude"] = value.latitude
            evolve_args["longitude"] = value.longitude

            self._current_state = current_state.evolve(
                False, self.silence_update_warnings, **evolve_args
            )

        self._last_point = value

    @property
    def last_event(self) -> TrackingEvent | None:
        return self._last_event

    @last_event.setter
    def last_event(self, value: TrackingEvent | None) -> None:
        self._last_event = value

    def update_current_state(
        self, silence_update_warnings: bool | None = None, **state_args
    ) -> tuple[CurrentState, dict[str, Any]]:
        if silence_update_warnings is None:
            silence_update_warnings = self.silence_update_warnings
        # Extract UTC offset
        prefixes = ("online", "state")
        utc_offset = self.utc_offset
        for prefix in prefixes:
            utc = (non_utc := prefix + "_timestamp") + "_utc"
            if not (
                (non_utc_val := state_args.get(non_utc)) is None
                or (utc_val := state_args.get(utc)) is None
            ):
                utc_offset = round((non_utc_val - utc_val) / 60) * 60
                if self.utc_offset != utc_offset:
                    self.logger.debug(
                        f"Calculated UTC offset for device {self.device_id}: {utc_offset} seconds"
                    )
                    self.utc_offset = utc_offset
                break

        # Adjust for two timestamps
        for prefix in prefixes:
            utc = (non_utc := prefix + "_timestamp") + "_utc"
            if (val := state_args.get(utc)) is not None:
                if state_args.get(non_utc) is None:
                    state_args[non_utc] = val + utc_offset
            elif (val := state_args.get(non_utc)) is not None:
                state_args[utc] = val - utc_offset

        # Create new state if not present
        if self.state is None:
            self.logger.debug(f"Initializing state object")
            new_state = CurrentState(**state_args)
        elif state_args := self.state.evolve_args(
            silence_update_warnings, **state_args
        ):
            self.logger.debug(f"Updating state object")
            new_state = self.state.evolve(False, silence_update_warnings, **state_args)
        else:
            self.logger.debug(f"No attributes to update")
            return self.state, {}

        # remove last_updated attribute as quite duplicate
        state_args.pop("last_updated", None)

        self.state = new_state
        return new_state, state_args

    async def async_geocode(
        self, language: str | None = None, full: bool = False
    ) -> str | dict[str, str] | None:
        """
        Retrieve the geocoded location for the given latitude and longitude.
        :param language: Language code
        :param full: Whether to return the whole response
        :return: (Whole response) OR (Short address) OR (None if empty)
        """
        if not (state := self.state):
            raise ValueError("State is not available")
        if None in (state.latitude, state.longitude):
            raise ValueError("Both latitude and longitude are required")
        return await self.account.async_geocode(
            state.latitude, state.longitude, language, full
        )

    async def async_fetch_last_event(self) -> TrackingEvent | None:
        try:
            return next(iter(await self.async_fetch_events(0, None, 1)))
        except StopIteration:
            return None

    async def async_fetch_events(
        self,
        timestamp_from: int = 0,
        timestamp_to: int | None = None,
        limit: int = 20,
    ) -> list[TrackingEvent]:
        return await self.account.async_fetch_events(
            timestamp_from, timestamp_to, limit, self.device_id
        )

    async def async_fetch_track_data(self, track_id: int | str) -> HTTPTrack:
        return await self.account.async_fetch_track_data(self.device_id, track_id)

    async def async_update_system_info(self) -> dict[str, Any]:
        self._system_info = await self.account.async_fetch_device_system(self.device_id)
        return self._system_info

    # Remote command execution section
    async def async_remote_command(
        self,
        command_id: int | CommandID,
        params: Mapping[str, Any] | None = None,
        ensure_complete: bool = True,
    ):
        """Proxy method to execute commands on corresponding vehicle object"""
        if self._current_state is None:
            raise PandoraOnlineException("state update is required")

        if self.control_busy:
            raise PandoraOnlineException("device is busy executing command")

        control_future = None
        if ensure_complete:
            self._control_future = control_future = asyncio.Future()

        await self._account.async_remote_command(self.device_id, command_id, params)

        if ensure_complete:
            self.logger.debug(
                f"Ensuring command {command_id} completion "
                f"(timeout: {self.control_timeout})"
            )
            await asyncio.wait_for(control_future, self.control_timeout)
            control_future.result()

        self.logger.debug(f"Command {command_id} executed successfully")

    async def async_wake_up(self) -> None:
        return await self.account.async_wake_up_device(self.device_id)

    # Lock/unlock toggles
    async def async_remote_lock(self, ensure_complete: bool = True):
        return await self.async_remote_command(
            CommandID.LOCK, ensure_complete=ensure_complete
        )

    async def async_remote_unlock(self, ensure_complete: bool = True):
        return await self.async_remote_command(
            CommandID.UNLOCK, ensure_complete=ensure_complete
        )

    # Engine toggle
    async def async_remote_start_engine(self, ensure_complete: bool = True):
        return await self.async_remote_command(
            CommandID.START_ENGINE, ensure_complete=ensure_complete
        )

    async def async_remote_stop_engine(self, ensure_complete: bool = True):
        return await self.async_remote_command(
            CommandID.STOP_ENGINE, ensure_complete=ensure_complete
        )

    # Tracking toggle
    async def async_remote_enable_tracking(self, ensure_complete: bool = True):
        return await self.async_remote_command(
            CommandID.ENABLE_TRACKING, ensure_complete=ensure_complete
        )

    async def async_remote_disable_tracking(self, ensure_complete: bool = True):
        return await self.async_remote_command(
            CommandID.DISABLE_TRACKING, ensure_complete=ensure_complete
        )

    # Active security toggle
    async def async_enable_active_security(self, ensure_complete: bool = True):
        return await self.async_remote_command(
            CommandID.ENABLE_ACTIVE_SECURITY, ensure_complete=ensure_complete
        )

    async def async_disable_active_security(self, ensure_complete: bool = True):
        return await self.async_remote_command(
            CommandID.DISABLE_ACTIVE_SECURITY, ensure_complete=ensure_complete
        )

    # Block heater toggle
    async def async_remote_turn_on_block_heater(self, ensure_complete: bool = True):
        return await self.async_remote_command(
            CommandID.TURN_ON_BLOCK_HEATER, ensure_complete=ensure_complete
        )

    async def async_remote_turn_off_block_heater(self, ensure_complete: bool = True):
        return await self.async_remote_command(
            CommandID.TURN_OFF_BLOCK_HEATER, ensure_complete=ensure_complete
        )

    # External (timer_ channel toggle
    async def async_remote_turn_on_ext_channel(self, ensure_complete: bool = True):
        return await self.async_remote_command(
            CommandID.TURN_ON_EXT_CHANNEL, ensure_complete=ensure_complete
        )

    async def async_remote_turn_off_ext_channel(self, ensure_complete: bool = True):
        return await self.async_remote_command(
            CommandID.TURN_OFF_EXT_CHANNEL, ensure_complete=ensure_complete
        )

    # Service mode toggle
    async def async_remote_enable_service_mode(self, ensure_complete: bool = True):
        return await self.async_remote_command(
            CommandID.ENABLE_SERVICE_MODE, ensure_complete=ensure_complete
        )

    async def async_remote_disable_service_mode(self, ensure_complete: bool = True):
        return await self.async_remote_command(
            CommandID.DISABLE_SERVICE_MODE, ensure_complete=ensure_complete
        )

    # Various commands
    async def async_remote_trigger_horn(self, ensure_complete: bool = True):
        return await self.async_remote_command(
            CommandID.TRIGGER_HORN, ensure_complete=ensure_complete
        )

    async def async_remote_trigger_light(self, ensure_complete: bool = True):
        return await self.async_remote_command(
            CommandID.TRIGGER_LIGHT, ensure_complete=ensure_complete
        )

    async def async_remote_trigger_trunk(self, ensure_complete: bool = True):
        return await self.async_remote_command(
            CommandID.TRIGGER_TRUNK, ensure_complete=ensure_complete
        )

    # Climate commands

    @property
    def control_busy(self) -> bool:
        """Returns whether device is currently busy executing command."""
        return not (self._control_future is None or self._control_future.done())

    def release_control_lock(self, error: Any | None = None) -> None:
        if self._control_future is None:
            raise ValueError("control lock is not in effect")

        if error is None:
            self._control_future.set_result(True)
            self._control_future = None

        else:
            self._control_future.set_exception(
                PandoraOnlineException(
                    f"Error while executing command: {error}",
                )
            )
            self._control_future = None

    # External property accessors
    @property
    def account(self) -> "PandoraOnlineAccount":
        return self._account

    @property
    def device_id(self) -> int:
        return int(self._attributes["id"])

    @property
    def is_online(self) -> bool:
        """Returns whether vehicle can be deemed online"""
        current_state = self._current_state
        return current_state is not None and current_state.is_online

    # Attributes-related properties
    @property
    def system_info(self) -> Mapping[str, Any] | None:
        if (s := self._system_info) is None:
            return None
        return MappingProxyType(s)

    @system_info.setter
    def system_info(self, value: Mapping[str, Any] | None):
        self._system_info = dict(value)

    @property
    def settings_timestamp(self) -> int | None:
        if self._system_info is None:
            return None
        if not (ts := self._system_info["dtime"]):
            return None
        return int(datetime.fromisoformat(ts).timestamp())

    @property
    def vin(self) -> str | None:
        if self._system_info is None:
            return None
        if not (vin := self._system_info["vin"]):
            return None
        return vin

    @property
    def imei(self) -> str | None:
        if self._system_info is None:
            return None
        if not (imei := self._system_info["imei"]):
            return None
        return imei

    @property
    def attributes(self) -> Mapping[str, Any]:
        return MappingProxyType(self._attributes)

    @attributes.setter
    def attributes(self, value: Mapping[str, Any]):
        if int(value["id"]) != self.device_id:
            raise ValueError("device IDs must match")
        self._attributes = value
        self._features = None

    @property
    def features(self) -> Features | None:
        if self._features is None and isinstance(
            self._attributes.get("features"), Mapping
        ):
            self._features = Features.from_dict(self._attributes["features"])
        return self._features

    @property
    def type(self) -> str | None:
        return self._attributes.get("type")

    @property
    def name(self) -> str:
        """Get the name of the device."""
        return self._attributes["name"]

    @property
    def model(self) -> str:
        """Get model of the device."""
        return self._attributes["model"]

    @property
    def firmware_version(self) -> str:
        opts = [self._attributes.get("firmware")]
        if self._system_info is not None:
            opts.append(self._system_info.get("firmware"))
        return _max_none(opts)

    @property
    def voice_version(self) -> str:
        opts = [self._attributes.get("voice_version")]
        if self._system_info is not None:
            opts.append(self._system_info.get("voice"))
        return _max_none(opts)

    @property
    def color(self) -> str | None:
        return self._attributes.get("color")

    @property
    def car_type_id(self) -> int | None:
        return self._attributes.get("car_type")

    @property
    def car_type(self) -> str | None:
        car_type = self.car_type_id
        if car_type is None:
            return None
        if car_type == 1:
            return "truck"
        if car_type == 2:
            return "moto"
        return "car"

    @property
    def photo_id(self) -> str | None:
        return self._attributes.get("photo")

    @property
    def photo_url(self) -> str | None:
        photo_id = self.photo_id
        if not photo_id:
            return photo_id

        return f"/images/avatars/{photo_id}.jpg"

    @property
    def phone(self) -> str | None:
        opts = [self._attributes.get("phone")]
        if self._system_info is not None:
            opts.append(self._system_info.get("phone"))
        return _max_none(opts)

    @property
    def phone_other(self) -> str | None:
        opts = [self._attributes.get("phone1")]
        if self._system_info is not None:
            opts.append(self._system_info.get("phone1"))
        return _max_none(opts)
