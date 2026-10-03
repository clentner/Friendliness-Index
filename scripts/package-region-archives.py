"""Package disjoint overview/detail PMTiles with resumable immutable part views."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import runpy
import sys
import time


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, default=Path('build/new-york-display'))
    parser.add_argument('--report', type=Path, default=Path('qa-artifacts/ny/archives/package.json'))
    args = parser.parse_args(); started = time.monotonic()
    source = args.source.resolve(); manifest = json.loads((source / 'manifest.json').read_text())
    dataset = manifest['dataset']; expected = set(manifest['available_tiles'])
    assert len(expected) == manifest['tiles'] and manifest['minzoom'] == 5 and manifest['maxzoom'] == 14
    results = []; inventory = {}; payload_bytes = 0
    for name, low, high in [('overview', 5, 12), ('detail', 13, 14)]:
        keys = sorted(key for key in expected if low <= int(key.split('/')[0]) <= high)
        view = Path('build/ny-archive-parts') / name
        part_manifest = {**manifest, 'available_tiles': keys, 'tiles': len(keys), 'minzoom': low, 'maxzoom': high,
                         'archive_partition': {'id': name, 'minzoom': low, 'maxzoom': high,
                             'full_source_manifest_sha256': sha(source / 'manifest.json')}}
        view.mkdir(parents=True, exist_ok=True)
        part_manifest_path = view / 'manifest.json'
        if part_manifest_path.exists():
            assert json.loads(part_manifest_path.read_text()) == part_manifest, 'Part provenance changed'
        else:
            part_manifest_path.write_text(json.dumps(part_manifest), encoding='utf-8')
        part_bytes = 0
        for key in keys:
            relative = Path('datasets') / dataset / 'tiles' / (key + '.png')
            original, target = source / relative, view / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            if target.exists():
                assert os.path.samefile(original, target), 'Part payload replaced'
            else:
                os.link(original, target)
            part_bytes += original.stat().st_size
        # Exact final size is checked below; this preflight leaves ample room
        # for the measured NY directory/metadata overhead.
        assert part_bytes < 500_000_000, 'Part requires a smaller bounded partition'
        archive = Path('build/archives') / f'new-york-{dataset}-{name}.pmtiles'
        report_path = args.report.parent / name / 'package.json'
        if archive.exists():
            assert report_path.exists(), 'Inspect archive without a completed report before resuming'
            part = json.loads(report_path.read_text())
            assert sha(archive) == part['archive_sha256'] and archive.stat().st_size == part['archive_bytes']
            assert part['metadata']['source_manifest_sha256'] == sha(part_manifest_path)
        else:
            previous = sys.argv
            try:
                sys.argv = ['scripts/package-raster.py', str(view), str(archive), '--report', str(report_path)]
                runpy.run_path('scripts/package-raster.py', run_name='__main__')
            finally:
                sys.argv = previous
            part = json.loads(report_path.read_text())
        assert part['archive_bytes'] <= 512_000_000
        members = json.loads(report_path.with_name('tile-inventory.json').read_text())
        assert set(members) == set(keys) and not (set(members) & set(inventory))
        inventory.update({key: {**value, 'part': name} for key, value in members.items()})
        payload_bytes += part_bytes
        results.append({**part, 'id': name, 'minzoom': low, 'maxzoom': high,
                        'report': str(report_path), 'archive_file': archive.name})
        print(json.dumps({'completed_part': name, 'tiles': len(keys), 'archive_bytes': part['archive_bytes']}), flush=True)
    assert set(inventory) == expected
    assert any('zero_color_blue' in part['pixel_examples'] for part in results), 'Native zero-color evidence required across the complete archive set'
    report = {'dataset': dataset, 'source': str(source), 'source_manifest_sha256': sha(source / 'manifest.json'),
              'archive_layout': 'zoom-partitions-v1', 'parts': results, 'internal_tiles': len(inventory),
              'source_png_bytes': payload_bytes, 'archive_objects': len(results),
              'archive_bytes_total': sum(part['archive_bytes'] for part in results),
              'verified_byte_for_byte': sum(part['verified_byte_for_byte'] for part in results),
              'seconds': time.monotonic() - started}
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2))
    args.report.with_name('tile-inventory.json').write_text(json.dumps(inventory))
    config = {'dataset': dataset, 'archive_layout': report['archive_layout'],
              'archive_bytes_total': report['archive_bytes_total'], 'archive_parts': [],
              'website_origin': 'https://maps.chrislentner.com', 'pages_origin': 'https://friendliness-index.pages.dev'}
    for part in results:
        key = f"ny/{dataset}/{part['archive_sha256'][:16]}-{part['id']}.pmtiles"
        config['archive_parts'].append({k: part[k] for k in ['id', 'minzoom', 'maxzoom', 'archive_file', 'archive_bytes', 'archive_sha256']})
        config['archive_parts'][-1]['archive_url'] = 'https://tiles.chrislentner.com/' + key
    target = Path('deploy/ny-archives.json')
    if target.exists():
        assert json.loads(target.read_text()) == config, 'Refusing to replace a different archive configuration'
    else:
        target.write_text(json.dumps(config, indent=2))
    print(json.dumps({k: v for k, v in report.items() if k != 'parts'}), flush=True)


if __name__ == '__main__':
    main()
