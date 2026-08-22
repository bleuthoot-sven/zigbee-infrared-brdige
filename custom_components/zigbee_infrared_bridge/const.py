"""Constants for the Zigbee Infrared Bridge integration."""

from typing import Final

DOMAIN = "zigbee_infrared_bridge"

SUBENTRY_TYPE_COMMAND: Final = "command"

CONF_IEEE: Final = "ieee"

IR_CONTROL_CLUSTER_ID: Final = 0xE004
IR_LEARN_COMMAND_ID: Final = 0x01
IR_SEND_COMMAND_ID: Final = 0x02
ATTR_LAST_LEARNED_IR_CODE: Final = "last_learned_ir_code"

LEARN_TIMEOUT: Final = 30
LEARN_POLL_INTERVAL: Final = 1
