In the tree : sort the features by Bounding Box area (use the lat lon coordinates even though it won't be a real area : do not reproject).
If multiple by exact same area (like maybe for the points the area will all be 0 : first in the list) : order those by id ASC to separate between them. So the returned objects have a stable position.
Do it for both nearby + enclosing.