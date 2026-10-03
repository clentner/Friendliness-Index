"""Assert pixel equality between loose PNG and PMTiles browser captures."""
import json
import sys
from pathlib import Path
from PIL import Image, ImageChops

root = Path(sys.argv[1] if len(sys.argv) > 1 else 'qa-artifacts/pmtiles/browser')
results = json.loads((root / 'results.json').read_text())
assert len(results['runs']) == 6, 'All three viewport pairs must finish first'
pairs = []
baseline = 'reference' if any(r['mode']=='reference' for r in results['runs']) else 'loose'
for width in [1440, 390, 320]:
    originals = sorted(root.glob(f'{baseline}-{width}-*.png'))
    run=next(r for r in results['runs'] if r['viewport']['width']==width and r['mode']==baseline)
    assert len(originals) == run.get('views',10), f'Missing views at width {width}'
    for original in originals:
        archive = original.with_name(original.name.replace(baseline+'-', 'archive-', 1))
        with Image.open(original) as before, Image.open(archive) as after:
            assert before.size == after.size
            difference = ImageChops.difference(before.convert('RGB'), after.convert('RGB'))
            assert difference.getbbox() is None, original.name
        pairs.append({'loose': original.name, 'archive': archive.name, 'pixel_equal': True})
report = {'verified_pairs': len(pairs), 'differing_pixels': 0, 'pairs': pairs}
(root / 'pixel-comparison.json').write_text(json.dumps(report, indent=2))
print(json.dumps({'verified_pairs': len(pairs), 'differing_pixels': 0}))
