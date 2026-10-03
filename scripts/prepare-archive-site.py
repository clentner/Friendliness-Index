"""Stage an archive-backed Pages upload while preserving the original PNG export."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil


def sha(path):
    with path.open('rb') as source:
        return hashlib.file_digest(source, 'sha256').hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, default=Path('build/massachusetts'))
    parser.add_argument('--output', type=Path, default=Path('build/massachusetts-pmtiles'))
    parser.add_argument('--archive', type=Path, default=Path('build/archives/massachusetts-5124e42eb1483a75.pmtiles'))
    parser.add_argument('--archive-dir', type=Path, default=Path('build/archives'))
    parser.add_argument('--sdk', type=Path, default=Path('.tools/pmtiles/js/node_modules'))
    parser.add_argument('--config', type=Path, default=Path('deploy/ma-archive.json'))
    parser.add_argument('--report', type=Path, default=Path('qa-artifacts/pmtiles-production/preparation.json'))
    args = parser.parse_args()
    config = json.loads(args.config.read_text())
    manifest = json.loads((args.source / 'manifest.json').read_text())
    assert manifest['dataset'] == config['dataset']
    parts = config.get('archive_parts')
    for part in parts or [config]:
        archive = args.archive_dir / part['archive_file'] if parts else args.archive
        assert archive.stat().st_size == part['archive_bytes']
        assert sha(archive) == part['archive_sha256']
        assert part['archive_bytes'] <= 512_000_000, 'Archive exceeds conservative CDN cache ceiling; partition before staging'
    if parts:
        assert config['archive_layout'] == 'zoom-partitions-v1'
        next_zoom = manifest['minzoom']
        for part in parts:
            assert part['minzoom'] == next_zoom and part['maxzoom'] >= part['minzoom']
            next_zoom = part['maxzoom'] + 1
        assert next_zoom == manifest['maxzoom'] + 1
        assert sum(p['archive_bytes'] for p in parts) == config['archive_bytes_total']
    assert not args.output.exists(), 'Refusing to replace a staged site'
    assert json.loads((args.sdk / 'pmtiles/package.json').read_text())['version'] == '4.5.0'
    original = {p.relative_to(args.source).as_posix(): {'bytes': p.stat().st_size, 'sha256': sha(p)}
                for p in args.source.rglob('*') if p.is_file()}
    prefix = f"datasets/{manifest['dataset']}/tiles/"
    omitted = [name for name in original if name.startswith(prefix)]
    assert len(omitted) == manifest['tiles']
    raw_index = json.loads((args.source / 'datasets' / manifest['dataset'] / 'raw-index.json').read_text())
    expected_raw = {f"datasets/{manifest['dataset']}/{part['path']}" for part in raw_index['parts']}
    for name in original:
        if name.startswith(prefix):
            continue
        target = args.output / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(args.source / name, target)
    for name in ['app.js', 'style.css']:
        shutil.copy2(Path('web') / name, args.output / name)
    html = Path('web/index.html').read_text(encoding='utf-8')
    label = manifest['area_label']
    html = html.replace('Greater Boston', label).replace('GREATER BOSTON', label.upper())
    html = html.replace('Boston pilot', label + ' map').replace('Boston', label)
    (args.output / 'index.html').write_text(html, encoding='utf-8')
    for source, target in [('pmtiles/dist/pmtiles.js', 'pmtiles.js'),
                           ('fflate/LICENSE', 'FFLATE-LICENSE.txt')]:
        shutil.copy2(args.sdk / source, args.output / 'vendor' / target)
    shutil.copy2('deploy/licenses/PMTILES-LICENSE.txt', args.output / 'vendor/PMTILES-LICENSE.txt')
    manifest.pop('available_tiles')
    manifest.pop('tile_url')
    if parts:
        manifest.update(archive_layout=config['archive_layout'], archive_bytes_total=config['archive_bytes_total'],
                        archive_parts=[{k:v for k,v in part.items() if k != 'archive_file'} for part in parts])
    else:
        manifest.update(archive_url=config['archive_url'], archive_sha256=config['archive_sha256'],
                        archive_bytes=config['archive_bytes'])
    (args.output / 'manifest.json').write_text(json.dumps(manifest), encoding='utf-8')
    # Dataset metadata is immutable source-export provenance, including its old
    # PNG paths. Keep it byte-identical; the top-level manifest controls delivery.
    preserved = [name for name in original if name.startswith('datasets/') and not name.startswith(prefix)]
    for name in preserved:
        assert sha(args.output / name) == original[name]['sha256'], name
    for name in original:
        assert sha(args.source / name) == original[name]['sha256'], name
    assets = {p.relative_to(args.output).as_posix(): {'bytes': p.stat().st_size, 'sha256': sha(p)}
              for p in args.output.rglob('*') if p.is_file()}
    assert len(assets) < 20000 and max(v['bytes'] for v in assets.values()) < 25 * 1024**2
    assert not any(name.endswith('.pmtiles') or name.startswith(prefix) for name in assets)
    raw = [name for name in preserved if '/raw/' in name]
    assert set(raw) == expected_raw, 'Staged analytical parts differ from the source raw index'
    report = {'config': config, 'output': str(args.output.resolve()), 'files': len(assets),
              'bytes': sum(v['bytes'] for v in assets.values()), 'assets': assets,
              'omitted_raster_files': len(omitted), 'preserved_raw_parts': len(raw),
              'preserved_raw_bytes': sum(original[name]['bytes'] for name in raw),
              'source_export_unchanged_files': len(original), 'deployment_ready': False,
              'pending': 'Confirm live archive endpoint and verify range, CORS, cache, and browser behavior.'}
    target = args.report
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps({k: v for k, v in report.items() if k != 'assets'}))


if __name__ == '__main__':
    main()
