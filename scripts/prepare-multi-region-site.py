"""Stage linked MA and NY maps while preserving MA data; never publish anything."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil


def inventory(root):
    result = {}
    for path in root.rglob('*'):
        if path.is_file():
            with path.open('rb') as stream:
                digest = hashlib.file_digest(stream, 'sha256').hexdigest()
            result[path.relative_to(root).as_posix()] = {
                'bytes': path.stat().st_size, 'sha256': digest}
    return result


def with_region_navigation(html, current):
    assert html.count('</head>') == html.count('</body>') == 1
    assert 'region-navigation' not in html
    links = []
    for code, label, href in [('ma', 'Massachusetts', '/'), ('ny', 'New York State', '/ny/')]:
        active = ' aria-current="page"' if code == current else ''
        links.append(f'<a href="{href}"{active}>{label}</a>')
    navigation = '<nav class="region-navigation" aria-label="Map region">' + ''.join(links) + '</nav>'
    return html.replace('</head>', '<link rel="stylesheet" href="/region-navigation.css"></head>')\
               .replace('</body>', navigation + '</body>')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ma', type=Path, default=Path('build/massachusetts-pmtiles'))
    parser.add_argument('--ny', type=Path, default=Path('build/new-york-pmtiles'))
    parser.add_argument('--output', type=Path, default=Path('build/ma-ny-pmtiles'))
    parser.add_argument('--report', type=Path, default=Path('qa-artifacts/ny/combined-site.json'))
    args = parser.parse_args()
    assert not args.output.exists(), 'Refusing to replace a staged site'
    assert not (args.ma / 'ny').exists(), 'The /ny/ route is already occupied'
    for root, label in [(args.ma, 'Massachusetts'), (args.ny, 'New York State')]:
        manifest = json.loads((root / 'manifest.json').read_text())
        assert manifest['area_label'] == label
        assert manifest.get('archive_url') or manifest.get('archive_parts'), 'Require a verified archive-backed staging directory'
        assert not manifest.get('available_tiles'), 'Loose PNG inventory must be omitted'
    before_ma, before_ny = inventory(args.ma), inventory(args.ny)
    assert len(before_ma) == 441 and sum(x['bytes'] for x in before_ma.values()) == 175_551_041
    assert not any(name.endswith('.pmtiles') for name in before_ma | before_ny)
    shutil.copytree(args.ma, args.output)
    shutil.copytree(args.ny, args.output / 'ny', ignore=shutil.ignore_patterns('_headers'))
    expected_html = {}
    for source, relative, current in [(args.ma, 'index.html', 'ma'), (args.ny, 'ny/index.html', 'ny')]:
        expected_html[relative] = with_region_navigation((source / 'index.html').read_text(encoding='utf-8'), current)
        (args.output / relative).write_text(expected_html[relative], encoding='utf-8')
    shutil.copy2('web/region-navigation.css', args.output / 'region-navigation.css')
    # Existing MA cache and security rules remain byte-for-byte at the beginning.
    # Only the two new NY paths receive additional cache directives.
    headers = (args.ma / '_headers').read_bytes()
    additions = (b'\n/ny/datasets/*\n  Cache-Control: public, max-age=31536000, immutable\n'
                 b'/ny/manifest.json\n  Cache-Control: no-cache\n')
    (args.output / '_headers').write_bytes(headers + additions)
    combined = inventory(args.output)
    for name, original in before_ma.items():
        if name not in {'_headers', 'index.html'}:
            assert combined[name] == original, f'MA served asset changed: {name}'
    for name, original in before_ny.items():
        if name not in {'_headers', 'index.html'}:
            assert combined['ny/' + name] == original, f'NY asset changed: {name}'
    for name, expected in expected_html.items():
        assert (args.output / name).read_text(encoding='utf-8') == expected
    assert inventory(args.ma) == before_ma, 'MA staging source changed'
    assert inventory(args.ny) == before_ny, 'NY staging source changed'
    total_bytes = sum(x['bytes'] for x in combined.values())
    baseline_bytes = sum(x['bytes'] for x in before_ma.values())
    assert len(combined) <= 20_000
    assert max(x['bytes'] for x in combined.values()) <= 25 * 1024**2
    report = {
        'output': str(args.output.resolve()),
        'proposed_urls': ['https://maps.chrislentner.com/ny/',
                          'https://friendliness-index.pages.dev/ny/'],
        'baseline_upload_inputs': len(before_ma), 'baseline_bytes': baseline_bytes,
        'combined_upload_inputs': len(combined), 'combined_bytes': total_bytes,
        'combined_served_assets': len(combined) - 1,
        'incremental_upload_inputs': len(combined) - len(before_ma),
        'incremental_served_assets': len(combined) - len(before_ma),
        'incremental_site_bytes': total_bytes - baseline_bytes,
        'headers_added_bytes': len(additions),
        'unchanged_ma_served_assets': len(before_ma) - 2,
        'changed_ma_served_assets': ['index.html'],
        'ma_html_change': 'Add persistent links to both regions and shared navigation stylesheet only',
        'ma_manifest_unchanged': combined['manifest.json'] == before_ma['manifest.json'],
        'largest_asset_bytes': max(x['bytes'] for x in combined.values()),
        'source_directories_unchanged': True,
        'ma_map_logic_and_data_unchanged': True, 'discoverable_region_navigation': True,
        'published': False,
        'pending': 'NY archive upload and Pages deployment require explicit approval; live endpoint QA follows authorized upload.',
        'assets': combined,
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2))
    print(json.dumps({k: v for k, v in report.items() if k != 'assets'}))


if __name__ == '__main__':
    main()
