"""Create a separate, resumable display variant; preserve all source score/PNG files."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import time
from PIL import Image


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def atomic_json(path, data):
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(json.dumps(data, indent=2), encoding='utf-8')
    temporary.replace(path)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, default=Path('build/new-york'))
    parser.add_argument('--output', type=Path, default=Path('build/new-york-display'))
    parser.add_argument('--minzoom', type=int, default=5)
    parser.add_argument('--report', type=Path, default=Path('qa-artifacts/ny/display-overviews.json'))
    args = parser.parse_args(); started = time.monotonic()
    source, output = args.source.resolve(), args.output.resolve()
    assert source != output and source not in output.parents and output not in source.parents
    manifest_path = source / 'manifest.json'
    manifest = json.loads(manifest_path.read_text())
    assert 0 <= args.minzoom < manifest['minzoom']
    metadata_name = f"datasets/{manifest['dataset']}/metadata.json"
    identity = {'source': str(source), 'output': str(output), 'source_manifest_sha256': sha(manifest_path),
                'original_minzoom': manifest['minzoom'], 'minzoom': args.minzoom,
                'script_sha256': sha(__file__), 'app_sha256': sha('web/app.js'), 'style_sha256': sha('web/style.css')}
    state = args.report.with_name(args.report.stem + '.state.json')
    state.parent.mkdir(parents=True, exist_ok=True)
    if output.exists():
        assert state.exists() and json.loads(state.read_text()) == identity, 'Display resume provenance mismatch'
    else:
        atomic_json(state, identity); output.mkdir(parents=True)
    linked = copied = 0
    # Keep bulky immutable payloads as same-volume hard links. Never write an
    # existing PNG/raw payload; modified manifests and client files are separate.
    for path in source.rglob('*'):
        if not path.is_file():
            continue
        relative = path.relative_to(source)
        if relative.as_posix() in {'manifest.json', metadata_name, 'app.js', 'style.css'}:
            continue
        target = output / relative; target.parent.mkdir(parents=True, exist_ok=True)
        if path.suffix in {'.png', '.f32'}:
            if target.exists():
                assert os.path.samefile(path, target), f'Unexpected display payload: {target}'
            else:
                os.link(path, target)
            linked += 1
        else:
            if target.exists():
                assert sha(path) == sha(target), f'Display copy changed: {target}'
            else:
                shutil.copy2(path, target)
            copied += 1
        if (linked + copied) % 5000 == 0:
            print(json.dumps({'linked_payloads': linked, 'copied_files': copied}), flush=True)
    tile_root = output / 'datasets' / manifest['dataset'] / 'tiles'
    current = {tuple(map(int, key.split('/')[1:])) for key in manifest['available_tiles']
               if int(key.split('/')[0]) == manifest['minzoom']}
    additions = {}
    for z in range(manifest['minzoom'] - 1, args.minzoom - 1, -1):
        parents = {(x // 2, y // 2) for x, y in current}
        for tx, ty in sorted(parents):
            canvas = Image.new('RGBA', (512, 512))
            for dx in range(2):
                for dy in range(2):
                    child = tile_root / str(z + 1) / str(tx * 2 + dx) / f'{ty * 2 + dy}.png'
                    if child.exists():
                        with Image.open(child) as image:
                            canvas.paste(image, (dx * 256, dy * 256))
            target = tile_root / str(z) / str(tx) / f'{ty}.png'
            target.parent.mkdir(parents=True, exist_ok=True)
            temporary = target.with_suffix('.tmp')
            canvas.resize((256, 256), Image.Resampling.LANCZOS).save(temporary, format='PNG', optimize=True)
            digest = sha(temporary)
            if target.exists():
                assert sha(target) == digest, 'Resumed overview differs'
                temporary.unlink()
            else:
                temporary.replace(target)
            additions[f'{z}/{tx}/{ty}'] = {'bytes': target.stat().st_size, 'sha256': digest}
        current = parents
    for name in ['app.js', 'style.css']:
        shutil.copy2(Path('web') / name, output / name)
    # The loose comparison viewer also loads this script, even without archives.
    for original, target in [('.tools/pmtiles/js/node_modules/pmtiles/dist/pmtiles.js', 'vendor/pmtiles.js'),
                             ('deploy/licenses/PMTILES-LICENSE.txt', 'vendor/PMTILES-LICENSE.txt'),
                             ('.tools/pmtiles/js/node_modules/fflate/LICENSE', 'vendor/FFLATE-LICENSE.txt')]:
        shutil.copy2(original, output / target)
    manifest['minzoom'] = args.minzoom
    manifest['min_view_zoom'] = 3
    manifest['available_tiles'] = sorted(manifest['available_tiles'] + list(additions))
    manifest['tiles'] = len(manifest['available_tiles'])
    manifest['display_derivation'] = {**identity, 'source': str(args.source), 'output': str(args.output),
        'resampling': 'Existing RGBA PNG parents, Pillow LANCZOS; original z7-z14 and all analytical payloads unchanged'}
    atomic_json(output / metadata_name, manifest)
    atomic_json(output / 'manifest.json', manifest)
    assert sha(manifest_path) == identity['source_manifest_sha256']
    for path in source.rglob('*'):
        if path.is_file() and path.suffix in {'.png', '.f32'}:
            assert os.path.samefile(path, output / path.relative_to(source)), 'Source payload replaced'
    files = [p for p in output.rglob('*') if p.is_file()]
    report = {**identity, 'dataset': manifest['dataset'], 'scores_sha256': manifest['scores_sha256'],
              'linked_original_payloads': linked, 'copied_original_files': copied,
              'added_tiles': additions, 'added_tile_bytes': sum(v['bytes'] for v in additions.values()),
              'tiles': manifest['tiles'], 'files': len(files), 'bytes': sum(p.stat().st_size for p in files),
              'source_manifest_unchanged': True, 'source_payload_inodes_unchanged': True,
              'seconds': time.monotonic() - started}
    atomic_json(args.report, report)
    print(json.dumps(report), flush=True)


if __name__ == '__main__':
    main()
