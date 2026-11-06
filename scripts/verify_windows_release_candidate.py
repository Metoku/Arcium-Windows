"""Correlate fresh native-build, launch and packaging evidence before artifact upload.

This does not compile, install, sign or publish. These records describe trusted
CI execution; they are not cryptographic build attestations or interactive QA.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import stat
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def digest(path: Path) -> str:
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def read(path: Path) -> dict:
    value = json.loads(path.read_text(encoding='utf-8-sig'))
    if not isinstance(value, dict):
        raise ValueError(f'Expected an object in {path.name}')
    return value


def verify(repo: Path, build: Path, dist: Path, version: str, commit: str,
           build_report: Path, raw_smoke: Path, packaged_smoke: Path) -> dict:
    if not re.fullmatch(r'[0-9]+\.[0-9]+\.[0-9]+(?:-[A-Za-z0-9.-]+)?', version):
        raise ValueError('Invalid package version')
    if not re.fullmatch(r'[a-f0-9]{40}', commit):
        raise ValueError('Invalid integration commit')
    proof = read(build_report)
    expected = {'arcium_commit':(repo / 'upstream/arcium-core.sha').read_text().strip(),
                'windows_platform_commit':(repo / 'upstream/helium-windows.sha').read_text().strip(),
                'chromium_version':(repo / 'upstream/chromium-version.txt').read_text().strip(),
                'integration_commit':commit}
    if (proof.get('browser_compiled') is not True or
            proof.get('release_candidate_integrations') is not True or
            proof.get('status') != 'BROWSER_BINARY_CREATED_NOT_LAUNCHED' or
            any(proof.get(key) != value for key, value in expected.items())):
        raise ValueError('Native build does not match the exact integration and pinned sources')
    build = build.resolve(strict=True)
    executable = build / 'chrome.exe'
    binary_hash = digest(executable)
    if proof.get('browser_binary_bytes') != executable.stat().st_size:
        raise ValueError('Native executable size changed after build')
    for report in (raw_smoke, packaged_smoke):
        smoke = read(report)
        if (smoke.get('status') != 'HEADLESS_LAUNCH_PASSED' or
                smoke.get('browser_launched') is not True or
                smoke.get('isolated_profile_deleted') is not True or
                smoke.get('browser_sha256') != binary_hash):
            raise ValueError('Missing matching isolated launch evidence')
    name = f'Arcium-Windows-{version}'
    archive = dist / (name + '.zip')
    setup = dist / (name + '-Setup.exe')
    artifact_hashes = {}
    for artifact in (archive, setup):
        actual = digest(artifact)
        sidecar = Path(str(artifact) + '.sha256').read_text(encoding='utf-8-sig').strip()
        if sidecar != actual + '  ' + artifact.name:
            raise ValueError('Artifact checksum sidecar does not match')
        artifact_hashes[artifact.name] = actual
    packaged = {}
    with zipfile.ZipFile(archive) as package:
        for entry in package.infolist():
            if entry.is_dir():
                continue
            path = PurePosixPath(entry.filename)
            if (stat.S_ISLNK(entry.external_attr >> 16) or
                    not entry.filename.startswith(name + '/') or path.is_absolute() or
                    '..' in path.parts or '\\' in entry.filename or ':' in entry.filename or
                    path.as_posix() != entry.filename):
                raise ValueError('Unsafe packaged path')
            relative = PurePosixPath(*path.parts[1:]).as_posix()
            key = relative.casefold()
            if key in packaged or any(part.casefold() in ('default', 'user data', 'local state')
                                      for part in path.parts[1:]) or path.suffix.lower() in ('.csv', '.log'):
                raise ValueError('Duplicate or private packaged file')
            original = (repo / 'LICENSE' if relative == 'LICENSE.Arcium.txt' else build / relative)
            resolved = original.resolve(strict=True)
            if relative != 'LICENSE.Arcium.txt' and not resolved.is_relative_to(build):
                raise ValueError('Packaged file escapes the compiled runtime')
            with package.open(entry) as stream:
                packaged_hash = hashlib.file_digest(stream, 'sha256').hexdigest()
            if digest(resolved) != packaged_hash:
                raise ValueError(f'Packaged bytes differ from the compiled runtime: {relative}')
            packaged[key] = packaged_hash
    required = {'chrome.exe', 'chrome.dll', 'chrome_elf.dll', 'resources.pak',
                'chrome_100_percent.pak', 'locales/en-us.pak', 'license.arcium.txt'}
    if not required.issubset(packaged) or not {'v8_context_snapshot.bin', 'snapshot_blob.bin'} & packaged.keys():
        raise ValueError('Packaged runtime is incomplete')
    provenance = read(Path(str(setup) + '.json'))
    if (provenance.get('PackageVersion') != version or provenance.get('RuntimeVersion') != version or
            provenance.get('PortableFile') != archive.name or
            provenance.get('PortableSha256') != artifact_hashes[archive.name] or
            provenance.get('InstallerSha256') != artifact_hashes[setup.name] or
            provenance.get('DistributionCommit') != commit or
            provenance.get('Repository') != 'Metoku/Arcium-Windows'):
        raise ValueError('Installer provenance does not match this newly built runtime')
    return {'schema':1, 'status':'WINDOWS_RELEASE_CANDIDATE_VERIFIED', 'package_version':version,
            **expected, 'artifact_sha256':artifact_hashes, 'runtime_sha256':packaged,
            'native_compilation':True, 'isolated_launches':True,
            'interactive_acceptance':False, 'signed':False, 'published':False}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--version', required=True)
    parser.add_argument('--commit', required=True)
    parser.add_argument('--build-dir', type=Path, default=ROOT / 'work/windows-platform/build/src/out/Default')
    parser.add_argument('--dist', type=Path, default=ROOT / 'dist')
    parser.add_argument('--build-report', type=Path, default=ROOT / 'work/browser-only-build.json')
    parser.add_argument('--raw-smoke', type=Path, default=ROOT / 'work/browser-launch-smoke.json')
    parser.add_argument('--packaged-smoke', type=Path, default=ROOT / 'work/packaged-browser-smoke.json')
    args = parser.parse_args()
    try:
        result = verify(ROOT, args.build_dir, args.dist, args.version, args.commit,
                        args.build_report, args.raw_smoke, args.packaged_smoke)
        output = args.dist / f'Arcium-Windows-{args.version}-release-candidate.json'
        if output.exists():
            raise ValueError('Candidate receipt already exists')
        output.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    except (OSError, ValueError, KeyError, zipfile.BadZipFile) as error:
        parser.exit(1, f'{error}\n')
    print('WINDOWS_RELEASE_CANDIDATE_VERIFIED')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
