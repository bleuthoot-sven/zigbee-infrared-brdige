"""Config flow for the Zigbee Infrared Bridge integration."""

from typing import Any, override

import voluptuous as vol
from zigpy.types import EUI64

from homeassistant.components.zha.const import (  # pylint: disable=home-assistant-component-root-import
    DOMAIN as ZHA_DOMAIN,
)
from homeassistant.components.zha.helpers import (  # pylint: disable=home-assistant-component-root-import
    get_zha_gateway,
)
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_DEVICE_ID
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.selector import (
    DeviceFilterSelectorConfig,
    DeviceSelector,
    DeviceSelectorConfig,
)

from .const import CONF_IEEE, DOMAIN, IR_CONTROL_CLUSTER_ID


class NotAnIrBlaster(HomeAssistantError):
    """Raised when the picked ZHA device is not a supported IR blaster."""


def _async_get_ir_blaster_ieee(hass_device_entry: dr.AnyDeviceEntry) -> EUI64:
    """Return the IEEE address of a ZHA device, validated as an IR blaster."""
    ieee_str = next(
        (
            identifier[1]
            for identifier in hass_device_entry.identifiers
            if identifier[0] == ZHA_DOMAIN
        ),
        None,
    )
    if ieee_str is None:
        raise NotAnIrBlaster
    return EUI64.convert(ieee_str)


def _async_validate_ir_blaster(hass: HomeAssistant, ieee: EUI64) -> None:
    """Raise NotAnIrBlaster unless the ZHA device exposes an IR control cluster."""
    zha_device = get_zha_gateway(hass).get_device(ieee)
    if zha_device is None:
        raise NotAnIrBlaster
    if not any(
        IR_CONTROL_CLUSTER_ID in endpoint.in_clusters
        for endpoint_id, endpoint in zha_device.device.endpoints.items()
        if endpoint_id
    ):
        raise NotAnIrBlaster


class ZigbeeInfraredBridgeConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Zigbee Infrared Bridge."""

    VERSION = 1

    @override
    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}
        if user_input is not None:
            device_registry = dr.async_get(self.hass)
            device_entry = device_registry.async_get(user_input[CONF_DEVICE_ID])
            try:
                if device_entry is None:
                    raise NotAnIrBlaster  # noqa: TRY301
                ieee = _async_get_ir_blaster_ieee(device_entry)
                _async_validate_ir_blaster(self.hass, ieee)
            except NotAnIrBlaster:
                errors["base"] = "not_ir_blaster"
            else:
                await self.async_set_unique_id(str(ieee))
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=device_entry.name_by_user or device_entry.name or str(ieee),
                    data={CONF_IEEE: str(ieee)},
                )

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_DEVICE_ID): DeviceSelector(
                        DeviceSelectorConfig(
                            filter=DeviceFilterSelectorConfig(integration=ZHA_DOMAIN)
                        )
                    ),
                }
            ),
            errors=errors,
        )
