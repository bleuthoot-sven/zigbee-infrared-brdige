"""The Zigbee Infrared Bridge integration."""

from zigpy.types import EUI64

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady, HomeAssistantError

from .const import CONF_IEEE
from .ir_blaster import ZigbeeIrBlaster

_PLATFORMS: list[Platform] = [Platform.BUTTON]

type ZigbeeInfraredBridgeConfigEntry = ConfigEntry[ZigbeeIrBlaster]


async def async_setup_entry(
    hass: HomeAssistant, entry: ZigbeeInfraredBridgeConfigEntry
) -> bool:
    """Set up Zigbee Infrared Bridge from a config entry."""
    blaster = ZigbeeIrBlaster(hass, EUI64.convert(entry.data[CONF_IEEE]))
    try:
        blaster.async_ensure_available()
    except HomeAssistantError as err:
        raise ConfigEntryNotReady from err

    entry.runtime_data = blaster

    await hass.config_entries.async_forward_entry_setups(entry, _PLATFORMS)

    return True


async def async_unload_entry(
    hass: HomeAssistant, entry: ZigbeeInfraredBridgeConfigEntry
) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, _PLATFORMS)
