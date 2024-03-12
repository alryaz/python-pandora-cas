__all__ = ("PandoraOnlineAccount",)

import asyncio
import json
import logging
from datetime import datetime, timedelta
from time import time
from types import MappingProxyType
from typing import (
    Mapping,
    Any,
    Iterable,
    Collection,
    Callable,
    Awaitable,
    ClassVar,
    Final,
)

import aiohttp
import attr
from async_timeout import timeout

from pandora_cas.data import FuelTank, CurrentState, TrackingEvent, TrackingPoint
from pandora_cas.device import PandoraOnlineDevice
from pandora_cas.enums import CommandID, WSMessageType
from pandora_cas.errors import (
    MalformedResponseError,
    AuthenticationError,
    PandoraOnlineException,
    MissingAccessTokenError,
    SessionExpiredError,
    InvalidAccessTokenError,
)

_LOGGER: Final = logging.getLogger(__name__)


class PandoraOnlineAccount:
    """Pandora Online account interface."""

    BASE_URL: ClassVar[str] = "https://pro.p-on.ru"
    OAUTH_HEADER: ClassVar[str] = "Basic cGNvbm5lY3Q6SW5mXzRlUm05X2ZfaEhnVl9zNg=="

    def __init__(
        self,
        session: aiohttp.ClientSession,
        username: str,
        password: str,
        access_token: str | None = None,
        utc_offset: int = 0,
        *,
        logger: (
            logging.Logger | logging.LoggerAdapter | type[logging.LoggerAdapter]
        ) = _LOGGER,
    ) -> None:
        """
        Instantiate Pandora Online account object.
        :param username: Account username
        :param password: Account password
        :param access_token: Access token (optional)
        """
        if utc_offset is None:
            from calendar import timegm
            from time import mktime, localtime, gmtime

            utc_offset = timegm(t := localtime()) - timegm(gmtime(mktime(t)))

        if not (-86400 < utc_offset < 86400):
            raise ValueError("utc offset cannot be greater than 24 hours")

        self._utc_offset = utc_offset
        self._username = username
        self._password = password
        self.access_token = access_token
        self._user_id: int | None = None
        self._session = session

        #: last update timestamp
        self._last_update = -1

        #: list of vehicles associated with this account.
        self._devices: dict[int, PandoraOnlineDevice] = {}

        if isinstance(logger, type):
            logger = logger(_LOGGER)
        self.logger = logger

    def __repr__(self):
        """Retrieve representation of account object"""
        return f"<{self}>"

    def __str__(self):
        return (
            f"{self.__class__.__name__}["
            f'username="{self.username}", '
            f"user_id={self.user_id}"
            f"]"
        )

    # Basic properties
    @property
    def utc_offset(self) -> int:
        return self._utc_offset

    @property
    def user_id(self) -> int | None:
        return self._user_id

    @property
    def username(self) -> str:
        """Username accessor."""
        return self._username

    @property
    def last_update(self) -> int:
        return self._last_update

    @property
    def devices(self) -> Mapping[int, "PandoraOnlineDevice"]:
        """Devices (immutable) accessor."""
        return MappingProxyType(self._devices)

    # Requests
    @staticmethod
    async def _handle_json_response(response: aiohttp.ClientResponse) -> Any:
        """
        Process aiohttp response into data decoded from JSON.

        :param response: aiohttp.ClientResponse object.
        :return: Decoded JSON data.
        :raises PandoraOnlineException: Bad status, but server described it.
        :raises MalformedResponseError: When bad JSON message encountered.
        :raises aiohttp.ClientResponseError: When unexpected response status.
        """
        given_exc, data = None, None
        try:
            data = await response.json(content_type=None)
        except json.JSONDecodeError as e:
            given_exc = MalformedResponseError("bad JSON encoding")
            given_exc.__cause__ = e
            given_exc.__context__ = e
        # else:
        #     # When making a pull request, make sure not to remove this section.
        #     _LOGGER.debug(f"{response.method} {response.url.path} < {data}")

        try:
            status = (
                data.get("error_text")
                or data.get("status")
                or data.get("action_result")
            )
        except AttributeError:
            status = None

        if 400 <= response.status <= 403:
            raise AuthenticationError(status or "unknown auth error")

        try:
            # Raise for status at this point
            response.raise_for_status()
        except aiohttp.ClientResponseError as exc:
            if status is not None:
                raise PandoraOnlineException(status) from exc
            raise

        # Raise exception for encoding if presented previously
        if given_exc:
            raise given_exc

        # Return data ready for consumption
        return data

    @staticmethod
    async def _handle_dict_response(response: aiohttp.ClientResponse) -> dict:
        """Process aiohttp response into a dictionary decoded from JSON."""
        data = await PandoraOnlineAccount._handle_json_response(response)
        if not isinstance(data, dict):
            raise MalformedResponseError("response is not a mapping")
        return data

    @staticmethod
    async def _handle_list_response(response: aiohttp.ClientResponse) -> list:
        """Process aiohttp response into a list decoded from JSON."""
        data = await PandoraOnlineAccount._handle_json_response(response)
        if not isinstance(data, list):
            raise MalformedResponseError("response is not a list")
        return data

    async def async_check_access_token(self, access_token: str | None = None) -> None:
        """
        Validate access token against API.

        :param access_token: Check given access token. When none provided,
                             current access token is checked.
        :raises MalformedResponseError: Response payload is malformed.
        :raises MissingAccessTokenError: No token is provided or present.
        :raises SessionExpiredError: Token expired or never authed.
        :raises InvalidAccessTokenError: Malformed token is provided.
        :raises AuthenticationException: All other auth-related errors.
        """

        # Extrapolate access token to use within request
        if not (access_token or (access_token := self.access_token)):
            raise MissingAccessTokenError("access token not available")

        # Perform request
        async with self._session.post(
            self.BASE_URL + "/api/iamalive",
            data={"access_token": access_token},
        ) as request:
            # Accept all successful requests, do not check payload
            if request.status == 200:
                return

            # Decode payload for errors
            try:
                response = await request.json(content_type=None)
            except json.JSONDecodeError as e:
                self.logger.error(
                    f"Malformed access token checking "
                    f"response: {await response.text()}",
                    exc_info=e,
                )
                raise MalformedResponseError("Malformed checking response")

        self.logger.debug(f"Received error for access token check: {response}")

        # Extract status code (description) from payload
        try:
            status = response["status"]
        except (AttributeError, LookupError):
            raise AuthenticationError("error contains no status")

        # Custom exceptions for certain status codes
        if "expired" in status:
            raise SessionExpiredError(status)
        if "wrong" in status:
            raise InvalidAccessTokenError(status)

        # Raise for all other status codes
        raise AuthenticationError(status)

    async def async_fetch_access_token(self) -> str:
        """
        Retrieve new access token from server.
        :returns: New access token
        :raises MalformedResponseError: Response payload is malformed.
        """
        async with self._session.post(
            self.BASE_URL + "/oauth/token",
            headers={
                "Authorization": self.OAUTH_HEADER,
            },
        ) as response:
            data = await self._handle_dict_response(response)

            try:
                return data["access_token"]
            except KeyError as e:
                raise MalformedResponseError("Access token not present") from e

    async def async_apply_access_token(self, access_token: str):
        """
        Attempt authentication using provided access token.
        :param access_token: Access token for authentication
        :raises MalformedResponseError: Issues related to user ID
        """
        self.logger.debug(f"Authenticating access token: {access_token}")

        async with self._session.post(
            self.BASE_URL + "/api/users/login",
            data={
                "login": self._username,
                "password": self._password,
                "lang": "ru",
                "v": "3",
                "utc_offset": self._utc_offset // 60,
                "access_token": access_token,
            },
        ) as response:
            try:
                data = await self._handle_dict_response(response)
            except AuthenticationError:
                raise
            except PandoraOnlineException as exc:
                raise AuthenticationError(*exc.args) from exc

        # Extrapolate user identifier
        try:
            user_id = int(data["user_id"])
        except (TypeError, ValueError) as exc:
            raise MalformedResponseError("Unexpected user ID format") from exc
        except KeyError as exc:
            raise MalformedResponseError("User ID not present") from exc

        # Save processed data
        self._user_id = user_id
        self.access_token = access_token

        self.logger.info("Access token authentication successful")

    async def async_authenticate(self, access_token: str | None = None) -> None:
        """
        Perform authentication (optionally using provided access token).

        Performs authentication in 4 steps at max:
        - Attempt authentication using provided token
        - Attempt authentication using existing token
        - Attempt fetching new access token
        - Attempt authentication using new token

        At most three different access tokens may circulate within
        this method.

        Raises all exceptions from `async_fetch_access_token` and
        `async_apply_access_token`.
        :param access_token: Optional access token to use.
        :raises MalformedResponseError: Issues related to user ID.
        """
        self.logger.debug(f"Authenticating access token: {access_token}")
        if access_token:
            try:
                await self.async_apply_access_token(access_token)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                self.logger.warning(
                    f"Authentication with provided access token failed: {exc}",
                    exc_info=exc,
                )
            else:
                return

        if access_token != (access_token := self.access_token) and access_token:
            try:
                await self.async_apply_access_token(access_token)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                self.logger.warning(
                    f"Authentication with existing access token failed: {exc}",
                    exc_info=exc,
                )
            else:
                return

        try:
            access_token = await self.async_fetch_access_token()
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            self.logger.error(
                f"Could not retrieve access token: {exc}",
                exc_info=exc,
            )
            raise

        try:
            await self.async_apply_access_token(access_token)
        except asyncio.CancelledError:
            raise
        except BaseException as exc:
            self.logger.error(
                f"Authentication with fetched access token failed: {exc}",
                exc_info=exc,
            )
            raise

    async def async_refresh_devices(self) -> None:
        """
        Retrieve and cache list of vehicles for the account.

        :raises MissingAccessTokenError: No access token for request.
        :raises MalformedResponseError: Device data is malformed beyond reading.
        :raises aiohttp.ClientError: Error requesting data.
        """
        if not (access_token := self.access_token):
            raise MissingAccessTokenError

        self.logger.debug("Retrieving devices")

        async with self._session.get(
            self.BASE_URL + "/api/devices",
            params={"access_token": access_token},
        ) as response:
            devices_data = await self._handle_list_response(response)

        self.logger.debug(f"Retrieved devices: {devices_data}")

        for device_attributes in devices_data:
            try:
                device_id = self.parse_device_id(device_attributes)
            except (TypeError, ValueError, LookupError) as exc:
                self.logger.error(f"Error parsing device ID: {exc}", exc_info=exc)
            else:
                try:
                    device_object = self._devices[device_id]
                except LookupError:
                    self.logger.debug(f"Adding new device with ID {device_id}")
                    self._devices[device_id] = PandoraOnlineDevice(
                        self, device_attributes, logger=self.logger
                    )
                else:
                    device_object.attributes = device_attributes

    async def async_remote_command(
        self,
        device_id: int,
        command_id: int | CommandID,
        params: Mapping[str, Any] = None,
    ) -> None:
        """
        Execute remote command on target device.
        :param device_id: Device ID to execute command on.
        :param command_id: Identifier of the command to execute.
        :param params: additional parameters to send with the command.
        :raises PandoraOnlineException: Failed command execution with response.
        """
        self.logger.info(f"Sending command {command_id} to device {device_id}")

        data = {"id": device_id, "command": int(command_id)}

        if params:
            data["comm_params"] = json.dumps(dict(params))

        async with self._session.post(
            self.BASE_URL + "/api/devices/command",
            data=data,
            params={"access_token": self.access_token},
        ) as response:
            data = await self._handle_dict_response(response)

        try:
            status = data["action_result"][str(device_id)]
        except (LookupError, AttributeError, TypeError):
            status = "unknown error"

        if status != "sent":
            self.logger.error(
                f"Error sending command {command_id} "
                f"to device {device_id}: {status}"
            )
            raise PandoraOnlineException(status)

        self.logger.info(f"Command {command_id} sent to device {device_id}")

    async def async_wake_up_device(self, device_id: int) -> None:
        """
        Send wake up command to target device.

        :param device_id: Device identifier
        """
        self.logger.info(f"Waking up device {device_id}")

        async with self._session.post(
            self.BASE_URL + "/api/devices/wakeup",
            data={"id": device_id},
            params={"access_token": self.access_token},
        ) as response:
            data = await self._handle_dict_response(response)

        try:
            status = data["status"]
        except (LookupError, AttributeError, TypeError):
            status = "unknown error"

        if status != "success":
            self.logger.error(f"Error waking up device {device_id}: {status}")
            raise PandoraOnlineException(status)

        response.raise_for_status()

    async def async_fetch_device_settings(self, device_id: int | str) -> dict[str, Any]:
        """
        Fetch settings relevant to target device.

        :param device_id: Device identifier
        """
        async with self._session.get(
            self.BASE_URL + "/api/devices/settings",
            params={"access_token": self.access_token, "id": device_id},
        ) as response:
            data = await self._handle_dict_response(response)

        try:
            devices_settings = data["device_settings"]
        except KeyError as exc:
            raise MalformedResponseError("device_settings not retrieved") from exc

        if not (device_id is None or device_id in devices_settings):
            raise MalformedResponseError("settings not retrieved")

        return sorted(devices_settings[device_id], key=lambda x: x.get("dtime") or 0)[
            -1
        ]

    @staticmethod
    def parse_device_id(data: Mapping[str, Any]) -> int:
        # Fixes absense of identifier value on certain device responses.
        try:
            device_id = data["dev_id"]
        except KeyError:
            device_id = data["id"]

        if not device_id:
            raise ValueError("device ID is empty / zero")

        return int(device_id)

    @staticmethod
    def parse_fuel_tanks(
        fuel_tanks_data: Iterable[Mapping[str, Any | None]],
        existing_fuel_tanks: Collection[FuelTank | None] = None,
    ) -> tuple[FuelTank, ...]:
        fuel_tanks = []

        for fuel_tank_data in fuel_tanks_data or ():
            id_ = int(fuel_tank_data["id"])

            fuel_tank = None

            for existing_fuel_tank in existing_fuel_tanks or ():
                if existing_fuel_tank.id == id_:
                    fuel_tank = existing_fuel_tank
                    break

            try:
                ras = float(fuel_tank_data["ras"])
            except (ValueError, TypeError, LookupError):
                ras = None

            try:
                ras_t = float(fuel_tank_data["ras_t"])
            except (ValueError, TypeError, LookupError):
                ras_t = None

            try:
                value = float(fuel_tank_data["val"])
            except (ValueError, TypeError, LookupError):
                value = 0.0

            if fuel_tank is None:
                fuel_tanks.append(FuelTank(id=id_, value=value, ras=ras, ras_t=ras_t))
            else:
                object.__setattr__(fuel_tank, "value", value)
                object.__setattr__(fuel_tank, "ras", ras)
                object.__setattr__(fuel_tank, "ras_t", ras_t)

        return tuple(fuel_tanks)

    def _update_device_current_state(
        self, device: "PandoraOnlineDevice", **state_args
    ) -> tuple[CurrentState, dict[str, Any]]:
        # Extract UTC offset
        prefixes = ("online", "state")
        utc_offset = device.utc_offset
        for prefix in prefixes:
            utc = (non_utc := prefix + "_timestamp") + "_utc"
            if not (
                (non_utc_val := state_args.get(non_utc)) is None
                or (utc_val := state_args.get(utc)) is None
            ):
                utc_offset = round((non_utc_val - utc_val) / 60) * 60
                if device.utc_offset != utc_offset:
                    self.logger.debug(
                        f"Calculated UTC offset for device {device.device_id}: {utc_offset} seconds"
                    )
                    device.utc_offset = utc_offset
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
        if (state := device.state) is None:
            device.state = state = CurrentState(**state_args)
            self.logger.debug(f"Setting new state object on device {device.device_id}")
        else:
            bad_timestamp = None
            for postfix in ("", "_utc"):
                for prefix in prefixes:
                    if getattr(state, key := (prefix + "_timestamp" + postfix)) is None:
                        continue
                    if state_args.get(key) is None:
                        continue
                    if getattr(state, key) <= state_args.get(key):
                        continue
                    bad_timestamp = key
                    break
            if bad_timestamp is None:
                device.state = attr.evolve(state, **state_args)
                self.logger.debug(f"Updating state object on device {device.device_id}")
            else:
                self.logger.warning(
                    f"State update for device {device.device_id} is "
                    f"older than existing data (based on '{bad_timestamp}'), "
                    f"this state update will be ignored completely!"
                )
                for postfix in ("", "_utc"):
                    for prefix in prefixes:
                        key = f"{prefix}_timestamp{postfix}"
                        cur, new = (
                            getattr(state, key) or 0,
                            state_args.get(key) or 0,
                        )
                        sign = "=" if cur == new else ("<" if cur < new else ">")
                        self.logger.debug(
                            f"Timestamp {key} for {device.device_id}: {cur} {sign} {new}"
                        )
                return state, {}

        # noinspection PyTypeChecker
        return state, state_args

    # noinspection PyMethodMayBeStatic
    def _process_http_event(
        self, device: "PandoraOnlineDevice", data: Mapping[str, Any]
    ) -> TrackingEvent:
        event = TrackingEvent.from_dict(data, device_id=device.device_id)

        if (e := device.last_event) and e.timestamp < event.timestamp:
            device.last_event = TrackingEvent

        return event

    def _process_http_state(
        self,
        device: "PandoraOnlineDevice",
        data_stats: Mapping[str, Any] | None = None,
        data_time: Mapping[str, Any] | None = None,
    ) -> tuple[CurrentState, dict[str, Any]]:
        update_args = {}
        if data_stats:
            self.logger.debug(
                f"Received data update from HTTP for device {device.device_id}: {data_stats}"
            )
            update_args.update(
                **CurrentState.get_http_state_args(
                    data_stats,
                    identifier=device.device_id,
                ),
                is_online=bool(data_stats.get("online")),
            )
        if data_time:
            self.logger.debug(
                f"Received time update from HTTP for device {device.device_id}: {data_time}"
            )
            update_args.update(
                online_timestamp=data_time.get("onlined"),
                online_timestamp_utc=data_time.get("online"),
                command_timestamp_utc=data_time.get("command"),
                settings_timestamp_utc=data_time.get("setting"),
            )
        return self._update_device_current_state(device, **update_args)

    async def async_fetch_events(
        self,
        timestamp_from: int = 0,
        timestamp_to: int | None = None,
        limit: int = 20,
        device_id: int | None = None,
    ) -> list[TrackingEvent]:
        if timestamp_from < 0:
            raise ValueError("timestamp_from must not be less than zero")
        if timestamp_to is None:
            # Request future to avoid timezone differences
            timestamp_to = int((datetime.now() + timedelta(days=1)).timestamp())

        log_postfix = f"between {timestamp_from} and {timestamp_to}"
        self.logger.debug(f"Fetching events{log_postfix}")
        params = {
            "access_token": self.access_token,
            "from": str(timestamp_from),
            "to": str(timestamp_to),
        }
        if device_id:
            params["id"] = str(device_id)
        if limit:
            params["limit"] = str(limit)
        async with self._session.get(
            self.BASE_URL + "/api/lenta",
            params=params,
        ) as response:
            data = await self._handle_dict_response(response)

        events = []
        for event_entry in data.get("lenta") or []:
            if not (event_data := event_entry.get("obj")):
                continue
            events.append(TrackingEvent.from_dict(event_data))
        self.logger.debug(f"Received {len(events)} event{log_postfix}")
        return events

    async def async_request_updates(
        self, timestamp: int | None = None
    ) -> tuple[dict[int, dict[str, Any]], list[TrackingEvent]]:
        """
        Fetch the latest changes from update server.
        :param timestamp: Timestamp to fetch updates since (optional, uses
                          last update timestamp internally if not provided).
        :return: Dictionary of (device_id => (state_attribute => new_value))
        """
        if not (access_token := self.access_token):
            raise MissingAccessTokenError("Account is not authenticated")

        # Select last timestamp if none provided
        _timestamp = self._last_update if timestamp is None else timestamp

        self.logger.info(f"Fetching changes since {_timestamp}")

        async with self._session.get(
            self.BASE_URL + "/api/updates",
            params={"ts": _timestamp, "access_token": access_token},
        ) as response:
            data = await self._handle_dict_response(response)

        device_new_attrs: dict[int, dict[str, Any]] = {}

        # Stats / time updates
        updates: dict[int, dict[str, dict[str, Any]]] = {}
        for key in ("stats", "time"):
            # Check if response contains necessary data
            if not (mapping := data.get(key)):
                continue

            # Iterate over device responses
            for device_id, device_data in mapping.items():
                try:
                    device = self._devices[int(device_id)]
                except (TypeError, ValueError):
                    self.logger.warning(f"Bad device ID in {key} data: {device_id}")
                except LookupError:
                    self.logger.warning(
                        f"Received {key} data for "
                        f"uninitialized device {device_id}: {device_data}"
                    )
                    continue
                else:
                    # Two .setdefault-s just in case data is doubled
                    updates.setdefault(device.device_id, {}).setdefault(
                        "data_" + key, {}
                    ).update(device_data)

        # Process state update once the list has been compiled
        for device_id, update_args in updates.items():
            device_new_attrs[device_id] = self._process_http_state(
                self._devices[device_id], **update_args
            )[1]

        # Event updates
        events = []
        for event_wrapper in data.get("lenta") or ():
            if not (event_obj := event_wrapper.get("obj")):
                continue

            try:
                raw_device_id = event_obj["dev_id"]
            except (LookupError, AttributeError):
                # @TODO: handle such events?
                continue

            try:
                device = self._devices[int(raw_device_id)]
            except (TypeError, ValueError):
                self.logger.warning(f"Bad device ID in event data: {raw_device_id}")
                continue
            except LookupError:
                self.logger.warning(
                    "Received event data for "
                    f"uninitialized device {raw_device_id}: {event_obj}"
                )
                continue

            events.append(self._process_ws_event(device, event_obj))

        if device_new_attrs:
            self.logger.debug(f"Received updates from HTTP: {device_new_attrs}")

        try:
            self._last_update = int(data["ts"])
        except (LookupError, TypeError, ValueError):
            self.logger.warning("Response did not contain timestamp")

        return device_new_attrs, events

    def _process_ws_initial_state(
        self, device: "PandoraOnlineDevice", data: Mapping[str, Any]
    ) -> tuple[CurrentState, dict[str, Any]]:
        """
        Process WebSockets state initialization.
        :param device: Device this update is designated for
        :param data: Data containing update
        :return: [Device state, Dictionary of real updates]
        """

        self.logger.debug(f"Initializing state for {device.device_id} from {data}")

        return self._update_device_current_state(
            device,
            **CurrentState.get_ws_state_args(data, identifier=device.device_id),
        )

    def _process_ws_state(
        self, device: "PandoraOnlineDevice", data: Mapping[str, Any]
    ) -> tuple[CurrentState, dict[str, Any]]:
        """
        Process WebSockets state update.
        :param device: Device this update is designated for
        :param data: Data containing update
        :return: [Device state, Dictionary of real updates]
        """
        self.logger.debug(f"Updating state for {device.device_id}")

        return self._update_device_current_state(
            device,
            **CurrentState.get_ws_state_args(data, identifier=device.device_id),
        )

    # The routines are virtually the same
    _process_ws_event = _process_http_event

    def _process_ws_point(
        self,
        device: "PandoraOnlineDevice",
        data: Mapping[str, Any],
    ) -> tuple[TrackingPoint, CurrentState | None, dict[str, Any] | None]:
        try:
            fuel = data["fuel"]
        except KeyError:
            fuel = None
        else:
            if fuel is not None:
                fuel = float(fuel)

        try:
            speed = data["speed"]
        except KeyError:
            speed = None
        else:
            if speed is not None:
                speed = float(speed)

        try:
            max_speed = data["max_speed"]
        except KeyError:
            max_speed = None
        else:
            if max_speed is not None:
                max_speed = float(max_speed)

        try:
            length = data["length"]
        except KeyError:
            length = None
        else:
            if length is not None:
                length = float(length)

        timestamp = data.get("dtime") or time()

        # Update state since point is newer
        if (state := device.state) and state.state_timestamp <= timestamp:
            state, state_args = self._update_device_current_state(
                device,
                **CurrentState.get_ws_point_args(
                    data,
                    identifier=device.device_id,
                    state_timestamp=timestamp,
                ),
            )
        else:
            state_args = None

        return (
            TrackingPoint(
                device_id=device.device_id,
                track_id=data["track_id"],
                latitude=data["x"],
                longitude=data["y"],
                timestamp=timestamp,
                fuel=fuel,
                speed=speed,
                max_speed=max_speed,
                length=length,
            ),
            state,
            state_args,
        )

    # noinspection PyMethodMayBeStatic
    def _process_ws_command(
        self, device: "PandoraOnlineDevice", data: Mapping[str, Any]
    ) -> tuple[int, int, int]:
        command_id, result, reply = (
            data["command"],
            data["result"],
            data["reply"],
        )

        try:
            result = int(result)
        except (TypeError, ValueError):
            self.logger.warning(
                f"Could not decode result {result} for command "
                f"{command_id}, assuming an error"
            )
            result = 1

        if device.control_busy:
            if result:
                device.release_control_lock(f"(CID:{command_id}) reply={reply}")
            else:
                device.release_control_lock()

        return command_id, result, reply

    # noinspection PyMethodMayBeStatic
    def _process_ws_update_settings(
        self, device: "PandoraOnlineDevice", data: Mapping[str, Any]
    ) -> Mapping[str, Any]:
        # @TODO: do something?
        return {
            **data,
            "device_id": device.device_id,
        }

    async def _do_ws_auto_auth(self) -> bool:
        try:
            try:
                self.logger.debug("[reauth] Checking WS access token")
                await self.async_check_access_token()
            except AuthenticationError:
                self.logger.debug("[reauth] Performing authentication")
                await self.async_authenticate()
            else:
                self.logger.debug("[reauth] WS access token still valid")
        except asyncio.CancelledError:
            raise
        except AuthenticationError as exc:
            self.logger.error(
                f"[reauth] Severe authentication error: {exc}",
                exc_info=exc,
            )
            raise
        except (OSError, TimeoutError) as exc:
            self.logger.error(
                "[reauth] Temporary authentication error, "
                f"will check again later: {exc}",
                exc_info=exc,
            )
        else:
            # Successful authentication validation
            return True
        # Failed authentication validation
        return False

    async def _iterate_websockets(self, effective_read_timeout: float | None = None):
        if not (access_token := self.access_token):
            raise MissingAccessTokenError

        # WebSockets session
        async with self._session.ws_connect(
            self.BASE_URL + f"/api/v4/updates/ws?access_token={access_token}",
            heartbeat=15.0,
        ) as ws:
            self.logger.debug("WebSockets connected")
            while not ws.closed:
                message = None
                if effective_read_timeout is not None and effective_read_timeout > 0:
                    async with timeout(effective_read_timeout):
                        while message is None or message.type != aiohttp.WSMsgType.text:
                            if (message := await ws.receive()).type in (
                                aiohttp.WSMsgType.CLOSED,
                                aiohttp.WSMsgType.CLOSING,
                                aiohttp.WSMsgType.ERROR,
                                aiohttp.WSMsgType.CLOSE,
                            ):
                                break
                else:
                    message = await ws.receive()

                if message.type != aiohttp.WSMsgType.text:
                    break

                try:
                    contents = message.json()
                except json.JSONDecodeError:
                    self.logger.warning(f"Unknown message data: {message}")
                if isinstance(contents, Mapping):
                    self.logger.debug(f"Received WS message: {contents}")
                    yield contents
                else:
                    self.logger.warning(
                        "Received message is not " f"a mapping (dict): {message}"
                    )

    async def async_listen_websockets(
        self,
        auto_restart: bool = False,
        auto_reauth: bool = True,
        effective_read_timeout: float | None = 180.0,
    ):
        while True:
            known_exception = None
            try:
                async for message in self._iterate_websockets(effective_read_timeout):
                    yield message
            except asyncio.CancelledError:
                self.logger.debug("WS listener stopped gracefully")
                raise

            # Handle temporary exceptions
            except TimeoutError as exc:
                known_exception = exc
                self.logger.error(f"WS temporary error: {exc}")

            except OSError as exc:
                known_exception = exc
                self.logger.error(f"WS OS Error: {exc}")

            except aiohttp.ClientError as exc:
                # @TODO: check if authentication is required
                known_exception = exc
                self.logger.error(f"WS client error: {exc}")

            except PandoraOnlineException as exc:
                known_exception = exc
                self.logger.error(f"WS API error: {exc}")

            else:
                self.logger.debug("WS client closed")

            # Raise exception
            if not auto_restart:
                raise (
                    known_exception or PandoraOnlineException("WS closed prematurely")
                )

            # Reauthenticate if required
            while auto_reauth and not await self._do_ws_auto_auth():
                await asyncio.sleep(3.0)

            if not auto_reauth:
                # Sleep for all else
                await asyncio.sleep(3.0)

    async def async_listen_for_updates(
        self,
        *,
        state_callback: (
            Callable[
                ["PandoraOnlineDevice", CurrentState, Mapping[str, Any]],
                Awaitable[None] | None,
            ]
            | None
        ) = None,
        command_callback: (
            Callable[
                ["PandoraOnlineDevice", int, int, Any | None],
                Awaitable[None] | None,
            ]
            | None
        ) = None,
        event_callback: (
            Callable[
                ["PandoraOnlineDevice", TrackingEvent],
                Awaitable[None] | None,
            ]
            | None
        ) = None,
        point_callback: (
            Callable[
                [
                    "PandoraOnlineDevice",
                    TrackingPoint,
                    CurrentState | None,
                    Mapping[str, Any] | None,
                ],
                Awaitable[None] | None,
            ]
            | None
        ) = None,
        update_settings_callback: (
            Callable[
                ["PandoraOnlineDevice", Mapping[str, Any]],
                Awaitable[None] | None,
            ]
            | None
        ) = None,
        reconnect_on_device_online: bool = True,
        auto_restart: bool = False,
        auto_reauth: bool = True,
        effective_read_timeout: float | None = 180.0,
    ) -> None:
        async def _handle_ws_message(contents: Mapping[str, Any]) -> bool | None:
            """
            Handle WebSockets message.
            :returns: True = keep running, None = restart, False = stop
            """
            callback_coro = None

            # Extract message type and data
            try:
                type_, data = (
                    contents["type"],
                    contents["data"],
                )
            except LookupError:
                self.logger.error(f"WS malformed data: {contents}")
                return True

            # Extract device ID
            try:
                device_id = self.parse_device_id(data)
            except (TypeError, ValueError):
                self.logger.warning(f"WS data with invalid device ID: {data['dev_id']}")
                return True
            except LookupError:
                self.logger.warning(f"WS {type_} with no device ID: {data}")
                return True

            # Check presence of the device
            try:
                device = self._devices[device_id]
            except LookupError:
                self.logger.warning(
                    f"WS {type_} for unregistered " f"device ID {device_id}: {data}"
                )
                return True

            return_result = True

            try:
                if type_ == WSMessageType.INITIAL_STATE:
                    result = self._process_ws_initial_state(device, data)
                    if state_callback:
                        callback_coro = state_callback(device, *result)

                elif type_ == WSMessageType.STATE:
                    prev_online = device.is_online
                    result = self._process_ws_state(device, data)
                    if (
                        reconnect_on_device_online
                        and not prev_online
                        and device.is_online
                    ):
                        self.logger.debug(
                            "Will restart WS to fetch new state "
                            f"after device {device_id} went online"
                        )
                        # Force reconnection to retrieve initial state immediately
                        return_result = None
                    if result is not None and state_callback:
                        callback_coro = state_callback(device, *result)

                elif type_ == WSMessageType.POINT:
                    result = self._process_ws_point(device, data)
                    if point_callback:
                        callback_coro = point_callback(device, *result)

                elif type_ == WSMessageType.COMMAND:
                    (
                        command_id,
                        result,
                        reply,
                    ) = self._process_ws_command(device, data)

                    if command_callback:
                        callback_coro = command_callback(
                            device,
                            command_id,
                            result,
                            reply,
                        )

                elif type_ == WSMessageType.EVENT:
                    result = self._process_ws_event(device, data)
                    if event_callback:
                        callback_coro = event_callback(device, result)

                elif type_ == WSMessageType.UPDATE_SETTINGS:
                    result = self._process_ws_update_settings(device, data)
                    if event_callback:
                        callback_coro = update_settings_callback(device, result)

                else:
                    self.logger.warning(f"WS data of unknown type {type_}: {data}")
            except BaseException as exc:
                self.logger.warning(
                    "Error during preliminary response processing "
                    f"with message type {type_}: {repr(exc)}\nPlease, "
                    "report this error to the developer immediately!",
                    exc_info=exc,
                )
                return True

            if callback_coro is not None:
                try:
                    await asyncio.shield(callback_coro)
                except asyncio.CancelledError:
                    raise
                except BaseException as exc:
                    self.logger.exception(f"Error during callback handling: {exc}")

            return return_result

        # On empty (none) responses, reconnect WS
        # On False response, stop WS
        response = None
        while response is not False:
            async for message in self.async_listen_websockets(
                auto_restart=auto_restart,
                auto_reauth=auto_reauth,
                effective_read_timeout=effective_read_timeout,
            ):
                if not (response := await _handle_ws_message(message)):
                    break

        self.logger.info("WS updates listener stopped")
