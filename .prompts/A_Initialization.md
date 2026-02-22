copy the spirit of /Users/guilhem/Documents/projects/___cloned/qgis_osminfo

use the simple_overpass folder as the root of the plugin. Follow the convention for python + tool in /Users/guilhem/Documents/projects/github/qgis_simple_browse
Make the code simple . You can create additional files but not too many.

Similar menu in web (with the Simple Overpass name)
discard the About menu. No mention of NextBox anywhere.

Settings : like OSM Info : in the QGIS setting panel (its own entry in the settings menu tree): also openable from the : Web > Simple Overpass > Settings menu
Use https://overpass-api.de/api/interpreter as the default API. Instead of a combobox for Overpass Server and a list of prelisted API endpoints : Make it a freely editable text field that can be filled by the user.
Defauylt distance 15. Default timeout 30
Keep checkboxes for nearby / enclosing
Keep checkbox : Enable Debug

I want an additional checkbox (default checked) : Only include objects with tag
I want an additional text field / calendar (default empty) : it is to enter a date: it will add a [date:"2025-07-25T15:30:00Z"];  for filtering the date (it does not have to include a time : if the query demands it : use beginning of the chosen date ie midnight ). If empty : do not include a date in the query
I want a filter text field : like the user can enter name or highway to include only the object with that tag or something like building=house to filter. It will be applied to every query + type of objects.
I want a checkbox : Only center (default false). So instead of returning full geoms like OSM Info : it returns only a point.

Menu icon in the Plugin toolbar. Change the .svg in this repo.
When active, on map click : make queries

replace the queries below with the params + clicked location (in WGS 84)  + bbox in current QGIS interface + add some strings / queries based on params + replace the "+" with space if needed (this is just hte JSON encoding)
Alwyas include the tags in out.

If Only center is chosen : replace the nearby with center isntead of geoms. For enclosing : keep the bb.

These are the opoenstreetmap.org queries : 
nearby : 
{
    "data": "[timeout:10][out:json];(node(around:15,45.880732,6.052496);way(around:15,45.880732,6.052496););out+tags+geom(45.879063,6.048043,45.881984,6.059899);relation(around:15,45.880732,6.052496);out+geom(45.879063,6.048043,45.881984,6.059899);"
}

Or use : 

[out:json][timeout:10];
nwr(around:15, 45.880732, 6.052496)(if:count_tags() > 0);
out tags geom(45.8790, 6.0480, 45.8819, 6.0598);

Add if:count_tags() > 0 :  dependings if the settings calls for it

enclosing :
{
    "data": "[timeout:10][out:json];is_in(45.880732,6.052496)->.a;way(pivot.a);out+tags+bb;out+ids+geom(45.879063,6.048043,45.881984,6.059899);relation(pivot.a);out+tags+bb;"
}

On results : add them to the GUI as the results come. Beware : do not block completely the GUI while the tree    is updated from the data. The OSM Info plugin has a few seconds where the interface is blocked (beach ball).

In the result tree: keep the ways the features are represented in OSM info. The current right click menu : keep them BUT only on the root of the feature (so its main name if it has one or ID : not on each tag). 
Also add a Copy Name (if it has a name) or Copy ID to that menu : this will copy what the tree shows.
For the tags below in the tree : only entry in right click menu is Copy Value
The ctrl+c or cmd+c while selected does the same copy as what I described