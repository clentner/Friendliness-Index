"""Check representative PNG pixels using independent ordinary-file raster reads."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import time
import numpy as np
from PIL import Image
from pilot.region import NY_SAMPLE_LOCATIONS, SAMPLE_LOCATIONS
from pilot.source import TO_METERS
from pilot.tiles import colorize


def reference_values(stream, shape, origin, spacing, z, tx, ty):
    px, py = np.meshgrid(np.arange(256, dtype=float) + .5, np.arange(256, dtype=float) + .5)
    longitude = (tx + px / 256) * 360 / 2**z - 180
    latitude = np.degrees(np.arctan(np.sinh(np.pi * (1 - 2 * (ty + py / 256) / 2**z))))
    x, y = TO_METERS.transform(longitude, latitude)
    columns = np.floor((x - origin[0]) / spacing).astype(np.int64)
    rows = np.floor((y - origin[1]) / spacing).astype(np.int64)
    valid = (rows >= 0) & (rows < shape[0]) & (columns >= 0) & (columns < shape[1])
    values = np.full((256, 256), np.nan, dtype=np.float64)
    # No DiskRaster, memmap, exporter sampling helper or candidate envelope.
    for row in np.unique(rows[valid]):
        selected = valid & (rows == row)
        cc = columns[selected]
        left, right = int(cc.min()), int(cc.max()) + 1
        stream.seek((int(row) * shape[1] + left) * 4)
        raw = stream.read((right - left) * 4)
        assert len(raw) == (right - left) * 4
        values[selected] = np.frombuffer(raw, dtype='<f4')[cc - left]
    return values


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--site', type=Path, default=Path('build/new-york'))
    parser.add_argument('--run', type=Path, default=Path('build/ny-run'))
    parser.add_argument('--report', type=Path, default=Path('qa-artifacts/ny/pixel-reference.json'))
    args = parser.parse_args()
    started = time.monotonic()
    manifest = json.loads((args.site / 'manifest.json').read_text())
    grid = manifest['grid']; z = manifest['maxzoom']
    places = list(NY_SAMPLE_LOCATIONS if manifest['area_label'] == 'New York State' else SAMPLE_LOCATIONS)
    if manifest['area_label'] == 'New York State':
        places += [('Toronto', -79.38, 43.65), ('Jersey City', -74.07, 40.73), ('Pittsfield MA', -73.245, 42.451)]
    tile_root = args.site / 'datasets' / manifest['dataset'] / 'tiles'
    results = []
    with (args.run / 'scores.f32').open('rb') as stream:
        for name, longitude, latitude in places:
            tx = math.floor((longitude + 180) / 360 * 2**z)
            ty = math.floor((1 - math.asinh(math.tan(math.radians(latitude))) / math.pi) / 2 * 2**z)
            values = reference_values(stream, grid['shape'], grid['origin_corner_m'],
                                      manifest['parameters']['grid_spacing_m'], z, tx, ty)
            finite = np.isfinite(values)
            tile = tile_root / str(z) / str(tx) / f'{ty}.png'
            result = {'place': name, 'tile': f'{z}/{tx}/{ty}',
                      'finite_pixels': int(finite.sum()), 'finite_zero_pixels': int(np.count_nonzero(values == 0)),
                      'transparent_pixels': int((~finite).sum()), 'png_present': tile.exists()}
            if tile.exists():
                with Image.open(tile) as image:
                    actual = np.asarray(image)
                np.testing.assert_array_equal(actual, colorize(values), err_msg=name)
                result['png_sha256'] = hashlib.sha256(tile.read_bytes()).hexdigest()
                result['exact_rgba_match'] = True
            else:
                assert not finite.any(), f'Missing PNG contains finite analytical values: {name}'
                result['correctly_absent_nodata'] = True
            if finite.any():
                result.update(min_score=float(values[finite].min()), max_score=float(values[finite].max()))
            results.append(result)
    report = {'dataset': manifest['dataset'], 'scores_sha256': manifest['scores_sha256'],
              'method': 'Independent ordinary-file row reads and pixel coordinate sampling; unchanged shared palette',
              'places': results, 'sampled_pixels': len(results) * 256 * 256,
              'exact_png_matches': sum(r.get('exact_rgba_match', False) for r in results),
              'correctly_absent_tiles': sum(r.get('correctly_absent_nodata', False) for r in results),
              'seconds': time.monotonic() - started}
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2))
    print(json.dumps({k: v for k, v in report.items() if k != 'places'}))


if __name__ == '__main__':
    main()
