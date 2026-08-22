"""Remote entity for learned IR commands."""

import asyncio
import logging
from collections.abc import Iterable
from types import MappingProxyType
from typing import Any, override

from homeassistant.components import persistent_notification
from homeassistant.components.remote import (
    ATTR_COMMAND,
    ATTR_DELAY_SECS,
    ATTR_NUM_REPEATS,
    ATTR_TIMEOUT,
    DEFAULT_DELAY_SECS,
    RemoteEntity,
    RemoteEntityFeature,
)
from homeassistant.config_entries import ConfigSubentry
from homeassistant.const import CONF_CODE
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import ZigbeeInfraredBridgeConfigEntry
from .const import CONF_IEEE, DOMAIN, LEARN_TIMEOUT, SUBENTRY_TYPE_COMMAND

_LOGGER = logging.getLogger(__name__)

LEARN_NOTIFICATION_ID = f"{DOMAIN}_learn_command"


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ZigbeeInfraredBridgeConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the IR blaster remote from a config entry."""
    dr.async_get(hass).async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, entry.data[CONF_IEEE])},
        name=entry.title,
    )

    async_add_entities([IrBlasterRemote(entry)])


class IrBlasterRemote(RemoteEntity):
    """A remote that replays previously learned IR commands."""

    _attr_has_entity_name = True
    _attr_icon = "mdi:remote"
    _attr_is_on = True
    _attr_supported_features = (
        RemoteEntityFeature.LEARN_COMMAND | RemoteEntityFeature.DELETE_COMMAND
    )

    def __init__(self, entry: ZigbeeInfraredBridgeConfigEntry) -> None:
        """Initialize the remote."""
        self._entry = entry
        self._learn_lock = asyncio.Lock()
        self._attr_unique_id = entry.entry_id
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.data[CONF_IEEE])},
            name=entry.title,
        )

    def _get_subentry_for_command(self, command: str) -> ConfigSubentry | None:
        """Return the config subentry for a learned command name."""
        for subentry in self._entry.subentries.values():
            if (
                subentry.subentry_type == SUBENTRY_TYPE_COMMAND
                and subentry.title == command
            ):
                return subentry
        return None

    def _get_code_for_command(self, command: str) -> str | None:
        """Return the IR code for a learned command name."""
        subentry = self._get_subentry_for_command(command)
        if subentry is None:
            return None
        return subentry.data[CONF_CODE]

    def _async_store_command(self, command: str, code: str) -> None:
        """Persist a learned command."""
        subentry = self._get_subentry_for_command(command)
        if subentry is not None:
            self.hass.config_entries.async_update_subentry(
                self._entry,
                subentry,
                data={CONF_CODE: code},
            )
            return

        self.hass.config_entries.async_add_subentry(
            self._entry,
            ConfigSubentry(
                data=MappingProxyType({CONF_CODE: code}),
                subentry_type=SUBENTRY_TYPE_COMMAND,
                title=command,
                unique_id=command,
            ),
        )

    @override
    async def async_send_command(self, command: Iterable[str], **kwargs: Any) -> None:
        """Send one or more learned IR commands by name."""
        commands = list(command)
        repeat = kwargs.get(ATTR_NUM_REPEATS, 1)
        delay = kwargs.get(ATTR_DELAY_SECS, DEFAULT_DELAY_SECS)
        send_queue = [cmd for _ in range(repeat) for cmd in commands]

        for index, cmd in enumerate(send_queue):
            code = self._get_code_for_command(cmd)
            if code is None:
                raise ValueError(f"Command not found: {cmd!r}")
            await self._entry.runtime_data.async_send_code(code)
            if index < len(send_queue) - 1:
                await asyncio.sleep(delay)

    @override
    async def async_learn_command(self, **kwargs: Any) -> None:
        """Learn one or more IR commands from a physical remote."""
        command_list = kwargs.get(ATTR_COMMAND)
        if not command_list:
            raise ValueError("command is required")

        timeout = kwargs.get(ATTR_TIMEOUT, LEARN_TIMEOUT)

        async with self._learn_lock:
            for command in command_list:
                persistent_notification.async_create(
                    self.hass,
                    (
                        f"Point the remote at the IR blaster and press the "
                        f"'{command}' button."
                    ),
                    title="Learn command",
                    notification_id=LEARN_NOTIFICATION_ID,
                )
                try:
                    code = await self._entry.runtime_data.async_learn_code(timeout)
                except HomeAssistantError as err:
                    _LOGGER.error("Failed to learn '%s': %s", command, err)
                    raise
                finally:
                    persistent_notification.async_dismiss(
                        self.hass, notification_id=LEARN_NOTIFICATION_ID
                    )

                self._async_store_command(command, code)

    @override
    async def async_delete_command(self, **kwargs: Any) -> None:
        """Delete one or more learned IR commands."""
        command_list = kwargs.get(ATTR_COMMAND)
        if not command_list:
            raise ValueError("command is required")

        not_found: list[str] = []
        for command in command_list:
            subentry = self._get_subentry_for_command(command)
            if subentry is None:
                not_found.append(command)
                continue
            self.hass.config_entries.async_remove_subentry(
                self._entry, subentry.subentry_id
            )

        if not_found:
            if len(not_found) == 1:
                raise ValueError(f"Command not found: {not_found[0]!r}")
            raise ValueError(f"Commands not found: {not_found!r}")
