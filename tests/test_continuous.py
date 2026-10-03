import runpy
import unittest
import numpy as np

helpers=runpy.run_path('scripts/prepare-continuous-site.py')


class ContinuousTests(unittest.TestCase):
    def test_priority_copies_one_pixel_without_double_opacity(self):
        ma=np.array([[[34,62,92,210],[10,20,30,0],[1,2,3,80]]],dtype=np.uint8)
        ny=np.array([[[200,100,50,210],[4,5,6,210],[9,8,7,190]]],dtype=np.uint8)
        result=helpers['select_pixels'](ma,ny)
        np.testing.assert_array_equal(result,[[[34,62,92,210],[4,5,6,210],[1,2,3,80]]])
        np.testing.assert_array_equal(ma,[[[34,62,92,210],[10,20,30,0],[1,2,3,80]]])

    def test_compact_routing_preserves_holes_and_zoom(self):
        self.assertEqual(helpers['compact']({'14/7/9','14/3/9','14/4/9','13/3/9','14/5/9'}),
                         {'13/9':[3,3],'14/9':[3,5,7,7]})
