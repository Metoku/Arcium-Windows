"""Inspect real ICO/PE representations without Windows APIs or extra packages."""
import argparse
import hashlib
import json
from pathlib import Path
import struct


def icon_sizes(data, *, group=False):
    reserved, kind, count = struct.unpack_from('<HHH', data)
    if reserved != 0 or kind != 1 or not 1 <= count <= 64:
        raise ValueError('Invalid icon directory')
    stride = 14 if group else 16
    if len(data) < 6 + count * stride:
        raise ValueError('Truncated icon directory')
    sizes = set()
    for index in range(count):
        offset = 6 + index * stride
        width, height = struct.unpack_from('<BB', data, offset)
        size = (width or 256, height or 256)
        sizes.add(size)
        if not group:
            length, start = struct.unpack_from('<II', data, offset + 8)
            image = data[start:start + length]
            if len(image) != length or image[:8] != b'\x89PNG\r\n\x1a\n':
                raise ValueError('Expected a complete PNG icon representation')
            if struct.unpack_from('>II', image, 16) != size or image[24:26] != b'\x08\x06':
                raise ValueError('Icon representation must retain its dimensions and RGBA alpha')
    return sizes


def pe_icon_groups(data):
    pe = struct.unpack_from('<I', data, 0x3C)[0]
    if data[:2] != b'MZ' or data[pe:pe + 4] != b'PE\0\0':
        raise ValueError('Expected a PE executable')
    sections, optional_size = struct.unpack_from('<H12xH', data, pe + 6)
    optional = pe + 24
    magic = struct.unpack_from('<H', data, optional)[0]
    if magic not in (0x10B, 0x20B):
        raise ValueError('Unsupported PE optional header')
    directories = optional + (112 if magic == 0x20B else 96)
    resource_rva, _ = struct.unpack_from('<II', data, directories + 16)
    if not resource_rva:
        return {}

    def file_offset(rva):
        for index in range(sections):
            section = optional + optional_size + index * 40
            virtual_size, virtual, raw_size, raw = struct.unpack_from('<IIII', data, section + 8)
            if virtual <= rva < virtual + max(virtual_size, raw_size):
                offset = raw + rva - virtual
                if offset >= len(data):
                    raise ValueError('PE resource points outside the file')
                return offset
        raise ValueError('PE resource RVA has no section')

    base = file_offset(resource_rva)

    def children(directory):
        named, numbered = struct.unpack_from('<HH', data, base + directory + 12)
        if named + numbered > 65536:
            raise ValueError('Invalid resource directory')
        return [struct.unpack_from('<II', data, base + directory + 16 + index * 8)
                for index in range(named + numbered)]

    groups = {}
    for kind, kind_offset in children(0):
        if kind != 14:  # RT_GROUP_ICON
            continue
        for name, name_offset in children(kind_offset & 0x7FFFFFFF):
            for language, entry in children(name_offset & 0x7FFFFFFF):
                if entry & 0x80000000:
                    raise ValueError('Unexpected resource directory depth')
                rva, length = struct.unpack_from('<II', data, base + entry)
                start = file_offset(rva)
                groups[f'{name}:{language}'] = icon_sizes(data[start:start + length], group=True)
    return groups


def verify_installed_icons(root, setup, source):
    source_bytes = source.read_bytes()
    expected = icon_sizes(source_bytes)
    icon_name = 'Arcium-' + hashlib.sha256(source_bytes).hexdigest()[:16] + '.ico'
    installed = root / 'icons' / icon_name
    if installed.read_bytes() != source_bytes:
        raise AssertionError('Installed icon differs from the complete source ICO')
    launcher = pe_icon_groups((root / 'Arcium.exe').read_bytes())
    setup_icons = pe_icon_groups(setup.read_bytes())
    if not any(expected <= sizes for sizes in launcher.values()):
        raise AssertionError('Launcher discarded one or more high-DPI icon representations')
    if not any({(16, 16), (32, 32), (48, 48), (256, 256)} <= sizes for sizes in setup_icons.values()):
        raise AssertionError('Setup is missing a complete small/large icon group')
    return {
        'icon_file': icon_name,
        'installed_icon_sha256': hashlib.sha256(installed.read_bytes()).hexdigest(),
        'ico_sizes': sorted(expected),
        'launcher_groups': {key: sorted(value) for key, value in launcher.items()},
        'setup_groups': {key: sorted(value) for key, value in setup_icons.items()},
        'status': 'HIGH_DPI_ICONS_PASSED',
    }


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--installed-root', required=True, type=Path)
    parser.add_argument('--setup', required=True, type=Path)
    parser.add_argument('--report', required=True, type=Path)
    args = parser.parse_args()
    source = Path(__file__).resolve().parents[1] / 'installer/windows/assets/Arcium.ico'
    result = verify_installed_icons(args.installed_root, args.setup, source)
    args.report.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result))
