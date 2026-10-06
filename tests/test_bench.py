import json
import socket
import tempfile
import threading
import unittest
import urllib.request
from pathlib import Path

from allisr.engine import Engine
from allisr.fusion import haversine_m
from allisr.listen import Listeners
from allisr.parse import parse
from bench.feeds import KEY_WEST, messages
from bench.server import serve


class OrbitTests(unittest.TestCase):
    def test_ais_moves_inside_ten_miles(self):
        start = parse("aivdm", messages(0)["ais"][1], "LIVE")[0]
        later = parse("aivdm", messages(600)["ais"][1], "LIVE")[0]
        self.assertGreater(
            haversine_m(start.location["lat"], start.location["lon"], later.location["lat"], later.location["lon"]),
            1000,
        )
        for entity in (start, later):
            self.assertLess(
                haversine_m(entity.location["lat"], entity.location["lon"], KEY_WEST[0], KEY_WEST[1]),
                10 * 1609.344,
            )

    def test_only_an_enabled_feed_reaches_the_integrator(self):
        with tempfile.TemporaryDirectory() as tmp:
            engine = Engine(tmp)
            engine.add_inlet("ship", "Ship", "", "ais")
            engine.add_inlet("plane", "Plane", "", "adsb")
            engine.set_inlet_listen("ship", "127.0.0.1:0")
            engine.set_inlet_listen("plane", "127.0.0.1:0")
            listeners = Listeners(engine)
            listeners.sync()
            try:
                ports = {item.source_id: item.listen for item in engine.inlets}
                bench = serve(0)
                thread = threading.Thread(target=bench.serve_forever, daemon=True)
                thread.start()
                try:
                    bench.bench.set_feed("ais", True, ports["ship"])
                    bench.bench.set_feed("adsb", False, ports["plane"])
                    for _ in range(30):
                        if any(item.ontology_template == "ais" for item in engine.store.snapshot()):
                            break
                        threading.Event().wait(0.05)
                    kinds = {item.ontology_template for item in engine.store.snapshot()}
                    self.assertIn("ais", kinds)
                    self.assertNotIn("adsb", kinds)
                    self.assertTrue(all(item.provenance == "LIVE" for item in engine.store.snapshot()))
                finally:
                    bench.bench_stop.set()
                    bench.shutdown()
            finally:
                listeners.close()


class PageTests(unittest.TestCase):
    def test_page_lists_each_feed_off(self):
        server = serve(0)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            base = f"http://127.0.0.1:{server.server_address[1]}"
            page = urllib.request.urlopen(base + "/").read().decode("utf-8")
            self.assertIn("ALL-ISR FEED BENCH", page)
            self.assertIn("not the integrator", page)
            state = json.load(urllib.request.urlopen(base + "/api/state"))
            self.assertEqual([row["id"] for row in state["feeds"]], ["ais", "adsb", "radar", "uas", "usv"])
            self.assertTrue(all(not row["enabled"] for row in state["feeds"]))
            body = json.dumps({"id": "usv", "enabled": True, "target": "127.0.0.1:9"}).encode()
            updated = json.load(urllib.request.urlopen(urllib.request.Request(
                base + "/api/feed", data=body, headers={"Content-Type": "application/json"}, method="POST"
            )))
            usv = next(row for row in updated["feeds"] if row["id"] == "usv")
            self.assertTrue(usv["enabled"])
            self.assertNotEqual(usv["last"], "sent")
        finally:
            server.bench_stop.set()
            server.shutdown()


if __name__ == "__main__":
    unittest.main()
