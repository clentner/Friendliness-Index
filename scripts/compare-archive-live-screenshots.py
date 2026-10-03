"""Compare real-endpoint viewer captures against the validated PNG baseline."""
import json
from pathlib import Path
import sys
from PIL import Image, ImageChops

mode = sys.argv[1] if len(sys.argv) > 1 else 'staged'
assert mode in ['staged', 'live']
root = Path('qa-artifacts/pmtiles-real-endpoint') / mode
baseline = Path('qa-artifacts/pmtiles-production/browser')
results = json.loads((root / 'results.json').read_text())
assert len(results['runs']) == 4
pairs = []
for origin in ['maps', 'pages']:
    for width in [1440, 390]:
        captures = sorted(root.glob(f'{origin}-{width}-*.png'))
        assert len(captures) == 10
        for capture in captures:
            original = baseline / capture.name.replace(origin + '-', 'loose-', 1)
            with Image.open(original) as before, Image.open(capture) as after:
                assert before.size == after.size
                difference = ImageChops.difference(before.convert('RGB'), after.convert('RGB'))
                assert difference.getbbox() is None, capture.name
            pairs.append({'capture': capture.name, 'pixel_equal': True})
report = {'mode': mode, 'verified_pairs': len(pairs), 'differing_pixels': 0, 'pairs': pairs}
(root / 'pixel-comparison.json').write_text(json.dumps(report, indent=2))
print(json.dumps({k: v for k, v in report.items() if k != 'pairs'}))
