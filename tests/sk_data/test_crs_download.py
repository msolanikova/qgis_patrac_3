import hashlib
import io
import os
import tempfile
import unittest

from shapely.geometry import Point

from tools.sk_data import download
from tools.sk_data.crs import project_geometries, to_sjtsk, wgs84_to_sjtsk


class FakeResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()


class CrsTest(unittest.TestCase):
    def test_kosice_uses_the_slovak_operation(self):
        x, y = wgs84_to_sjtsk().transform(21.2611, 48.7164)
        # EPSG:4836 result; the generic fallback (3) would give x=-262576.1, y=-1240028.3
        self.assertAlmostEqual(x, -262580.66, delta=0.5)
        self.assertAlmostEqual(y, -1240038.58, delta=0.5)

    def test_project_geometries_and_to_sjtsk(self):
        import geopandas as gpd
        gdf = gpd.GeoDataFrame({"name": ["k"]}, geometry=[Point(21.2611, 48.7164)], crs=4326)
        out = to_sjtsk(gdf)
        self.assertEqual(out.crs.to_epsg(), 5514)
        self.assertEqual(list(out["name"]), ["k"])
        self.assertAlmostEqual(out.geometry.iloc[0].x, -262580.66, delta=0.5)
        self.assertEqual(len(project_geometries([Point(21.0, 48.5)])), 1)


class DownloadTest(unittest.TestCase):
    def test_worldcover_tiles(self):
        self.assertEqual(download.worldcover_tiles((20.161, 48.313, 22.408, 49.04)), ["N48E018", "N48E021"])
        self.assertEqual(download.worldcover_tiles((16.934, 47.759, 17.985, 48.878)), ["N45E015", "N48E015"])
        self.assertEqual(download.worldcover_tiles((21.0, 48.0, 24.0, 51.0)), ["N48E021"])  # edges on tile borders

    def test_worldcover_url(self):
        self.assertTrue(download.worldcover_url("N48E021").endswith("ESA_WorldCover_10m_2021_v200_N48E021_Map.tif"))

    def test_download_writes_file_and_checksum(self):
        with tempfile.TemporaryDirectory() as d:
            dest = os.path.join(d, "sub", "f.bin")
            info = download.download("http://x/f", dest, opener=lambda u: FakeResponse(b"abc"))
            with open(dest, "rb") as f:
                self.assertEqual(f.read(), b"abc")
            self.assertFalse(os.path.exists(dest + ".part"))
            self.assertEqual(info["sha256"], hashlib.sha256(b"abc").hexdigest())
            self.assertEqual(info["bytes"], 3)

    def test_fetch_sources_skips_existing_files_and_writes_manifest(self):
        calls = []

        def opener(url):
            calls.append(url)
            return FakeResponse(b"data")

        with tempfile.TemporaryDirectory() as d:
            m1 = download.fetch_sources(d, (21.0, 48.5, 21.5, 48.9), opener=opener)
            self.assertEqual(len(calls), 2)  # the OSM extract and tile N48E021
            self.assertIn("osm", m1)
            self.assertIn("worldcover-N48E021", m1)
            m2 = download.fetch_sources(d, (21.0, 48.5, 21.5, 48.9), opener=opener)
            self.assertEqual(len(calls), 2)  # nothing downloaded again
            self.assertEqual(set(m2), set(m1))
            self.assertTrue(os.path.exists(os.path.join(d, "source", "sources.json")))

    def test_fetch_sources_without_worldcover(self):
        calls = []
        with tempfile.TemporaryDirectory() as d:
            download.fetch_sources(d, (21.0, 48.5, 21.5, 48.9), opener=lambda u: calls.append(u) or FakeResponse(b"x"), include_worldcover=False)
        self.assertEqual(len(calls), 1)


if __name__ == "__main__":
    unittest.main()
