"""Package existing PNG bytes; verify the complete archive before publishing locally.

Requires requirements-archive.txt plus the project's Pillow dependency. This does
not score, resample, recolor, edit the export, or alter analytical float32 data.
"""
import argparse
import hashlib
import io
import json
import math
from pathlib import Path
import time

from PIL import Image
from pmtiles.reader import Reader, all_tiles
from pmtiles.tile import Compression, TileType, zxy_to_tileid
from pmtiles.writer import Writer


def digest(data):
    return hashlib.sha256(data).hexdigest()


def tile_at(lon, lat, zoom):
    n = 2**zoom
    return (zoom, int((lon + 180) / 360 * n),
            int((1 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2 * n))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('export', type=Path)
    parser.add_argument('archive', type=Path)
    parser.add_argument('--report', type=Path, required=True)
    args = parser.parse_args()
    started = time.monotonic()
    root = args.export.resolve()
    manifest_bytes = (root / 'manifest.json').read_bytes()
    manifest = json.loads(manifest_bytes)
    overview_only = manifest.get('archive_partition', {}).get('id') == 'overview' and manifest['maxzoom'] < 14
    keys = manifest['available_tiles']
    expected = set(keys)
    assert len(expected) == len(keys) == manifest['tiles']
    tile_root = root / 'datasets' / manifest['dataset'] / 'tiles'
    actual = {p.relative_to(tile_root).as_posix()[:-4] for p in tile_root.rglob('*.png')}
    assert actual == expected, 'Manifest and source PNG file set differ'
    assert not args.archive.exists(), 'Refusing to replace an existing archive'
    args.archive.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.archive.with_suffix('.pmtiles.tmp')
    metadata = {k: manifest[k] for k in ['dataset', 'metric_version', 'bbox',
        'area_label', 'source', 'parameters', 'grid', 'scores_sha256',
        'code_sha256', 'poi_config_sha256'] if k in manifest}
    metadata.update(name=manifest['area_label'] + ' Friendliness Index',
        format='png', type='overlay', version='1', tile_size=manifest['tile_size'],
        minzoom=manifest['minzoom'], maxzoom=manifest['maxzoom'],
        attribution='Friendliness Index · © OpenStreetMap contributors · ODbL',
        license='https://opendatacommons.org/licenses/odbl/',
        source_manifest_sha256=digest(manifest_bytes),
        nodata='Missing tiles and alpha=0 are transparent; finite zero scores remain colored.',
        analytical_data='Original little-endian float32 parts remain separate and unchanged.')
    bounds_fields = ['min_lon_e7', 'min_lat_e7', 'max_lon_e7', 'max_lat_e7']
    header = {key: round(value * 1e7) for key, value in zip(bounds_fields, manifest['bbox'])}
    header.update(tile_compression=Compression.NONE, tile_type=TileType.PNG)
    inventory = {}
    ordered = sorted((tuple(map(int, k.split('/'))) for k in keys), key=lambda zxy: zxy_to_tileid(*zxy))
    with temporary.open('xb') as output:
        writer = Writer(output)
        for zxy in ordered:
            key = '/'.join(map(str, zxy))
            data = (tile_root / (key + '.png')).read_bytes()
            assert data.startswith(b'\x89PNG\r\n\x1a\n'), key
            inventory[key] = {'bytes': len(data), 'sha256': digest(data)}
            writer.write_tile(zxy_to_tileid(*zxy), data)
        writer.finalize(header, metadata)
    built_seconds = time.monotonic() - started
    pixel_examples = {}
    with temporary.open('rb') as source:
        def read(offset, length):
            source.seek(offset)
            data = source.read(length)
            assert len(data) == length, 'Truncated archive'
            return data
        reader = Reader(read)
        stored_header = reader.header()
        assert reader.metadata() == metadata
        for field in bounds_fields:
            assert stored_header[field] == header[field]
        assert stored_header['min_zoom'] == manifest['minzoom']
        assert stored_header['max_zoom'] == manifest['maxzoom']
        assert stored_header['tile_type'] == TileType.PNG
        assert stored_header['tile_compression'] == Compression.NONE
        assert stored_header['addressed_tiles_count'] == len(expected)
        assert stored_header['clustered']
        seen = set()
        for zxy, data in all_tiles(read):
            key = '/'.join(map(str, zxy))
            assert key not in seen and key in expected, key
            original = (tile_root / (key + '.png')).read_bytes()
            assert data == original, 'Byte mismatch: ' + key
            assert digest(data) == inventory[key]['sha256'], key
            seen.add(key)
            if len(pixel_examples) < (1 if overview_only else 2) and zxy[0] == manifest['maxzoom']:
                rgba = Image.open(io.BytesIO(data)).convert('RGBA')
                pixels = list(rgba.getdata())
                for kind, predicate in [('transparent', lambda p: p[3] == 0),
                                        ('zero_color_blue', lambda p: p == (34, 62, 92, 210))]:
                    if overview_only and kind == 'zero_color_blue':
                        continue  # Resampling need not retain exact native RGBA values.
                    if kind not in pixel_examples:
                        for i, pixel in enumerate(pixels):
                            if predicate(pixel):
                                pixel_examples[kind] = {'tile': key, 'xy': [i % 256, i // 256], 'rgba': pixel}
                                break
        assert seen == expected, 'Archive has missing or additional entries'
        absent_checks = []
        for name, lon, lat in [('Hartford', -72.67, 41.76), ('Providence', -71.4128, 41.824),
                               ('Nashua', -71.4666, 42.7654), ('Atlantic', -69.9, 41.2)]:
            zxy = tile_at(lon, lat, manifest['maxzoom'])
            key = '/'.join(map(str, zxy))
            assert key not in expected and reader.get(*zxy) is None, key
            absent_checks.append({'place': name, 'tile': key})
    assert 'transparent' in pixel_examples, 'Missing transparency evidence'
    if not overview_only:
        assert 'zero_color_blue' in pixel_examples, 'Missing native zero-color evidence'
    assert (root / 'manifest.json').read_bytes() == manifest_bytes
    archive_bytes = temporary.stat().st_size
    with temporary.open('rb') as source:
        archive_sha = hashlib.file_digest(source, 'sha256').hexdigest()
    temporary.rename(args.archive)
    png_bytes = sum(v['bytes'] for v in inventory.values())
    report = {'dataset': manifest['dataset'], 'archive': str(args.archive.resolve()),
        'archive_sha256': archive_sha, 'archive_bytes': archive_bytes,
        'source_png_bytes': png_bytes, 'overhead_bytes': archive_bytes - png_bytes,
        'internal_tiles': len(inventory), 'source_objects': len(inventory), 'archive_objects': 1,
        'verified_byte_for_byte': len(seen), 'metadata': metadata,
        'header': {k: v.value if hasattr(v, 'value') else v for k, v in stored_header.items()},
        'missing_tiles': absent_checks, 'pixel_examples': pixel_examples,
        'native_zero_color_required': not overview_only,
        'build_seconds': round(built_seconds, 3), 'total_seconds': round(time.monotonic() - started, 3)}
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2), encoding='utf-8')
    args.report.with_name('tile-inventory.json').write_text(json.dumps(inventory), encoding='utf-8')
    print(json.dumps({k: v for k, v in report.items() if k not in ['metadata', 'header']}))


if __name__ == '__main__':
    main()
