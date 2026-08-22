"""Button entities for learned IR commands."""

from typing import override

from homeassistant.components.button import ButtonEntity
from homeassistant.const import CONF_CODE
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr, entity_registry as er
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import ZigbeeInfraredBridgeConfigEntry
from .const import CONF_IEEE, DOMAIN, SUBENTRY_TYPE_COMMAND


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ZigbeeInfraredBridgeConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up IR command buttons from a config entry."""
    buttons = [
        IrCommandButton(entry, subentry_id)
        for subentry_id, subentry in entry.subentries.items()
        if subentry.subentry_type == SUBENTRY_TYPE_COMMAND
    ]
    if not buttons:
        return

    # One parent device for the IR blaster; entities keep their own subentry ids.
    dr.async_get(hass).async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, entry.data[CONF_IEEE])},
        name=entry.title,
    )

    async_add_entities(buttons)


class IrCommandButton(ButtonEntity):
    """A button that replays a previously learned IR command."""

    _attr_has_entity_name = True

    def __init__(
        self, entry: ZigbeeInfraredBridgeConfigEntry, subentry_id: str
    ) -> None:
        """Initialize the button."""
        self._entry = entry
        self.subentry_id = subentry_id
        self._attr_unique_id = subentry_id
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.data[CONF_IEEE])},
            name=entry.title,
        )

    @override
    async def async_added_to_hass(self) -> None:
        """Link the entity to its config subentry after registration."""
        await super().async_added_to_hass()
        er.async_get(self.hass).async_update_entity(
            self.entity_id,
            config_subentry_id=self.subentry_id,
        )

    @property
    @override
    def name(self) -> str:
        """Return the name of the button."""
        return self._entry.subentries[self.subentry_id].title

    @override
    async def async_press(self) -> None:
        """Send the learned IR command."""
        code = self._entry.subentries[self.subentry_id].data[CONF_CODE]
        await self._entry.runtime_data.async_send_code(code)
