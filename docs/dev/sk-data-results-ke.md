# Košický kraj build results

Both builds passed validation. They were run in parallel with these commands (QGIS's Python, from the repository root):

```bash
"$QGIS_PY" -m tools.sk_data build --region ke --landcover osm --out "$HOME/patracdata/build/ke-osm"
"$QGIS_PY" -m tools.sk_data build --region ke --landcover osm+worldcover --out "$HOME/patracdata/build/ke-osm-worldcover"
```

`~/patracdata/kraje/ke` (the folder the plugin reads) is a copy of the `ke-osm-worldcover` build: it was made with
`cp -R` and `diff -rq` between the two folders printed nothing.

| | OSM only (`--landcover osm`) | OSM + WorldCover (`--landcover osm+worldcover`) |
|---|---|---|
| sectors | 106,447 | 109,978 |
| total_ha | 675,028 | 675,016 |
| region_ha | 675,079 | 675,079 |
| area_ratio | 0.9999 | 0.9999 |
| share_in_min_max | 0.801 | 0.748 |
| share_of_area_in_min_max | 0.881 | 0.851 |
| sectors_over_max | 20 | 14 |
| sectors_under_tiny | 4 | 3 |
| other_share_of_area | 0.5 | 0.0 |
| places | 439 | 439 |
| seconds | 382 | 1180 |

The two builds ran in parallel on the same machine, so the times may be slightly longer than for a build run alone.

## Sectors by type, OSM + WorldCover

| typ | sectors |
|---|---|
| AREZAS | 6,065 |
| ARUCZA | 914 |
| ELEKTR | 16 |
| HRBITO | 73 |
| KOLEJI | 103 |
| LETISTE | 21 |
| LPKROV | 4,007 |
| LPSTROM | 48,118 |
| MAZCHU | 385 |
| ORNAPU | 32,700 |
| OTHER | 5 |
| SADZAH | 484 |
| SKLADK | 94 |
| TRTRPO | 15,145 |
| ULOMIS | 177 |
| VINICE | 409 |
| VODPLO | 1,103 |
| ZAHPAR | 159 |

## Comparison with the prototype

The prototype (earlier runs of the same code, not repeated here) had 106,419 sectors, share_in_min_max 0.80 and
other_share_of_area 0.5 for OSM only, and 109,978 sectors, share_in_min_max 0.748 and other_share_of_area 0.0
for OSM + WorldCover. Its timings, about 6 and 20 minutes, are from those earlier runs.

The OSM + WorldCover build has the same sector count as the prototype. The OSM-only build has 28 more sectors
(106,447 vs 106,419) and one more tiny sector (4 vs 3). The cause was not investigated; both builds validate.

## Review

To be filled in by the user.
