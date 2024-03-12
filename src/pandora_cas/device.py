__all__ = ("PandoraOnlineDevice", "DEFAULT_CONTROL_TIMEOUT")

import asyncio
import logging
from types import MappingProxyType
from typing import Mapping, Any, Final, TYPE_CHECKING

import attr

from pandora_cas.data import CurrentState, TrackingPoint, TrackingEvent
from pandora_cas.enums import CommandID, Features
from pandora_cas.errors import PandoraOnlineException

if TYPE_CHECKING:
    from pandora_cas.account import PandoraOnlineAccount

_LOGGER: Final = logging.getLogger(__name__)

DEFAULT_CONTROL_TIMEOUT: Final = 30.0


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
        *,
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
        self._current_state = current_state
        self._last_point: TrackingPoint | None = None
        self._last_event: TrackingEvent | None = None
        self._utc_offset = utc_offset

        # Control timeout setting
        self.control_timeout = control_timeout

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

            self._current_state = attr.evolve(current_state, **evolve_args)

        self._last_point = value

    @property
    def last_event(self) -> TrackingEvent | None:
        return self._last_event

    @last_event.setter
    def last_event(self, value: TrackingEvent | None) -> None:
        self._last_event = value

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
            timestamp_from, timestamp_to, limit
        )

    # Remote command execution section
    async def async_remote_command(
        self,
        command_id: int | CommandID,
        ensure_complete: bool = True,
        params: Mapping[str, Any] | None = None,
    ):
        """Proxy method to execute commands on corresponding vehicle object"""
        if self._current_state is None:
            raise PandoraOnlineException("state update is required")

        if self.control_busy:
            raise PandoraOnlineException("device is busy executing command")

        if ensure_complete:
            self._control_future = asyncio.Future()

        await self._account.async_remote_command(self.device_id, command_id, params)

        if ensure_complete:
            self.logger.debug(
                f"Ensuring command {command_id} completion "
                f"(timeout: {self.control_timeout})"
            )
            await asyncio.wait_for(self._control_future, self.control_timeout)
            self._control_future.result()

        self.logger.debug(f"Command {command_id} executed successfully")

    async def async_wake_up(self) -> None:
        return await self.account.async_wake_up_device(self.device_id)

    # Lock/unlock toggles
    async def async_remote_lock(self, ensure_complete: bool = True):
        return await self.async_remote_command(CommandID.LOCK, ensure_complete)

    async def async_remote_unlock(self, ensure_complete: bool = True):
        return await self.async_remote_command(CommandID.UNLOCK, ensure_complete)

    # Engine toggle
    async def async_remote_start_engine(self, ensure_complete: bool = True):
        return await self.async_remote_command(CommandID.START_ENGINE, ensure_complete)

    async def async_remote_stop_engine(self, ensure_complete: bool = True):
        return await self.async_remote_command(CommandID.STOP_ENGINE, ensure_complete)

    # Tracking toggle
    async def async_remote_enable_tracking(self, ensure_complete: bool = True):
        return await self.async_remote_command(
            CommandID.ENABLE_TRACKING, ensure_complete
        )

    async def async_remote_disable_tracking(self, ensure_complete: bool = True):
        return await self.async_remote_command(
            CommandID.DISABLE_TRACKING, ensure_complete
        )

    # Active security toggle
    async def async_enable_active_security(self, ensure_complete: bool = True):
        return await self.async_remote_command(
            CommandID.ENABLE_ACTIVE_SECURITY, ensure_complete
        )

    async def async_disable_active_security(self, ensure_complete: bool = True):
        return await self.async_remote_command(
            CommandID.DISABLE_ACTIVE_SECURITY, ensure_complete
        )

    # Coolant heater toggle
    async def async_remote_turn_on_coolant_heater(self, ensure_complete: bool = True):
        return await self.async_remote_command(
            CommandID.TURN_ON_BLOCK_HEATER, ensure_complete
        )

    async def async_remote_turn_off_coolant_heater(self, ensure_complete: bool = True):
        return await self.async_remote_command(
            CommandID.TURN_OFF_BLOCK_HEATER, ensure_complete
        )

    # External (timer_ channel toggle
    async def async_remote_turn_on_ext_channel(self, ensure_complete: bool = True):
        return await self.async_remote_command(
            CommandID.TURN_ON_EXT_CHANNEL, ensure_complete
        )

    async def async_remote_turn_off_ext_channel(self, ensure_complete: bool = True):
        return await self.async_remote_command(
            CommandID.TURN_OFF_EXT_CHANNEL, ensure_complete
        )

    # Service mode toggle
    async def async_remote_enable_service_mode(self, ensure_complete: bool = True):
        return await self.async_remote_command(
            CommandID.ENABLE_SERVICE_MODE, ensure_complete
        )

    async def async_remote_disable_service_mode(self, ensure_complete: bool = True):
        return await self.async_remote_command(
            CommandID.DISABLE_SERVICE_MODE, ensure_complete
        )

    # Various commands
    async def async_remote_trigger_horn(self, ensure_complete: bool = True):
        return await self.async_remote_command(CommandID.TRIGGER_HORN, ensure_complete)

    async def async_remote_trigger_light(self, ensure_complete: bool = True):
        return await self.async_remote_command(CommandID.TRIGGER_LIGHT, ensure_complete)

    async def async_remote_trigger_trunk(self, ensure_complete: bool = True):
        return await self.async_remote_command(CommandID.TRIGGER_TRUNK, ensure_complete)

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
        return self._attributes["firmware"]

    @property
    def voice_version(self) -> str:
        return self._attributes["voice_version"]

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
        return self._attributes.get("phone") or None

    @property
    def phone_other(self) -> str | None:
        return self._attributes.get("phone1") or None
