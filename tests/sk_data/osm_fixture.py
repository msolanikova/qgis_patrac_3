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
  <node id="31" lat="48.690" lon="21.190"/>
  <node id="32" lat="48.690" lon="21.220"/>
  <node id="33" lat="48.720" lon="21.220"/>
  <node id="34" lat="48.720" lon="21.190"/>
  <way id="10"><nd ref="1"/><nd ref="2"/><nd ref="3"/><nd ref="4"/><nd ref="1"/>
    <tag k="landuse" v="forest"/><tag k="name" v="A &quot;quoted&quot; wood"/></way>
  <way id="11"><nd ref="5"/><nd ref="6"/><tag k="highway" v="residential"/><tag k="name" v="Hlavna"/></way>
  <way id="12"><nd ref="7"/><nd ref="8"/><tag k="waterway" v="stream"/></way>
  <way id="13"><nd ref="9"/><nd ref="10"/><nd ref="11"/><nd ref="12"/><nd ref="9"/><tag k="building" v="yes"/></way>
  <way id="14"><nd ref="31"/><nd ref="32"/><nd ref="33"/><nd ref="34"/><nd ref="31"/></way>
  <relation id="100"><member type="way" ref="14" role="outer"/>
    <tag k="type" v="boundary"/><tag k="boundary" v="administrative"/><tag k="admin_level" v="4"/><tag k="name" v="Test kraj"/></relation>
</osm>
"""


def write_fixture(path):
    with open(path, "w", encoding="utf-8") as f:
        f.write(OSM_XML)
    return path
