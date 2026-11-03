from pathlib import Path


AUDIO_EXTENSIONS = {
    '.aac', '.aiff', '.flac', '.m4a', '.mp3', '.oga', '.ogg', '.opus', '.wav', '.weba'
}
TEXT_EXTENSIONS = {
    '.csv', '.json', '.log', '.md', '.text', '.txt', '.xml', '.yaml', '.yml'
}


def classify_attachment(filename, content_type=None, *, is_voice_message=False):
    if is_voice_message:
        return 'audio'

    suffix = Path(filename or '').suffix.lower()
    media_type = (content_type or '').split(';', 1)[0].strip().lower()

    if media_type.startswith('audio/') or suffix in AUDIO_EXTENSIONS:
        return 'audio'
    if media_type == 'application/pdf' or suffix == '.pdf':
        return 'pdf'
    if media_type.startswith('text/') or suffix in TEXT_EXTENSIONS:
        return 'text'
    return 'other'