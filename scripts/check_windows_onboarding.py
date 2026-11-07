"""Validate first-run isolation and build the actual pinned onboarding frontend.

Used by the Windows source replay. This never launches a browser, copies a user
profile, or builds Chromium. The onboarding release includes its build tools.
"""
from __future__ import annotations

import ast
import configparser
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tarfile
import urllib.request
import xml.etree.ElementTree as ET

from scripts.apply_windows_arc_workflow import (
    ROOT, ONBOARDING_PATCH, SERVICES_PATCH, SERVICES_STRINGS_SOURCE, PROFILE_KEEP_ALIVE_PATCH,
    TAB_TOOLS_PATCH,
    git_apply, integrate, integrate_bundle,
    EXTERNAL_EXTENSION_SOURCE, LEGACY_EXTERNAL_EXTENSION_REGISTRY,
    EXTERNAL_EXTENSION_REGISTRY,
)
from scripts.check_windows_mac_buttons import MAC_PATCH, cpp_function
from scripts.check_windows_profile_keep_alive import (
    PROFILE_KEEP_ALIVE_CONSUMERS, verify_profile_keep_alive,
)
from scripts.check_windows_tab_tools import verify_tab_tools


ONBOARDING_ROOT = 'components/helium_onboarding'
ONBOARDING_API_FILES = (
    'chrome/install_static/install_constants.h',
    'chrome/install_static/install_util.cc',
    'chrome/common/chrome_paths_win.cc',
    'chrome/browser/ui/startup/startup_browser_creator_impl.cc',
)
BRANDING_API_FILES = (
    'tools/grit/grit/extern/tclib.py',
    'tools/grit/grit/extern/FP.py',
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
    declaration = next(line[1:] for line in ONBOARDING_PATCH.read_text().splitlines()
                       if line.startswith('+const wchar_t kRegistryExtensions[]'))
    extension_loader = source / 'chrome/browser/extensions/external_registry_loader_win.cc'
    if declaration not in extension_loader.read_text(encoding='utf-8'):
        raise RuntimeError('Arcium still shares an upstream external-extension registry root')
    startup = (source / ONBOARDING_API_FILES[-1]).read_text(encoding='utf-8')
    if ('if (!is_incognito_or_guest && !no_first_run)' not in startup or
            '!profile_->GetPrefs()->GetBoolean(prefs::kHeliumDidOnboarding)' not in startup or
            'GURL(chrome::kHeliumSetupURL)' not in startup):
        raise RuntimeError('The existing profile-scoped first-run route has changed')
    build = (source / ONBOARDING_ROOT / 'BUILD.gn').read_text(encoding='utf-8')
    build_action = build.split('action("build") {', 1)[1].split('action("grit")', 1)[0]
    for name in ('helium_onboarding_strings.grdp', 'src/pages/Welcome.svelte',
                 'src/pages/DataImport.svelte', 'src/pages/HeliumServices.svelte',
                 'src/lib/onboarding-flow.ts', 'src/components/PageNavigation.svelte'):
        if '"' + name + '"' not in build_action:
            raise RuntimeError(f'Onboarding incremental build input is missing: {name}')
    services = (source / 'chrome/browser/resources/settings/privacy_page/services_page.ts').read_text(
        encoding='utf-8')
    if "window.open('chrome://setup/?services=1', '_blank');" not in services:
        raise RuntimeError('Services settings does not open the dedicated consent route')
    strings = ET.parse(source / 'chrome/app/settings_strings.grdp').getroot()
    review_button = next(node for node in strings.iter('message')
                         if node.get('name') == 'IDS_SETTINGS_HELIUM_SERVICES_SETUP_PENDING_BUTTON')
    if ''.join(review_button.itertext()).strip() != 'Review services':
        raise RuntimeError('Services settings still directs completed profiles to first-run setup')
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
            'extension_registry_root_verified':True,
            'services_review_entry_verified':True,
            'incremental_asset_inputs_verified':True}


def build_onboarding_frontend(source: Path) -> dict:
    # Resolve Windows 8.3 aliases/junctions before passing both cwd and paths to
    # Node. Its ESM loader otherwise expands only one side of Vite's root.
    source = source.resolve(strict=True)
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


def check_services_branding(source: Path, postimages: dict[str, dict[str, bytes]],
                           core: Path) -> dict:
    """Replay the real release builder's branding before/after this catalog."""
    saved = {name:(source / name).read_bytes() for name in postimages['LF']}
    original_path = sys.path[:]
    checks = []
    try:
        sys.path.insert(0, str(core / 'utils'))
        spec = importlib.util.spec_from_file_location(
            'arcium_pinned_name_substitution', core / 'utils/name_substitution.py')
        branding = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(branding)
        if Path(branding.util.__file__).resolve() != (core / 'utils/name_substitution_utils.py').resolve():
            raise RuntimeError('Unexpected name-substitution utility loaded')
        branding.util.add_grit_to_path(source)
        for style, postimage in postimages.items():
            expected_old = None
            for applied_first in (False, True):
                for name, data in postimage.items():
                    (source / name).write_bytes(data)
                if not applied_first:
                    integrate(source, patch=SERVICES_PATCH, revert=True)
                    integrate(source, patch=TAB_TOOLS_PATCH, revert=True)
                strings = source / SERVICES_STRINGS_SOURCE
                # This is the exact function called by do_substitution in the
                # pinned Windows builder, including XML reserialization and
                # Chromium's real translation fingerprints. No GRIT mocks.
                branding.substitute_grit_file((strings, source, False, False))
                data = strings.read_bytes().replace(b'\r\n', b'\n')
                if style in ('CRLF', 'mixed'):
                    data = data.replace(b'\n', b'\r\n')
                strings.write_bytes(data)
                snapshot = lambda: {name:((source / name).read_bytes(),
                                          (source / name).stat().st_mtime_ns)
                                    for name in saved}
                before = snapshot()
                if not applied_first:
                    expected_old = {name:value[0] for name, value in before.items()}
                    if style == 'LF':
                        canonical = git_apply(source, SERVICES_PATCH, reverse=False, check=True)
                        if (not canonical.returncode or SERVICES_STRINGS_SOURCE not in canonical.stderr
                                or canonical.stderr.count('patch failed:') != 1):
                            raise RuntimeError('The reported post-branding strings failure was not reproduced')
                status = 'APPLIED' if applied_first else 'READY'
                if integrate(source, patch=TAB_TOOLS_PATCH) != status or snapshot() != before:
                    raise RuntimeError('Post-branding tab-tools check changed source or returned the wrong state')
                integrate(source, patch=TAB_TOOLS_PATCH, apply=True)
                before = snapshot()
                integrate(source, patch=TAB_TOOLS_PATCH, apply=True)
                if snapshot() != before:
                    raise RuntimeError('Post-branding tab-tools reapplication rewrote source')
                if integrate(source, patch=SERVICES_PATCH) != status or snapshot() != before:
                    raise RuntimeError('Post-branding services check changed source or returned the wrong state')
                integrate(source, patch=SERVICES_PATCH, apply=True)
                after = snapshot()
                integrate(source, patch=SERVICES_PATCH, apply=True)
                if snapshot() != after:
                    raise RuntimeError('Post-branding services reapplication rewrote source')
                integrate(source, patch=SERVICES_PATCH, revert=True)
                integrate(source, patch=TAB_TOOLS_PATCH, revert=True)
                if {name:value[0] for name, value in snapshot().items()} != expected_old:
                    raise RuntimeError('Services reversion did not preserve the builder branding exactly')
                strings.write_bytes(strings.read_bytes().replace(
                    b'Arcium services are not available', b'Unknown consent message', 1))
                edited = snapshot()
                try:
                    integrate(source, patch=SERVICES_PATCH, apply=True)
                except RuntimeError:
                    pass
                else:
                    raise RuntimeError('Services branding fallback accepted unknown consent copy')
                if snapshot() != edited:
                    raise RuntimeError('Rejected post-branding application changed source')
                checks.append({'endings':style, 'branding_after_apply':applied_first})
        return {'status':'PINNED_BUILDER_BRANDING_REPLAY_PASSED', 'checks':checks,
                'tab_tools_branding_verified':True,
                'reported_failure_reproduced':True, 'unknown_copy_rejected':True,
                'pinned_utility_sha256':{
                    name:hashlib.sha256((core / 'utils' / name).read_bytes()).hexdigest()
                    for name in ('name_substitution.py', 'name_substitution_utils.py')},
                'grit_sha256':{name:hashlib.sha256((source / name).read_bytes()).hexdigest()
                               for name in BRANDING_API_FILES}}
    finally:
        sys.path[:] = original_path
        for name, data in saved.items():
            if (source / name).read_bytes() != data:
                (source / name).write_bytes(data)


def check_onboarding(source: Path, originals: dict[str, bytes],
                     catalogs: tuple[Path, ...], assets: dict, core: Path) -> dict:
    """Exercise fresh/already-patched bundles and retain native build output."""
    checks, postimages, proof, frontend = [], {}, None, None
    upgrades = []
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
        others = (*catalogs, MAC_PATCH, PROFILE_KEEP_ALIVE_PATCH, TAB_TOOLS_PATCH)
        for order in ((ONBOARDING_PATCH, SERVICES_PATCH, *others),
                      (*others, SERVICES_PATCH, ONBOARDING_PATCH)):
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
                proof['profile_keep_alive'] = verify_profile_keep_alive(
                    source, compile_cpp=True, consumers=PROFILE_KEEP_ALIVE_CONSUMERS)
                proof['tab_tools'] = verify_tab_tools(source)
                frontend = build_onboarding_frontend(source)
                # Unknown extension roots must not be silently replaced.
                path = source / EXTERNAL_EXTENSION_SOURCE
                fixed = path.read_bytes()
                path.write_bytes(fixed.replace(EXTERNAL_EXTENSION_REGISTRY,
                                                EXTERNAL_EXTENSION_REGISTRY.replace(
                                                    b'Arcium', b'CustomBrowser'), 1))
                unknown = {name:(source / name).read_bytes() for name in originals}
                try:
                    integrate(source, patch=ONBOARDING_PATCH, apply=True)
                except RuntimeError:
                    pass
                else:
                    raise RuntimeError('Onboarding accepted an unknown extension root')
                if unknown != {name:(source / name).read_bytes() for name in originals}:
                    raise RuntimeError('Rejected onboarding application changed source')
                path.write_bytes(fixed)
                proof['unknown_extension_root_rejected'] = True
            if style not in upgrades:
                # A user may already have applied the first published version.
                path = source / EXTERNAL_EXTENSION_SOURCE
                fixed = path.read_bytes()
                path.write_bytes(fixed.replace(EXTERNAL_EXTENSION_REGISTRY,
                                               LEGACY_EXTERNAL_EXTENSION_REGISTRY, 1))
                timestamps = {name:(source / name).stat().st_mtime_ns for name in originals}
                if integrate(source, patch=ONBOARDING_PATCH) != 'UPDATE_AVAILABLE':
                    raise RuntimeError('Earlier onboarding catalog was not recognized')
                if timestamps != {name:(source / name).stat().st_mtime_ns for name in originals}:
                    raise RuntimeError('Read-only onboarding upgrade check changed source')
                integrate_bundle(source, apply=True)
                if postimage != {name:(source / name).read_bytes() for name in originals}:
                    raise RuntimeError('Earlier onboarding catalog did not upgrade exactly')
                if any((source / name).stat().st_mtime_ns != stamp
                       for name, stamp in timestamps.items() if name != EXTERNAL_EXTENSION_SOURCE):
                    raise RuntimeError('Onboarding upgrade rewrote unrelated source')
                upgrades.append(style)
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
    branding = check_services_branding(source, postimages, core)
    if sentinel.read_bytes() != sentinel_bytes or sentinel.stat().st_mtime_ns != sentinel_time:
        raise RuntimeError('Services branding check changed an existing browser profile')
    return {'status':'ONBOARDING_REPLAY_AND_FRONTEND_CHECKS_PASSED',
            'assets':assets, 'checks':checks, 'native_contracts':proof,
            'earlier_version_upgrades':upgrades,
            'frontend':frontend, 'services_branding':branding, 'existing_profile_retained':True,
            'browser_compiled':False, 'windows_runtime_verified':False}
