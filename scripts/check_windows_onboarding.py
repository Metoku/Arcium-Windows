"""Validate first-run isolation and build the actual pinned onboarding frontend.

Used by the Windows source replay. This never launches a browser, copies a user
profile, or builds Chromium. The onboarding release includes its build tools.
"""
from __future__ import annotations

import ast
import configparser
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tarfile
import urllib.request

from scripts.apply_windows_arc_workflow import (
    ROOT, ONBOARDING_PATCH, integrate, integrate_bundle,
)
from scripts.check_windows_mac_buttons import MAC_PATCH, cpp_function


ONBOARDING_ROOT = 'components/helium_onboarding'
ONBOARDING_API_FILES = (
    'chrome/install_static/install_constants.h',
    'chrome/install_static/install_util.cc',
    'chrome/common/chrome_paths_win.cc',
    'chrome/browser/ui/startup/startup_browser_creator_impl.cc',
)


def prepare_onboarding_assets(core: Path, source: Path,
                              archive: Path | None = None) -> dict:
    """Verify the core-pinned archive before extracting in the temporary source."""
    config = configparser.ConfigParser()
    config.read(core / 'deps.ini', encoding='utf-8')
    onboarding = config['onboarding']
    digest = onboarding['sha256']
    if not re.fullmatch(r'[a-f0-9]{64}', digest):
        raise ValueError('Invalid onboarding dependency digest')
    if onboarding['output_path'] != './' + ONBOARDING_ROOT:
        raise ValueError('Unknown onboarding extraction directory')
    url = onboarding['url']
    if not url.startswith('https://github.com/imputnet/helium-onboarding/releases/download/'):
        raise ValueError('Unknown onboarding dependency source')
    if archive is None:
        archive = source.parent / 'onboarding.tar.gz'
        with urllib.request.urlopen(url, timeout=60) as response, archive.open('wb') as output:
            shutil.copyfileobj(response, output)
    actual = hashlib.sha256(archive.read_bytes()).hexdigest()
    if actual != digest:
        raise ValueError('Onboarding dependency SHA256 mismatch')
    destination = source / ONBOARDING_ROOT
    destination.mkdir(parents=True, exist_ok=True)
    with tarfile.open(archive, 'r:gz') as package:
        # Python's data filter rejects absolute/traversing paths and escaping
        # links. The verified archive bundles platform-specific Node modules.
        package.extractall(destination, filter='data')
    if not (destination / 'node_modules/svelte/package.json').is_file():
        raise ValueError('Pinned onboarding archive is missing its build tools')
    return {'version':onboarding['version'], 'sha256':actual, 'url':url}


def verify_native_sources(source: Path) -> dict:
    fixture = json.loads((ROOT / 'tests/fixtures/windows_onboarding_native.json').read_text())
    for name, expected in fixture['headers'].items():
        if (source / name).read_text(encoding='utf-8').rstrip() != expected.rstrip():
            raise RuntimeError(f'Onboarding compiler header differs from pinned source: {name}')
    count = 0
    for name, functions in fixture['functions'].items():
        text = (source / name).read_text(encoding='utf-8')
        for signature, expected in functions.items():
            if cpp_function(text, signature) != expected:
                raise RuntimeError(f'Onboarding compiler body differs from pinned source: {signature}')
            count += 1
    policy = source / 'components/policy/tools/generate_policy_source.py'
    tree = ast.parse(policy.read_text(encoding='utf-8'))
    values = [ast.literal_eval(node.value) for node in tree.body
              if isinstance(node, ast.Assign) and any(
                  isinstance(target, ast.Name) and target.id == 'CHROMIUM_POLICY_KEY'
                  for target in node.targets)]
    if values != [r'SOFTWARE\\Policies\\Arcium']:
        raise RuntimeError('Arcium still shares an upstream Windows policy root')
    startup = (source / ONBOARDING_API_FILES[-1]).read_text(encoding='utf-8')
    if ('if (!is_incognito_or_guest && !no_first_run)' not in startup or
            '!profile_->GetPrefs()->GetBoolean(prefs::kHeliumDidOnboarding)' not in startup or
            'GURL(chrome::kHeliumSetupURL)' not in startup):
        raise RuntimeError('The existing profile-scoped first-run route has changed')
    build = (source / ONBOARDING_ROOT / 'BUILD.gn').read_text(encoding='utf-8')
    build_action = build.split('action("build") {', 1)[1].split('action("grit")', 1)[0]
    for name in ('helium_onboarding_strings.grdp', 'src/pages/Welcome.svelte',
                 'src/pages/DataImport.svelte'):
        if '"' + name + '"' not in build_action:
            raise RuntimeError(f'Onboarding incremental build input is missing: {name}')
    if not (shutil.which('g++') or shutil.which('c++')):
        raise RuntimeError('A C++ compiler is required for onboarding path contracts')
    result = subprocess.run([sys.executable, '-m', 'unittest',
                             'tests.test_windows_onboarding', '-v'], cwd=ROOT,
                            text=True, encoding='utf-8', capture_output=True)
    if result.returncode or 'skipped=' in result.stderr:
        raise RuntimeError('Native onboarding contracts failed:\n' + result.stdout + result.stderr)
    return {'header_bodies_verified':len(fixture['headers']),
            'function_bodies_verified':count, 'cpp_contracts_passed':True,
            'first_run_route_verified':True, 'policy_root_verified':True,
            'incremental_asset_inputs_verified':True}


def build_onboarding_frontend(source: Path) -> dict:
    root = source / ONBOARDING_ROOT
    output = source.parent / 'onboarding-dist'
    header = source.parent / 'onboarding-localized.h'
    commands = [
        ['node', 'util/generate-i18n.mts', str(header)],
        ['node', 'node_modules/svelte-check/bin/svelte-check', '--tsconfig', './tsconfig.app.json'],
        ['node', 'node_modules/typescript/bin/tsc', '-p', 'tsconfig.node.json'],
        # Upstream uses short real timer deadlines in its controller tests.
        # Run files serially so competing Svelte/compiler workers cannot expire
        # a pending-operation test while its setImmediate callback is paused.
        ['node', '--test', '--test-concurrency=1',
         *[str(p.relative_to(root)) for p in sorted((root / 'tests').glob('*.test.mjs'))]],
        ['node', 'node_modules/vite/bin/vite.js', 'build', '--outDir', str(output)],
        ['node', 'util/generate-grd.mts', str(output), str(source.parent / 'onboarding-resources.grd')],
    ]
    checks = []
    for command in commands:
        result = subprocess.run(command, cwd=root, text=True, encoding='utf-8',
                                errors='replace', capture_output=True, timeout=180)
        if result.returncode:
            raise RuntimeError('Pinned onboarding frontend check failed (' +
                               ' '.join(command[:3]) + '):\n' + result.stdout + result.stderr)
        checks.append({'command':command[:3], 'status':'PASSED',
                       'summary':(result.stdout + result.stderr).splitlines()[-12:]})
    native_keys = header.read_text(encoding='utf-8')
    for key in ('windowsProfileNotice', 'windowsPasswordNote', 'windowsPasswordImport'):
        if key not in native_keys:
            raise RuntimeError(f'Onboarding localized key was not generated: {key}')
    if not (output / 'index.html').is_file():
        raise RuntimeError('Onboarding frontend build has no entry page')
    return {'status':'ONBOARDING_FRONTEND_BUILT_AND_TYPECHECKED', 'checks':checks,
            'browser_compiled':False}


def check_onboarding(source: Path, originals: dict[str, bytes],
                     catalogs: tuple[Path, ...], assets: dict) -> dict:
    """Exercise fresh/already-patched bundles and retain native build output."""
    checks, postimages, proof, frontend = [], {}, None, None
    sentinel = source.parent / 'existing-helium-profile/Default/Preferences'
    sentinel.parent.mkdir(parents=True)
    sentinel.write_bytes(b'{"extensions":{"settings":{"existing-extension":{}}}}')
    sentinel_bytes, sentinel_time = sentinel.read_bytes(), sentinel.stat().st_mtime_ns
    for style in ('LF', 'CRLF', 'mixed', 'missing-final-newline'):
        baseline = {}
        for index, (name, data) in enumerate(sorted(originals.items())):
            data = data.replace(b'\r\n', b'\n')
            if style == 'CRLF' or (style == 'mixed' and index % 2):
                data = data.replace(b'\n', b'\r\n')
            if style == 'missing-final-newline':
                data = data.removesuffix(b'\n')
            baseline[name] = data
            (source / name).write_bytes(data)
        others = (*catalogs, MAC_PATCH)
        for order in ((ONBOARDING_PATCH, *others), (*others, ONBOARDING_PATCH)):
            for patch in order:
                times = {name:(source / name).stat().st_mtime_ns for name in originals}
                if integrate(source, patch=patch) != 'READY':
                    raise RuntimeError(f'Onboarding coexistence check not ready: {patch.name}')
                if times != {name:(source / name).stat().st_mtime_ns for name in originals}:
                    raise RuntimeError('Read-only onboarding check rewrote source')
                integrate(source, patch=patch, apply=True)
            postimage = {name:(source / name).read_bytes() for name in originals}
            if style in postimages and postimages[style] != postimage:
                raise RuntimeError('Onboarding result depends on catalog application order')
            postimages[style] = postimage
            if proof is None:
                proof = verify_native_sources(source)
                frontend = build_onboarding_frontend(source)
            times = {name:(source / name).stat().st_mtime_ns for name in originals}
            # --feature all must recognize previously installed catalogs, add
            # onboarding atomically, and coexist with optional Mac captions.
            if integrate_bundle(source, apply=True) != 'APPLIED':
                raise RuntimeError('Full bundle did not recognize first-run integration')
            if times != {name:(source / name).stat().st_mtime_ns for name in originals}:
                raise RuntimeError('Idempotent first-run application rewrote source')
            for patch in reversed(order):
                integrate(source, patch=patch, revert=True)
            if baseline != {name:(source / name).read_bytes() for name in originals}:
                raise RuntimeError('Onboarding revert did not restore exact source bytes')
            if sentinel.read_bytes() != sentinel_bytes or sentinel.stat().st_mtime_ns != sentinel_time:
                raise RuntimeError('First-run patch helper changed an existing browser profile')
            checks.append({'endings':style, 'order':[p.name for p in order]})
    return {'status':'ONBOARDING_REPLAY_AND_FRONTEND_CHECKS_PASSED',
            'assets':assets, 'checks':checks, 'native_contracts':proof,
            'frontend':frontend, 'existing_profile_retained':True,
            'browser_compiled':False, 'windows_runtime_verified':False}
