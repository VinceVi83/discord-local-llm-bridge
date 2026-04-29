import subprocess
import logging
from config_loader import cfg

logger = logging.getLogger(__name__)

async def handle_multiroom(self, m):
    multi_cfg = getattr(cfg, 'multiroom', None)
    if not multi_cfg:
        return

    try:
        is_v = False
        for attachment in m.attachments:
            if attachment.filename.endswith('.ogg'):
                is_v = True
                break

        if is_v:
            path = f"/tmp/{m.id}.ogg"
            await m.attachments[0].save(path)

        cmd = [multi_cfg.python_bin, "-m", "tools.hub_messenger"]
        if is_v:
            cmd.append("--ptt")
            cmd.append(path)
        else:
            cmd.append(m.content.strip())

        subprocess.Popen(cmd, cwd=multi_cfg.working_dir)
        await m.add_reaction("✅")
        logger.info(f"Multiroom: Success for {m.author}")
    except Exception as e:
        logger.error(f"Multiroom Plugin Error: {e}")
        await m.add_reaction("❌")
