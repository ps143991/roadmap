#!/usr/bin/env python3
"""Rebuild the vendored CodeMirror bundle from integrity-checked, pinned archives.

Python 3.10+ and network access are needed for development only. The default
builder is a pinned native Linux x86-64 esbuild binary; on another platform pass
--esbuild /path/to/an/esbuild-0.28.2-executable. Node and npm are not required.
The installed application uses only the finished JavaScript bundle, offline.
"""

import argparse
import base64
import hashlib
import io
import json
import platform
import shutil
import subprocess
import tarfile
import tempfile
from pathlib import Path
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
VENDOR = ROOT / 'vendor/codemirror'
LICENSE_NAMES = ('license', 'license.md', 'license.txt', 'copying')


def download_package(record, workspace):
    request = Request(record['source'], headers={'User-Agent': 'ThesisRoadmap-vendor-build'})
    with urlopen(request, timeout=60) as response:
        payload = response.read()
    algorithm, expected = record['integrity'].split('-', 1)
    actual = base64.b64encode(hashlib.new(algorithm, payload).digest()).decode()
    if actual != expected:
        raise ValueError(f"Archive integrity mismatch: {record['name']} {record['version']}")
    directory = workspace / 'node_modules' / record['name']
    directory.mkdir(parents=True)
    with tarfile.open(fileobj=io.BytesIO(payload), mode='r:gz') as archive:
        for member in archive.getmembers():
            relative = Path(member.name).relative_to('package')
            if not relative.parts:
                continue
            if '..' in relative.parts or not (member.isfile() or member.isdir()):
                raise ValueError(f"Unsafe archive entry: {record['name']} {member.name}")
            member.name = str(relative)
            archive.extract(member, directory)
    print(f"Verified {record['name']} {record['version']}", flush=True)
    return directory


def build(output, executable=None):
    lock = json.loads((VENDOR / 'dependencies.lock.json').read_text())
    packages = {record['name']: record for record in lock['packages']}
    builder = packages[lock['builder']]
    with tempfile.TemporaryDirectory(prefix='roadmap-codemirror-build-') as temporary:
        workspace = Path(temporary)
        licenses = []
        for record in lock['packages']:
            directory = download_package(record, workspace)
            if record['name'] == lock['builder']:
                continue
            license_files = [path for path in directory.iterdir() if path.name.lower() in LICENSE_NAMES]
            if len(license_files) != 1:
                raise ValueError(f"Expected one license file: {record['name']}")
            heading = f"{record['name']} {record['version']}\n" + '=' * 72 + '\n'
            licenses.append(heading + license_files[0].read_text().strip())
        native = executable or workspace / 'node_modules' / lock['builder'] / 'bin/esbuild'
        version = subprocess.check_output([str(native), '--version'], text=True).strip()
        if version != builder['version']:
            raise ValueError(f"Expected esbuild {builder['version']}, got {version}")
        entry = workspace / lock['entry']
        shutil.copy2(VENDOR / lock['entry'], entry)
        output.mkdir(parents=True, exist_ok=True)
        subprocess.run([str(native), str(entry), '--bundle', '--minify', '--format=iife', f"--global-name={lock['global']}", f"--target={lock['target']}", '--legal-comments=eof', f"--outfile={output / lock['output']}"], check=True)
        (output / 'LICENSES.txt').write_text('\n\n'.join(licenses) + '\n')
        actual = hashlib.sha256((output / lock['output']).read_bytes()).hexdigest()
        if actual != lock['bundle_sha256']:
            raise ValueError(f'Bundle differs from the pinned output: {actual}')
    print(f"Bundle: {output / lock['output']}")
    print(f'SHA-256: {actual}')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=VENDOR)
    parser.add_argument('--esbuild', type=Path, help='Use an existing native esbuild executable matching the pinned version')
    options = parser.parse_args()
    if not options.esbuild and (platform.system() != 'Linux' or platform.machine() not in ('x86_64', 'amd64')):
        parser.error('This platform needs --esbuild with a native executable matching the pinned version')
    build(options.output.resolve(), options.esbuild.resolve() if options.esbuild else None)


if __name__ == '__main__':
    main()
