#!/usr/bin/env python3
"""Build the portable per-user installer archive from an explicit file list."""

import argparse
import hashlib
import shutil
import tarfile
import tempfile
from pathlib import Path

from roadmap_packaging import DISTRIBUTION_FILES, copy_application

ROOT = Path(__file__).resolve().parent


def build(output):
    output.mkdir(parents=True, exist_ok=True)
    version = (ROOT / 'VERSION').read_text().strip()
    with tempfile.TemporaryDirectory(prefix='thesis-roadmap-build-') as workspace:
        source = Path(workspace) / f'roadmap-{version}'
        copy_application(ROOT, source)
        for name in DISTRIBUTION_FILES:
            shutil.copy2(ROOT / name, source / name)
        shutil.copytree(ROOT / 'docs', source / 'docs')
        shutil.copytree(ROOT / 'tests', source / 'tests', ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
        archive = output / f'roadmap-{version}.tar.gz'
        with tarfile.open(archive, 'w:gz') as stream:
            stream.add(source, arcname=source.name)
    checksum = output / f'{archive.name}.sha256'
    checksum.write_text(f'{hashlib.sha256(archive.read_bytes()).hexdigest()}  {archive.name}\n')
    print(archive)
    print(checksum)
    return archive


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT / 'dist')
    options = parser.parse_args()
    build(options.output.resolve())


if __name__ == '__main__':
    main()
