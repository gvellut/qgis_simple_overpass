def classFactory(iface):  # pylint: disable=invalid-name
    from .simple_overpass import SimpleOverpassPlugin

    return SimpleOverpassPlugin(iface)
