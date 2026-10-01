import math
import unittest
import heapq
import numpy as np
from pilot.metric import make_graph, score, score_chunked, DECAY, RADIUS, display_values


class MetricTests(unittest.TestCase):
    def test_multiplicity_and_connector_cost(self):
        graph = make_graph({1:(0,0), 2:(100,0)}, [[1,2]])
        values, _ = score(graph, [[0,10]], [[100,20],[100,20]])
        self.assertAlmostEqual(values[0], 2 * math.exp(-130/DECAY))

    def test_disconnected_components_not_discarded(self):
        graph = make_graph({1:(0,0),2:(100,0),3:(1000,0),4:(1100,0)}, [[1,2],[3,4]])
        values, _ = score(graph, [[0,0],[1000,0]], [[1100,0]])
        np.testing.assert_allclose(values, [0, math.exp(-100/DECAY)])

    def test_coincident_nodes_are_not_intersections(self):
        graph = make_graph({1:(0,0),2:(100,0),3:(100,0),4:(200,0)}, [[1,2],[3,4]])
        values, _ = score(graph, [[0,0]], [[200,0]])
        self.assertEqual(values[0], 0)

    def test_unreachable_distinct_from_zero(self):
        graph = make_graph({1:(0,0),2:(100,0)}, [[1,2]])
        values, _ = score(graph, [[0,0],[0,100]], [[100,100]])
        self.assertEqual(values[0], 0)
        self.assertTrue(math.isnan(values[1]))

    def test_radius_includes_connectors(self):
        graph = make_graph({1:(0,0),2:(RADIUS,0)}, [[1,2]])
        values, _ = score(graph, [[0,0],[0,1]], [[RADIUS,0]])
        self.assertAlmostEqual(values[0], math.exp(-RADIUS/DECAY))
        self.assertEqual(values[1], 0)

    def test_adjacent_geometry_and_duplicate_way(self):
        graph = make_graph({1:(0,0),2:(0,100),3:(100,100)}, [[1,2,3],[3,2,1]])
        values, _ = score(graph, [[0,0]], [[100,100]])
        self.assertAlmostEqual(values[0], math.exp(-200/DECAY))

    def test_seams_equal_global_reference(self):
        nodes = {i:(i*100, 0) for i in range(-20,51)}
        graph = make_graph(nodes, [list(nodes)])
        queries = np.array([[x, 15] for x in range(-100,3001,25)])
        pois = np.array([[x, 10] for x in range(-800,3801,137)])
        expected, _ = score(graph, queries, pois)
        for width in [400,1000,2000]:
            actual, _ = score_chunked(graph, queries, pois, width)
            np.testing.assert_allclose(actual, expected, rtol=1e-12, atol=1e-12)

    def test_display_scale_independent_of_region(self):
        np.testing.assert_allclose(display_values(np.array([0,1,30])), [0,math.log(2)/math.log(31),1])

    def test_independent_forward_oracle_on_cycle(self):
        graph = make_graph({1:(0,0),2:(100,0),3:(100,100),4:(0,100)},[[1,2,3,4,1]])
        queries=np.array([[10,15],[80,115],[30,90]])
        pois=np.array([[100,10],[100,10],[5,100]])
        adjacency={i:[] for i in range(len(graph.xy))}
        for (u,v),length in zip(graph.edges,graph.lengths):
            adjacency[u].append((v,length));adjacency[v].append((u,length))
        expected=[]
        for query in queries:
            offsets=np.linalg.norm(graph.xy-query,axis=1)
            source=int(np.argmin(offsets))
            distances={source:float(offsets[source])};queue=[(distances[source],source)]
            while queue:
                distance,u=heapq.heappop(queue)
                if distance!=distances[u]:continue
                for v,length in adjacency[u]:
                    candidate=distance+length
                    if candidate<distances.get(v,math.inf):
                        distances[v]=candidate;heapq.heappush(queue,(candidate,v))
            total=0
            for poi in pois:
                offset=np.linalg.norm(graph.xy-poi,axis=1)
                node=int(np.argmin(offset))
                distance=distances.get(node,math.inf)+offset[node]
                if distance<=RADIUS:total+=math.exp(-distance/DECAY)
            expected.append(total)
        actual,_=score(graph,queries,pois)
        np.testing.assert_allclose(actual,expected,rtol=1e-12)


if __name__ == "__main__":
    unittest.main()
