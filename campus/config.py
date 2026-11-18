from pathlib import Path
import os
import tomllib

ROOT = Path(__file__).resolve().parent.parent


class CampusError(Exception):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code

    def as_dict(self):
        return {'code': self.code, 'message': str(self)}


def load_config():
    path = Path(os.environ.get('AWE_CONFIG', ROOT / 'private/config.toml'))
    try:
        return tomllib.loads(path.read_text(encoding='utf-8-sig'))
    except FileNotFoundError:
        return {}
    except (ValueError, OSError):
        raise CampusError('invalid_config', '本地配置无法读取或 TOML 格式错误，请检查 private/config.toml。') from None


def local_path(value):
    path = Path(value)
    return path if path.is_absolute() else ROOT / path
