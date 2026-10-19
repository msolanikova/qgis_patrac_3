# Košický kraj build results

Both builds were made with `python -m tools.sk_data build --region ke` and passed validation.

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

The two builds ran in parallel on the same machine, so the times are slightly longer than a build run alone.

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

The prototype had 106,419 sectors, share_in_min_max 0.80 and other_share_of_area 0.5 for OSM only (about 6 minutes),
and 109,978 sectors, share_in_min_max 0.748 and other_share_of_area 0.0 for OSM + WorldCover (about 20 minutes);
these builds reproduce it (OSM only: 28 more sectors; OSM + WorldCover: identical sector count).

## Review

To be filled in by the user.
