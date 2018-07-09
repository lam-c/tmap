# -*- coding: utf-8 -*-
from tda.cover import Cover
import numpy as np
import pandas as pd
import itertools
from sklearn import cluster, preprocessing


class Mapper(object):
    """
    implement the TDA mapper framework for microbiome analysis
    """
    def __init__(self, verbose=1):
        self.verbose = verbose
        # self.lens = None
        # self.clusterer = None
        # self.cover = None
        # self.graph = {}

    def filter(self, data, lens=None):
        """
        project/filter high dimensional data points use the specified lens
        default to scale the projection data with MinMaxScaler
        """
        if data is None:
            raise Exception("Data must not be None.")
        if type(data) is not np.ndarray:
            data = np.array(data)

        # "Metric and Filters for projection/filtering"
        # projection of original data points onto a low dimensional space
        # lens is a list of filters (tmap.tda.filter.Filters), can combine and use different filters
        # if lens is None, data is assumed to be projected data already
        projected_data = None
        if len(lens) > 0:
            for _filter in lens:
                if self.verbose >= 1:
                    print("Filtering by %s." % (_filter.__class__.__name__,))
                    if _filter.metric is not None:
                        print("...calculate distance matrix using the %s metric." % _filter.metric.name)
                    else:
                        print("...calculate distance matrix with default.")

                if projected_data is None:
                    projected_data = _filter.fit_transform(data)
                else:
                    p = _filter.fit_transform(data)
                    projected_data = np.concatenate([projected_data, p], axis=1)
        else:
            # lens is None, and the input "data" is assumed to be already filtered
            projected_data = data

        if self.verbose >= 1:
            print("Finish filtering of points cloud data.")
        return projected_data

    def map(self, data, cover, clusterer=cluster.DBSCAN(eps=0.5, min_samples=1)):
        """
        map the points cloud with the projection data, and return a TDA graph.
        """
        # nodes, edges and graph of the TDA graph
        graph = {}
        nodes = {}
        edges = []

        # projection data & raw data should have a same number of points
        assert data.shape[0] == cover.n_points
        if self.verbose >= 1:
            print("Mapping on data %s using lens %s" %
                  (str(data.shape), str(cover.data.shape)))
        # Define covering of the projection data and minimal number of points in a hypercube to be cluster
        cluster_params = clusterer.get_params()
        min_cluster_samples = cluster_params.get("min_samples", 1)
        if self.verbose >= 1:
            print("...minimal number of points in hypercube to do clustering: %d" % (min_cluster_samples,))

        # generate hypercubes from the cover and perform clustering analysis
        cubes = cover.hypercubes
        data_idx = np.arange(data.shape[0])
        node_id = 0
        for cube in cubes:
            cube_data = data[cube]
            cube_data_idx = data_idx[cube]
            if cube_data.shape[0] >= min_cluster_samples:
                if (clusterer is not None) and ("fit" in dir(clusterer)):
                    clusterer.fit(cube_data)
                    for label in np.unique(clusterer.labels_):
                        # the "-1" label is used for "un-clustered" points!!!
                        if label != -1:
                            point_mask = np.zeros(data.shape[0], dtype=bool)
                            point_mask[cube_data_idx[clusterer.labels_ == label]] = True
                            nodes[node_id] = point_mask
                            node_id += 1
                else:
                    # assumed to have a whole cluster of cubes!!!
                    point_mask = np.zeros(data.shape[0], dtype=bool)
                    point_mask[cube_data_idx] = True
                    nodes[node_id] = point_mask
                    node_id += 1

        if self.verbose >= 1:
            print("...create %s nodes." % (len(nodes)))
        # no cluster of nodes, and return None
        if len(nodes) == 0:
            return graph

        # calculate properties of nodes: projection coordinates and size
        if self.verbose >= 1:
            print("...calculate projection coordinates of nodes.")

        node_keys = nodes.keys()
        node_positions = np.zeros((len(nodes), cover.data.shape[1]))
        node_sizes = np.zeros((len(nodes), 1))
        for i, node_id in enumerate(node_keys):
            data_in_node = cover.data[nodes[node_id], :]
            node_coordinates = np.average(data_in_node, axis=0)
            node_positions[i] += node_coordinates
            node_sizes[i] += len(data_in_node)

        # construct the TDA graph from overlaps (common points) between nodes
        if self.verbose >= 1:
            print("...construct a TDA graph.")

        adj_matrix = np.empty((len(nodes), len(nodes)))
        # set the NaN value for filtering edges with pandas stack function
        adj_matrix[:] = np.nan
        node_ids = nodes.keys()
        adj_matrix = pd.DataFrame(adj_matrix, index=node_ids, columns=node_ids)
        # todo: this edges making step to be improved? using some native numpy?
        for k1, k2 in itertools.combinations(node_ids, 2):
            if np.any(nodes[k1] & nodes[k2]):
                adj_matrix.loc[k1, k2] = 1

        edges = adj_matrix.stack(dropna=True)
        edges = edges.index.tolist()
        if self.verbose >= 1:
            print("...create %s edges." % (len(edges)))
            print("Finish TDA mapping")

        # transform the point mask into point ids in the nodes
        nodes = dict([(node_id, data_idx[nodes[node_id]]) for node_id in nodes.keys()])
        graph["nodes"] = nodes
        graph["edges"] = edges
        graph["samples"] = data_idx
        # ordered "node_keys", mapped with "node_positions" and "node_size" (lists)
        graph["node_keys"] = node_keys
        graph["node_positions"] = node_positions
        graph["node_sizes"] = node_sizes

        return graph

