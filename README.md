# ALL-ISR feed bench

Repository: https://github.com/misterdallas/ALL-ISR-sim

Lab tool. It is not the integrator and it does not ship with it.

The bench emits AIS, ADS-B, radar plots, one UAS, and one USV on their own wires. Each feed has its own switch and its own target address. Tracks orbit inside 10 miles of Key West. Nothing here is a live receiver.

## Run

Start the integrator first, and set a listen address on each source you want to feed. The addresses below are the ones configured on this machine.

```
set PYTHONPATH=C:\Users\Dallas\Desktop\GrokBuild\ALL-ISR-bench\app;C:\Users\Dallas\Desktop\GrokBuild\ALL-ISR\app
python -m bench
```

Open `http://127.0.0.1:8770/`. Feeds stay off until you check them.

| Feed | Default target | Wire |
| --- | --- | --- |
| AIS | 127.0.0.1:10110 | TCP AIVDM lines |
| ADS-B | 127.0.0.1:30003 | TCP SBS-1 MSG,3 |
| Radar | 127.0.0.1:10010 | TCP CoT XML, site key-west |
| UAS | 127.0.0.1:14550 | UDP MAVLink |
| USV | 127.0.0.1:10011 | TCP CoT XML |

The integrator decides the icon from the protocol it parsed. AIS and the USV leave as boats. ADS-B and the UAS leave as planes. A radar plot stays a ground marker until fusion matches it. Fusion needs a second radar scan, so the match appears on the second send.

An AIS position report carries the MMSI. The ADS-B line carries callsign N123AQ. The USV CoT carries callsign USV-1. The MAVLink position does not carry a name.
