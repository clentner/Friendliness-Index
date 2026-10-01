import tempfile
import unittest
from pathlib import Path
import numpy as np
from PIL import Image
from pilot.source import walking, allowed_poi, representative, TO_METERS, TO_WGS, acquisition_bounds, projected_bounds
from pilot.tiles import sample_grid, colorize, write_tiles


class SourceAndTileTests(unittest.TestCase):
    def test_pedestrian_access_overrides(self):
        self.assertFalse(walking({'highway':'footway','access':'private'}))
        self.assertTrue(walking({'highway':'footway','access':'private','foot':'yes'}))
        self.assertFalse(walking({'highway':'residential','foot':'no'}))
        self.assertFalse(walking({'highway':'motorway'}))

    def test_editorial_filter_precedence(self):
        cfg={'allow':{'shop':['*']},'deny':{'shop':['vacant']}}
        self.assertTrue(allowed_poi({'shop':'bakery'},cfg))
        self.assertFalse(allowed_poi({'shop':'vacant'},cfg))

    def test_metric_grid_roundtrip_and_nodata(self):
        origin=np.array(TO_METERS.transform(-71.06,42.36))
        scores=np.array([[1,2],[3,np.nan]])
        x,y=np.meshgrid(origin[0]+np.array([12.5,37.5]),origin[1]+np.array([12.5,37.5]))
        lon,lat=TO_WGS.transform(x,y)
        np.testing.assert_allclose(sample_grid(scores,origin,lon,lat),scores,equal_nan=True)
        self.assertEqual(colorize(scores)[1,1,3],0)
        self.assertGreater(colorize(np.zeros((1,1)))[0,0,3],0)

    def test_halo_encloses_core(self):
        bbox=[-71.08,42.35,-71.04,42.37]
        expanded=acquisition_bounds(bbox)
        self.assertLess(expanded[0],bbox[0])
        self.assertGreater(expanded[3],bbox[3])

    def test_raster_parent_has_real_child_pixels(self):
        bbox=[-71.065,42.355,-71.055,42.365]
        b=projected_bounds(bbox)
        origin=np.floor(b[:2]/25)*25
        cols,rows=np.ceil((b[2:]-origin)/25).astype(int)
        with tempfile.TemporaryDirectory() as tmp:
            stats=write_tiles(tmp,np.ones((rows,cols)),origin,bbox,minzoom=13,maxzoom=14)
            self.assertGreater(stats['tiles'],1)
            for file in Path(tmp).rglob('*.png'):
                with Image.open(file) as image:
                    self.assertEqual(image.size,(256,256))
                    self.assertEqual(image.mode,'RGBA')


if __name__=='__main__':
    unittest.main()
