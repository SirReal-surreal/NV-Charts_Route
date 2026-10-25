#!/usr/bin/env python3
"""Liest Tracks und Marker aus NV Charts (navipack.trip) und erzeugt routenkarte.html.

Aufruf: python3 build.py [pfad/zu/navipack.trip]
        python3 build.py --standalone   (Datei zum Weitergeben, ohne eigene Daten)
"""
import base64, json, math, os, shutil, sqlite3, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
if sys.platform == "win32":
    DEFAULT_DB = os.path.join(os.environ.get("ProgramData", r"C:\ProgramData"), "nvcharts", "navipack.trip")
else:
    DEFAULT_DB = os.path.expanduser("~/Library/Application Support/nvcharts/navipack.trip")
W = 2 * math.pi * 6371000  # Weltbreite in NV-Koordinaten (Kugelradius 6371 km, Ursprung oben links)


def xy_to_lonlat(x, y):
    lon = x / W * 360 - 180
    lat = math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * y / W))))
    return lon, lat


def standalone():
    """Eine HTML-Datei mit eingebautem SQLite-Leser; der Empfänger wählt seine eigene navipack.trip."""
    vendor = os.path.join(HERE, "vendor")
    with open(os.path.join(vendor, "sql-wasm.js"), encoding="utf-8") as f:
        js = f.read()
    with open(os.path.join(vendor, "sql-wasm.wasm"), "rb") as f:
        wasm = base64.b64encode(f.read()).decode()
    with open(os.path.join(HERE, "template.html"), encoding="utf-8") as f:
        html = f.read()
    inline = '<script>window.SQL_WASM=Uint8Array.from(atob("%s"),c=>c.charCodeAt(0));</script>\n<script>%s</script>' % (wasm, js)
    html = html.replace("<!--__SQLJS__-->", inline)
    out = os.path.join(HERE, "NV-Routenkarte.html")
    with open(out, "w", encoding="utf-8") as f:
        f.write(html)
    print("Standalone -> %s" % out)


def main():
    if "--standalone" in sys.argv:
        return standalone()
    src = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_DB
    with tempfile.TemporaryDirectory() as tmp:  # Kopie, damit die App-Datenbank unberührt bleibt
        db = os.path.join(tmp, "trip.db")
        shutil.copy(src, db)
        con = sqlite3.connect(db)
        tracks, markers = [], []
        for k, v in con.execute("select k, v from nkvt where k like 'u/trk/%/lola' and del=0"):
            tid = k.split("/")[2]
            pts = json.loads(v)
            if len(pts) < 2:
                continue
            row = con.execute("select v from nkvt where k=? and del=0", ("u/trk/%s/track" % tid,)).fetchone()
            if not row:
                continue  # ohne Metadaten-Eintrag zeigt NV Charts den Track auch nicht (Überrest)
            m = json.loads(row[0])
            tracks.append({
                "id": tid,
                "name": m.get("name") or m.get("anam") or "(ohne Namen)",  # anam: "Start --> Ziel", wenn kein eigener Name vergeben wurde
                "trip": m.get("trip") or "(ohne Reise)",
                "pts": [[round(p[0], 5), round(p[1], 5), int(p[2])] for p in pts],
            })
        for k, v in con.execute("select k, v from nkvt where k like 'u/mrk/%/marker' and del=0"):
            m = json.loads(v)
            lon, lat = xy_to_lonlat(*m["xy"])
            markers.append({"name": m.get("name") or "", "note": m.get("anam") or "",
                            "ts": m.get("id"), "lat": round(lat, 5), "lon": round(lon, 5)})
        con.close()  # unter Windows lässt sich die Kopie sonst nicht löschen
    tracks.sort(key=lambda t: t["pts"][0][2])
    data = json.dumps({"tracks": tracks, "markers": markers}, ensure_ascii=False, separators=(",", ":"))
    data = data.replace("</", "<\\/")
    with open(os.path.join(HERE, "template.html"), encoding="utf-8") as f:
        html = f.read().replace("/*__DATA__*/null", data)
    out = os.path.join(HERE, "routenkarte.html")
    with open(out, "w", encoding="utf-8") as f:
        f.write(html)
    print("%d Tracks, %d Marker -> %s" % (len(tracks), len(markers), out))


main()
