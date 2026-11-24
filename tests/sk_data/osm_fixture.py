"""A tiny hand-written OSM XML file around Kosice (about 3 x 3 km) for tests."""

OSM_XML = """<?xml version='1.0' encoding='UTF-8'?>
<osm version="0.6" generator="test">
  <node id="1" lat="48.700" lon="21.200"/>
  <node id="2" lat="48.700" lon="21.210"/>
  <node id="3" lat="48.710" lon="21.210"/>
  <node id="4" lat="48.710" lon="21.200"/>
  <node id="5" lat="48.695" lon="21.205"/>
  <node id="6" lat="48.715" lon="21.205"/>
  <node id="7" lat="48.705" lon="21.195"/>
  <node id="8" lat="48.705" lon="21.215"/>
  <node id="9" lat="48.7020" lon="21.2020"/>
  <node id="10" lat="48.7020" lon="21.2030"/>
  <node id="11" lat="48.7030" lon="21.2030"/>
  <node id="12" lat="48.7030" lon="21.2020"/>
  <node id="20" lat="48.705" lon="21.205"><tag k="place" v="village"/><tag k="name" v="Testov"/></node>
  <node id="21" lat="48.706" lon="21.215"><tag k="place" v="city"/><tag k="name" v="Testcity"/></node>
  <node id="31" lat="48.690" lon="21.190"/>
  <node id="32" lat="48.690" lon="21.220"/>
  <node id="33" lat="48.720" lon="21.220"/>
  <node id="34" lat="48.720" lon="21.190"/>
  <node id="41" lat="48.703" lon="21.203"/>
  <node id="42" lat="48.703" lon="21.207"/>
  <node id="43" lat="48.707" lon="21.207"/>
  <node id="44" lat="48.707" lon="21.203"/>
  <node id="45" lat="48.702" lon="21.212"/>
  <node id="46" lat="48.702" lon="21.218"/>
  <node id="47" lat="48.710" lon="21.218"/>
  <node id="48" lat="48.710" lon="21.212"/>
  <node id="51" lat="48.695" lon="21.195"/>
  <node id="52" lat="48.695" lon="21.219"/>
  <node id="53" lat="48.715" lon="21.219"/>
  <node id="54" lat="48.715" lon="21.195"/>
  <way id="10"><nd ref="1"/><nd ref="2"/><nd ref="3"/><nd ref="4"/><nd ref="1"/>
    <tag k="landuse" v="forest"/><tag k="name" v="A &quot;quoted&quot; wood"/></way>
  <way id="11"><nd ref="5"/><nd ref="6"/><tag k="highway" v="residential"/><tag k="name" v="Hlavna"/></way>
  <way id="12"><nd ref="7"/><nd ref="8"/><tag k="waterway" v="stream"/></way>
  <way id="13"><nd ref="9"/><nd ref="10"/><nd ref="11"/><nd ref="12"/><nd ref="9"/><tag k="building" v="yes"/></way>
  <way id="14"><nd ref="31"/><nd ref="32"/><nd ref="33"/><nd ref="34"/><nd ref="31"/></way>
  <way id="20"><nd ref="41"/><nd ref="42"/><nd ref="43"/><nd ref="44"/><nd ref="41"/></way>
  <way id="21"><nd ref="45"/><nd ref="46"/><nd ref="47"/><nd ref="48"/><nd ref="45"/></way>
  <way id="22"><nd ref="51"/><nd ref="52"/><nd ref="53"/><nd ref="54"/><nd ref="51"/></way>
  <relation id="100"><member type="way" ref="14" role="outer"/>
    <tag k="type" v="boundary"/><tag k="boundary" v="administrative"/><tag k="admin_level" v="4"/><tag k="name" v="Test kraj"/></relation>
  <relation id="101"><member type="way" ref="20" role="outer"/>
    <tag k="type" v="boundary"/><tag k="boundary" v="administrative"/><tag k="admin_level" v="8"/><tag k="name" v="Testov"/></relation>
  <relation id="102"><member type="way" ref="21" role="outer"/>
    <tag k="type" v="boundary"/><tag k="boundary" v="administrative"/><tag k="admin_level" v="5"/><tag k="name" v="Testcity"/></relation>
  <relation id="103"><member type="way" ref="22" role="outer"/>
    <tag k="type" v="boundary"/><tag k="boundary" v="administrative"/><tag k="admin_level" v="6"/><tag k="name" v="okres Test"/></relation>
</osm>
"""


def write_fixture(path):
    with open(path, "w", encoding="utf-8") as f:
        f.write(OSM_XML)
    return path


ROADS_OSM_XML = """<?xml version='1.0' encoding='UTF-8'?>
<osm version="0.6" generator="test">
  <node id="1" lat="48.690" lon="21.190"/>
  <node id="2" lat="48.690" lon="21.240"/>
  <node id="3" lat="48.717" lon="21.240"/>
  <node id="4" lat="48.717" lon="21.190"/>
  <node id="101" lat="48.700" lon="21.200"/>
  <node id="102" lat="48.700" lon="21.210"/>
  <node id="103" lat="48.700" lon="21.215"/>
  <node id="104" lat="48.700" lon="21.220"/>
  <node id="105" lat="48.706" lon="21.210"/>
  <node id="111" lat="48.692" lon="21.195"/>
  <node id="112" lat="48.692" lon="21.230"/>
  <node id="121" lat="48.696" lon="21.200"/>
  <node id="122" lat="48.696" lon="21.210"/>
  <node id="131" lat="48.702" lon="21.200"/>
  <node id="132" lat="48.702" lon="21.205"/>
  <node id="141" lat="48.704" lon="21.200"/>
  <node id="142" lat="48.704" lon="21.205"/>
  <node id="151" lat="48.708" lon="21.200"/>
  <node id="152" lat="48.708" lon="21.206"/>
  <node id="161" lat="48.697" lon="21.2125"/>
  <node id="162" lat="48.703" lon="21.2125"/>
  <node id="171" lat="48.700" lon="21.245"/>
  <node id="172" lat="48.700" lon="21.255"/>
  <node id="181" lat="48.712" lon="21.225"/>
  <node id="182" lat="48.712" lon="21.230"/>
  <node id="183" lat="48.715" lon="21.230"/>
  <node id="184" lat="48.715" lon="21.225"/>
  <node id="191" lat="48.710" lon="21.200"/>
  <node id="192" lat="48.710" lon="21.206"/>
  <node id="193" lat="48.711" lon="21.200"/>
  <node id="194" lat="48.711" lon="21.206"/>
  <way id="1"><nd ref="1"/><nd ref="2"/><nd ref="3"/><nd ref="4"/><nd ref="1"/></way>
  <way id="101"><nd ref="101"/><nd ref="102"/><nd ref="103"/>
    <tag k="highway" v="residential"/><tag k="name" v="Hlavn&#225; &quot;star&#225;&quot;"/></way>
  <way id="102"><nd ref="103"/><nd ref="104"/>
    <tag k="highway" v="unclassified"/><tag k="surface" v="gravel"/></way>
  <way id="103"><nd ref="102"/><nd ref="105"/>
    <tag k="highway" v="track"/><tag k="tracktype" v="grade2"/></way>
  <way id="111"><nd ref="111"/><nd ref="112"/><tag k="highway" v="motorway"/></way>
  <way id="121"><nd ref="121"/><nd ref="122"/><tag k="highway" v="residential"/><tag k="tunnel" v="yes"/></way>
  <way id="131"><nd ref="131"/><nd ref="132"/><tag k="highway" v="footway"/><tag k="footway" v="sidewalk"/></way>
  <way id="141"><nd ref="141"/><nd ref="142"/><tag k="highway" v="service"/><tag k="service" v="driveway"/></way>
  <way id="151"><nd ref="151"/><nd ref="152"/><tag k="highway" v="track"/><tag k="access" v="private"/></way>
  <way id="161"><nd ref="161"/><nd ref="162"/><tag k="highway" v="path"/></way>
  <way id="171"><nd ref="171"/><nd ref="172"/><tag k="highway" v="track"/></way>
  <way id="181"><nd ref="181"/><nd ref="182"/><nd ref="183"/><nd ref="184"/><nd ref="181"/><tag k="highway" v="track"/></way>
  <way id="191"><nd ref="191"/><nd ref="192"/><tag k="highway" v="path"/><tag k="sac_scale" v="alpine_hiking"/></way>
  <way id="193"><nd ref="193"/><nd ref="194"/><tag k="highway" v="footway"/><tag k="indoor" v="yes"/></way>
  <relation id="900"><member type="way" ref="1" role="outer"/>
    <tag k="type" v="boundary"/><tag k="boundary" v="administrative"/><tag k="admin_level" v="4"/><tag k="name" v="Road kraj"/></relation>
</osm>
"""

# The way ids of ROADS_OSM_XML, the road pieces they give inside "Road kraj" (see test_roads.RegionRoadsTest):
#   101 residential street, cut at the junction node 102 where the track 103 ends -> 2 pieces (about 736 m and 368 m)
#   102 unclassified, surface=gravel, continues the street through node 103 but is not chained to it -> 1 piece (368 m)
#   103 track, tracktype=grade2 -> 1 piece (667 m)
#   161 path crossing the street without a shared node -> 1 piece (667 m)
#   181 closed track ring -> 1 piece (about 1400 m)
# Not roads: 111 motorway, 121 tunnel, 131 sidewalk, 141 driveway, 151 access=private, 191 sac_scale=alpine_hiking,
# 193 indoor=yes; 171 is a track outside the
# relation (its midpoint lies outside, but inside the padded bounding box).


def write_roads_fixture(path):
    with open(path, "w", encoding="utf-8") as f:
        f.write(ROADS_OSM_XML)
    return path
