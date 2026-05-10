import subprocess
import logging
from config_loader import cfg

logger = logging.getLogger(__name__)

async def handle_multiroom(self, m):
    multi_cfg = getattr(cfg, 'multiroom', None)
    if not multi_cfg:
        return

    try:
        is_voice = False
        attachment_list = m.attachments
        for attachment in attachment_list:
            if attachment.filename.endswith('.ogg'):
                is_voice = True
                break

        path = None
        if is_voice:
            path = f"/tmp/{m.id}.ogg"
            await attachment_list[0].save(path)

        cmd = build_multiroom_command(multi_cfg, is_voice, path, m.content)

        subprocess.Popen(cmd, cwd=multi_cfg.working_dir)
        await m.add_reaction("✅")
        logger.info(f"Multiroom: Success for {m.author}")
    except Exception as e:
        logger.error(f"Multiroom Plugin Error: {e}")
        await m.add_reaction("❌")


def build_multiroom_command(multi_cfg, is_voice, path, content):
    cmd = [multi_cfg.python_bin, "-m", "tools.hub_messenger"]
    if is_voice:
        cmd.append("--ptt")
        cmd.append(path)
    else:
        cmd.append(content.strip())
    return cmd
