"""Request log paths and payload redaction."""
from pathlib import Path

def request_log_root(db_path):
    """Use project logs beside data; standalone databases keep adjacent logs."""
    directory = Path(db_path).resolve().parent
    project = directory.parent if directory.name == 'data' else directory
    return project / 'logs' / 'ds-requests'


def sanitize(value):
    if isinstance(value, dict):
        if value.get('type') in ('image_url', 'input_image', 'image'):
            return {'type': value['type']}
        return {k: sanitize(v) for k,v in value.items()}
    if isinstance(value, list):
        return [sanitize(v) for v in value]
    return value
