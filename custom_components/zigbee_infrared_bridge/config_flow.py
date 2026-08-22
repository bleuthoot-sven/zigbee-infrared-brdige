"""Config flow for the Zigbee Infrared Bridge integration."""

import asyncio
from typing import Any, override

import voluptuous as vol
from zigpy.types import EUI64

from homeassistant.components.zha.const import (  # pylint: disable=home-assistant-component-root-import
    DOMAIN as ZHA_DOMAIN,
)
from homeassistant.components.zha.helpers import (  # pylint: disable=home-assistant-component-root-import
    get_zha_gateway,
)
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    ConfigSubentryFlow,
    SubentryFlowResult,
)
from homeassistant.const import CONF_CODE, CONF_DEVICE_ID, CONF_NAME
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.selector import (
    DeviceFilterSelectorConfig,
    DeviceSelector,
    DeviceSelectorConfig,
)

from .const import (
    CONF_IEEE,
    DOMAIN,
    IR_CONTROL_CLUSTER_ID,
    LEARN_TIMEOUT,
    SUBENTRY_TYPE_COMMAND,
)


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

    @classmethod
    @callback
    @override
    def async_get_supported_subentry_types(
        cls, config_entry: ConfigEntry
    ) -> dict[str, type[ConfigSubentryFlow]]:
        """Return subentries supported by this handler."""
        return {SUBENTRY_TYPE_COMMAND: CommandSubentryFlowHandler}


class CommandSubentryFlowHandler(ConfigSubentryFlow):
    """Handle learning and naming an IR command."""

    learn_task: asyncio.Task[str] | None = None
    _learned_code: str

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        """Learn a new IR command."""
        return await self._async_step_learn(step_id="user", next_step_id="name")

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        """Re-learn an existing IR command."""
        return await self._async_step_learn(
            step_id="reconfigure", next_step_id="reconfigure_name"
        )

    async def _async_step_learn(
        self, step_id: str, next_step_id: str
    ) -> SubentryFlowResult:
        """Put the blaster into learn mode and wait for a code to be captured."""
        blaster = self._get_entry().runtime_data

        if self.learn_task is None:
            self.learn_task = self.hass.async_create_task(
                blaster.async_learn_code(LEARN_TIMEOUT)
            )

        if not self.learn_task.done():
            return self.async_show_progress(
                step_id=step_id,
                progress_action="learn",
                progress_task=self.learn_task,
            )

        try:
            self._learned_code = self.learn_task.result()
        except HomeAssistantError:
            return self.async_show_progress_done(next_step_id="timed_out")

        return self.async_show_progress_done(next_step_id=next_step_id)

    async def async_step_timed_out(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        """Handle a learn timeout."""
        return self.async_abort(reason="learn_timeout")

    async def async_step_name(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        """Ask for a name for the newly learned command."""
        if user_input is not None:
            return self.async_create_entry(
                data={CONF_CODE: self._learned_code}, title=user_input[CONF_NAME]
            )

        return self.async_show_form(
            step_id="name",
            data_schema=vol.Schema({vol.Required(CONF_NAME): str}),
        )

    async def async_step_reconfigure_name(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        """Confirm the name for a re-learned command."""
        subentry = self._get_reconfigure_subentry()
        if user_input is not None:
            return self.async_update_and_abort(
                self._get_entry(),
                subentry,
                data={CONF_CODE: self._learned_code},
                title=user_input[CONF_NAME],
            )

        return self.async_show_form(
            step_id="reconfigure_name",
            data_schema=vol.Schema(
                {vol.Required(CONF_NAME, default=subentry.title): str}
            ),
        )
