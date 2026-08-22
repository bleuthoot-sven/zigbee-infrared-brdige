"""Wrapper around a ZHA-paired Zigbee IR blaster.

The blaster's `IRLearn`/`IRSend` commands and `last_learned_ir_code` attribute
are provided by the `ts1201.py` Zosung quirk in `zha-quirks`. ZHA does not
expose a public, documented way for another integration to be notified when a
learned code becomes available, so this module reaches directly into ZHA's
internal gateway/device objects to issue cluster commands and poll the
attribute. That coupling is confined to this module.
"""

import asyncio
import logging

from zigpy.types import EUI64
from zigpy.zcl import Cluster

from homeassistant.components.zha.helpers import (  # pylint: disable=home-assistant-component-root-import
    get_zha_gateway,
)
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError

from .const import (
    ATTR_LAST_LEARNED_IR_CODE,
    IR_CONTROL_CLUSTER_ID,
    IR_LEARN_COMMAND_ID,
    IR_SEND_COMMAND_ID,
    LEARN_POLL_INTERVAL,
)

_LOGGER = logging.getLogger(__name__)


class ZigbeeIrBlaster:
    """Learn and send IR codes through a ZHA-paired Zigbee IR blaster."""

    def __init__(self, hass: HomeAssistant, ieee: EUI64) -> None:
        """Initialize the IR blaster."""
        self._hass = hass
        self._ieee = ieee
        self._learn_lock = asyncio.Lock()

    def async_ensure_available(self) -> None:
        """Raise HomeAssistantError unless the IR blaster is currently reachable."""
        self._get_ir_control_cluster()

    def _get_ir_control_cluster(self) -> Cluster:
        """Return the zigpy IR control cluster for this device."""
        device = get_zha_gateway(self._hass).get_device(self._ieee)
        if device is None:
            raise HomeAssistantError(f"Zigbee device {self._ieee} is not available")
        for endpoint_id, endpoint in device.device.endpoints.items():
            if endpoint_id and IR_CONTROL_CLUSTER_ID in endpoint.in_clusters:
                return device.async_get_cluster(endpoint_id, IR_CONTROL_CLUSTER_ID)
        raise HomeAssistantError(
            f"Zigbee device {self._ieee} no longer exposes an IR control cluster"
        )

    async def _async_read_last_learned_code(self, cluster: Cluster) -> str:
        """Read the current value of the last-learned-code attribute."""
        success, _ = await cluster.read_attributes(
            [ATTR_LAST_LEARNED_IR_CODE], allow_cache=False
        )
        return success.get(ATTR_LAST_LEARNED_IR_CODE, "")

    async def async_learn_code(self, timeout: float) -> str:
        """Put the blaster into learn mode and wait for a new code.

        `last_learned_ir_code` is never cleared between learns, so a freshly
        learned code is detected as any value different from the one read
        before learn mode was enabled.
        """
        async with self._learn_lock:
            cluster = self._get_ir_control_cluster()
            baseline = await self._async_read_last_learned_code(cluster)
            await cluster.command(IR_LEARN_COMMAND_ID, on_off=True)
            try:
                async with asyncio.timeout(timeout):
                    while True:
                        await asyncio.sleep(LEARN_POLL_INTERVAL)
                        code = await self._async_read_last_learned_code(cluster)
                        if code and code != baseline:
                            return code
            except TimeoutError as err:
                raise HomeAssistantError(
                    "Timed out waiting for an IR code to be learned"
                ) from err
            finally:
                await cluster.command(IR_LEARN_COMMAND_ID, on_off=False)

    async def async_send_code(self, code: str) -> None:
        """Send a previously learned IR code."""
        cluster = self._get_ir_control_cluster()
        await cluster.command(IR_SEND_COMMAND_ID, code=code)
