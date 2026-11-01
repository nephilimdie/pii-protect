"""Service RAM probe: N concurrent A4 @300 DPI requests against a running service + tesseract VmHWM.

Why: RAM per worker for sizing mem_limit. Run inside the service container (needs tests/synth.py):
  docker exec <ctr> python /srv/bench/mem_probe.py tesseract 4   # while sampling `docker stats`
Prints {"engine","concurrent","wall_s","tesseract_peak_rss_mib"}; key from OCR_INTERNAL_API_KEY.
"""
import glob, io, json, os, sys, threading, time, urllib.request, uuid
sys.path.insert(0, "/srv/tests")
from synth import make_page
buf = io.BytesIO(); make_page(scribble=True).image.save(buf, "PNG"); png = buf.getvalue()
engine = sys.argv[1]; n = int(sys.argv[2])
def post():
    b = uuid.uuid4().hex
    body = (f"--{b}\r\nContent-Disposition: form-data; name=\"engine\"\r\n\r\n{engine}\r\n--{b}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"p.png\"\r\nContent-Type: image/png\r\n\r\n").encode() + png + f"\r\n--{b}--\r\n".encode()
    r = urllib.request.Request("http://127.0.0.1:8090/v1/ocr", body, {"Content-Type": f"multipart/form-data; boundary={b}", "X-Internal-Key": os.environ["OCR_INTERNAL_API_KEY"]})
    urllib.request.urlopen(r, timeout=300).read()
hwm = {"tesseract": 0}; stop = False
def sample():
    while not stop:
        for p in glob.glob("/proc/[0-9]*/status"):
            try:
                s = open(p).read()
                if "Name:\ttesseract" in s:
                    hwm["tesseract"] = max(hwm["tesseract"], int(s.split("VmHWM:")[1].split()[0]) // 1024)
            except Exception: pass
        time.sleep(0.05)
threading.Thread(target=sample, daemon=True).start()
ts = [threading.Thread(target=post) for _ in range(n)]
t0 = time.perf_counter(); [t.start() for t in ts]; [t.join() for t in ts]
stop = True
print(json.dumps({"engine": engine, "concurrent": n, "wall_s": round(time.perf_counter() - t0, 2), "tesseract_peak_rss_mib": hwm["tesseract"]}))
