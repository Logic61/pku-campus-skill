"""Download the pinned official Windows release into this checkout, no global install."""
from pathlib import Path
import hashlib
import io
import json
import platform
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parent.parent
VERSION = '0.16.1'
URL = f'https://github.com/sshwy/pku3b/releases/download/{VERSION}/pku3b-{VERSION}-x86_64-pc-windows-msvc.zip'


def main():
    if platform.system() != 'Windows' or platform.machine().lower() not in ('amd64','x86_64'):
        raise SystemExit('This helper targets Windows x64. Configure blackboard.executable for your OS.')
    target = ROOT / 'bin/pku3b.exe'
    if target.exists():
        print('Existing bin/pku3b.exe retained; no overwrite.')
        return
    with urllib.request.urlopen(URL,timeout=60) as response:
        blob = response.read(60_000_001)
    if len(blob) > 60_000_000:
        raise SystemExit('Release archive exceeds size limit.')
    with zipfile.ZipFile(io.BytesIO(blob)) as archive:
        matches = [item for item in archive.infolist() if Path(item.filename).name == 'pku3b.exe']
        if len(matches) != 1 or matches[0].file_size > 100_000_000:
            raise SystemExit('Unexpected release archive.')
        binary = archive.read(matches[0])
    target.parent.mkdir(exist_ok=True)
    target.write_bytes(binary)
    metadata = {'version':VERSION,'url':URL,'sha256':hashlib.sha256(binary).hexdigest(),
                'note':'Local download fingerprint, not an independently published upstream checksum.'}
    (target.parent / 'pku3b-download.json').write_text(json.dumps(metadata,indent=2),encoding='utf-8')
    print(f'Installed project-local pku3b {VERSION}; SHA256 {metadata["sha256"]}')


if __name__ == '__main__':
    main()
