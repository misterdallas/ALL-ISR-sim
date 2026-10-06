"""Key West orbits spoken as real feed wires. This process is not the integrator."""

import socket
from math import cos, radians, sin

from allisr.parse import encode_aivdm, encode_mavlink_position

KEY_WEST = (24.5553, -81.7800)
_MILE_M = 1609.344

DEFAULTS = {
    "ais": "127.0.0.1:10110",
    "adsb": "127.0.0.1:30003",
    "radar": "127.0.0.1:10010",
    "uas": "127.0.0.1:14550",
    "usv": "127.0.0.1:10011",
}

LABELS = {
    "ais": "AIS",
    "adsb": "ADS-B",
    "radar": "Radar",
    "uas": "UAS",
    "usv": "USV",
}

NOTES = {
    "ais": "TCP AIVDM. Two boats. The position report carries the MMSI, not a name.",
    "adsb": "TCP SBS-1 MSG,3. One airplane, callsign N123AQ.",
    "radar": "TCP CoT. Key West plots KW-PLOT, KW-AIR, and KW-DARK. One scan per send.",
    "uas": "UDP MAVLink. System 21. The position message has no callsign.",
    "usv": "TCP CoT. Callsign USV-1.",
}


def _point(radius_mi: float, bearing_deg: float) -> tuple[float, float]:
    rad = radians(bearing_deg)
    north_m = radius_mi * _MILE_M * cos(rad)
    east_m = radius_mi * _MILE_M * sin(rad)
    lat = KEY_WEST[0] + north_m / 111320
    lon = KEY_WEST[1] + east_m / (111320 * cos(radians(KEY_WEST[0])))
    return lat, lon


def _place(radius_mi, mps, phase_deg, elapsed_s, clockwise=True):
    radius_m = radius_mi * _MILE_M
    turn = (mps / radius_m) * elapsed_s
    phase = radians(phase_deg)
    bearing = phase + (turn if clockwise else -turn)
    bearing_deg = (bearing * 180 / 3.141592653589793) % 360
    course = (bearing_deg + (90 if clockwise else -90)) % 360
    lat, lon = _point(radius_mi, bearing_deg)
    return lat, lon, course


def _radar(uid, lat, lon, callsign, mps, course, alt):
    return (
        f"<event version='2.0' uid='{uid}' type='a-u-G' how='m-s'>"
        f"<point lat='{lat:.6f}' lon='{lon:.6f}' hae='{alt}' ce='40' le='40'/>"
        f"<detail><contact callsign='{callsign}'/>"
        f"<track course='{course:.1f}' speed='{mps:.2f}'/>"
        f"<_allisr_ template='radar' site='key-west'/></detail></event>"
    )


def _sbs(icao, callsign, lat, lon, alt_m, mps, course):
    knots = mps / 0.514444
    feet = int(round(alt_m / 0.3048))
    name = f"{callsign:<8}"
    return (
        f"MSG,3,1,1,{icao},1,2026/10/05,12:00:00.000,2026/10/05,12:00:00.000,"
        f"{name},{feet},{knots:.0f},{course:.0f},{lat:.6f},{lon:.6f},0,0,0,0\n"
    )


def messages(elapsed_s: float) -> dict[str, tuple[str, bytes]]:
    """Return transport and payload for every feed at this moment on the orbit."""
    fish_lat, fish_lon, fish_crs = _place(5.0, 6.5, 10, elapsed_s, True)
    tug_lat, tug_lon, tug_crs = _place(7.5, 5.0, 190, elapsed_s, False)
    usv_lat, usv_lon, usv_crs = _place(6.2, 4.2, 80, elapsed_s, True)
    air_lat, air_lon, air_crs = _place(3.2, 32.0, 25, elapsed_s, True)
    uas_lat, uas_lon, uas_crs = _place(8.2, 16.0, 250, elapsed_s, True)
    dark_lat, dark_lon, dark_crs = _place(9.5, 3.0, 130, elapsed_s, False)
    ais = "\n".join(
        (
            encode_aivdm(366123456, fish_lat, fish_lon, sog_knots=6.5 / 0.514444, cog=fish_crs),
            encode_aivdm(366778899, tug_lat, tug_lon, sog_knots=5.0 / 0.514444, cog=tug_crs),
        )
    ) + "\n"
    radar = "".join(
        (
            _radar("radar-kw-fish", fish_lat + 0.0007, fish_lon, "KW-PLOT", 6.5, fish_crs, 0),
            _radar("radar-kw-air", air_lat + 0.0007, air_lon, "KW-AIR", 32.0, air_crs, 800),
            _radar("radar-kw-dark", dark_lat, dark_lon, "KW-DARK", 3.0, dark_crs, 0),
        )
    )
    usv = (
        f"<event version='2.0' uid='usv-kw-1' type='a-u-S' how='m-g'>"
        f"<point lat='{usv_lat:.6f}' lon='{usv_lon:.6f}' hae='0' ce='20' le='20'/>"
        f"<detail><contact callsign='USV-1'/>"
        f"<track course='{usv_crs:.1f}' speed='4.20'/>"
        f"<_allisr_ template='usv'/></detail></event>"
    )
    uas = encode_mavlink_position(
        21,
        uas_lat,
        uas_lon,
        150,
        int(16.0 * cos(radians(uas_crs)) * 100),
        int(16.0 * sin(radians(uas_crs)) * 100),
        0,
    )
    return {
        "ais": ("tcp", ais.encode("ascii")),
        "adsb": ("tcp", _sbs("A1B2C3", "N123AQ", air_lat, air_lon, 800, 32.0, air_crs).encode("ascii")),
        "radar": ("tcp", radar.encode("ascii")),
        "uas": ("udp", uas),
        "usv": ("tcp", usv.encode("ascii")),
    }


def send(target: str, mode: str, payload: bytes):
    host, sep, port = (target or "").rpartition(":")
    if not sep or not port.isdigit():
        raise OSError("target must be host:port")
    address = (host or "127.0.0.1", int(port))
    if mode == "udp":
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            sock.sendto(payload, address)
        finally:
            sock.close()
        return
    with socket.create_connection(address, timeout=3) as conn:
        conn.sendall(payload)
