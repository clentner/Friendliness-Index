"""Assert pixel equality between loose PNG and PMTiles browser captures."""
import json
from pathlib import Path
from PIL import Image, ImageChops

root = Path('qa-artifacts/pmtiles/browser')
results = json.loads((root / 'results.json').read_text())
assert len(results['runs']) == 6, 'All three viewport pairs must finish first'
pairs = []
for width in [1440, 390, 320]:
    originals = sorted(root.glob(f'loose-{width}-*.png'))
    assert len(originals) == 10, f'Expected ten views at width {width}'
    for original in originals:
        archive = original.with_name(original.name.replace('loose-', 'archive-', 1))
        with Image.open(original) as before, Image.open(archive) as after:
            assert before.size == after.size
            difference = ImageChops.difference(before.convert('RGB'), after.convert('RGB'))
            assert difference.getbbox() is None, original.name
        pairs.append({'loose': original.name, 'archive': archive.name, 'pixel_equal': True})
report = {'verified_pairs': len(pairs), 'differing_pixels': 0, 'pairs': pairs}
(root / 'pixel-comparison.json').write_text(json.dumps(report, indent=2))
print(json.dumps({'verified_pairs': len(pairs), 'differing_pixels': 0}))
