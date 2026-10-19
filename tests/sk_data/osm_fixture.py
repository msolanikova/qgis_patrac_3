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
