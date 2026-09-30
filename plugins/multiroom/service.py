import subprocess
import logging
from common.conf_manager import cfg, Utils

logger = logging.getLogger(__name__)

async def handle_multiroom(self, m):
    try:
        Utils.send_command_multiroom('system', m.content)
        await m.add_reaction("✅")
        logger.info(f"Multiroom: Success for {m.author}")
    except Exception as e:
        logger.error(f"Multiroom Plugin Error: {e}")
        await m.add_reaction("❌")
