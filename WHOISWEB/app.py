# [S01] Cấu hình, hằng số, kết nối SQLite, khởi tạo bảng
import os, re, time, uuid, json, hmac, sqlite3, unicodedata, html
from urllib.parse import unquote
from flask import Flask, request, jsonify, render_template, send_from_directory, g, abort

BASE = os.path.dirname(os.path.abspath(__file__))
UP = os.path.join(BASE, "uploads"); os.makedirs(UP, exist_ok=True)
DB, LOG = os.path.join(BASE, "forum.db"), os.path.join(BASE, "attack.log")
MAX_VISIBLE = 3                                    # chỉ hiện N bài gần nhất
MAX_INPUT = 300                                    # độ dài tối đa của payload
WAF_LEVEL = os.environ.get("WAF_LEVEL", "basic")   # basic | strict
ADMIN_TOKEN = os.environ.get("ADMIN_TOKEN", "")    # trống = tắt /__log
MAGIC = {b"\x89PNG": "png", b"\xff\xd8\xff": "jpg", b"GIF8": "gif", b"RIFF": "webp"}
app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 2 * 1024 * 1024  # ảnh tối đa 2MB

def db():
    if "db" not in g:
        g.db = sqlite3.connect(DB); g.db.row_factory = sqlite3.Row
    return g.db

@app.teardown_appcontext
def _close(_):
    d = g.pop("db", None)
    if d: d.close()

def init_db():
    with sqlite3.connect(DB) as c:
        c.executescript("""CREATE TABLE IF NOT EXISTS posts(id INTEGER PRIMARY KEY AUTOINCREMENT,
          kind TEXT, body TEXT, image TEXT, likes INTEGER DEFAULT 0, ts REAL);
          CREATE TABLE IF NOT EXISTS comments(id INTEGER PRIMARY KEY AUTOINCREMENT,
          post_id INTEGER, body TEXT, ts REAL);""")
    open(LOG, "a").close()

# [S02] Log JSON-lines, rate limit theo IP, header bảo mật
def log_event(kind, **d):
    rec = {"t": time.strftime("%Y-%m-%d %H:%M:%S"), "ip": request.remote_addr,
           "ua": request.headers.get("User-Agent", "")[:120], "kind": kind, **d}
    with open(LOG, "a", encoding="utf-8") as f: f.write(json.dumps(rec, ensure_ascii=False) + "\n")

HITS = {}
def limited(n=20, win=60):
    k, now = (request.remote_addr, request.endpoint), time.time()
    HITS[k] = [t for t in HITS.get(k, []) if now - t < win] + [now]
    return len(HITS[k]) > n

@app.after_request
def headers(r):
    r.headers["Content-Security-Policy"] = "default-src 'self'; img-src 'self'; object-src 'none'"
    r.headers["X-Content-Type-Options"] = "nosniff"
    return r

# [S03] WAF: 5 nhóm rule + normalize (basic: chỉ soi raw, strict: soi cả bản đã giải mã)
RULES = [(n, re.compile(p, re.I | re.S)) for n, p in [
    ("XSS", r"<\s*/?\s*(script|img|svg|iframe|object|embed|body|style|link|meta)|\bon\w+\s*=|javascript\s*:|data\s*:\s*text/html"),
    ("SQLI", r"\bunion\b.{0,20}\bselect\b|\bor\b\s+\d+\s*=\s*\d+|'\s*(or|and)\s|;\s*drop\b|--\s|/\*|\bsleep\s*\("),
    ("CMDI", r"(;|\|\||&&|\||`|\$\()\s*(ls|cat|id|whoami|curl|wget|nc|bash|sh|powershell|cmd)\b"),
    ("TRAVERSAL", r"\.\./|\.\.\\|/etc/(passwd|shadow)|c:\\windows"),
    ("SSTI", r"\{\{.*\}\}|\$\{.*\}|<%.*%>|\{%.*%\}"),
]]

def normalize(s):
    for _ in range(3):                              # giải mã nhiều lớp: %3C, &lt;, ...
        n = html.unescape(unquote(s))
        if n == s: break
        s = n
    s = unicodedata.normalize("NFKC", s).replace("\x00", "")
    return re.sub(r"/\*.*?\*/", " ", s)             # /**/ dùng làm khoảng trắng

def scan(text):
    return next((n for n, rx in RULES if rx.search(text)), None)

def waf(text):  # -> (rule_chặn, rule_bypass_nghi_ngờ)
    if len(text) > MAX_INPUT: return "LENGTH", None
    if hit := scan(text): return hit, None
    deep = scan(normalize(text))
    if deep and WAF_LEVEL == "strict": return deep, None
    return None, deep                               # deep != None: qua được WAF basic bằng encode

# [S04] Bộ phân tích lệnh (DSL sandbox): trả "hiệu ứng" cho client, KHÔNG eval/shell
THEMES = {
    "lab": {"--bg": "#e8edef", "--card": "#fbfcfc", "--text": "#17262e", "--accent": "#0b6e78", "--muted": "#6b7c85"},
    "dark": {"--bg": "#10161a", "--card": "#182027", "--text": "#dfe8ec", "--accent": "#4fc3cf", "--muted": "#7d8f98"},
    "hacker": {"--bg": "#000", "--card": "#07130a", "--text": "#33ff66", "--accent": "#00ff41", "--muted": "#1f8f3a"},
    "retro": {"--bg": "#2b1d0e", "--card": "#3a2812", "--text": "#ffb000", "--accent": "#ffd166", "--muted": "#a8741a"},
}
SLOTS = {"bg": "--bg", "text": "--text", "accent": "--accent", "card": "--card"}
COLOR = re.compile(r"^(#[0-9a-fA-F]{3,8}|[a-zA-Z]{3,20})$")
FAKE = {"whoami": "guest", "id": "uid=1001(guest) gid=1001(guest)", "pwd": "/var/www/sandbox",
        "ls": "index.html  static/  uploads/", "uname": "SandboxOS 0.0"}  # shell giả để dụ hành vi
HELP = ('help | reset | theme lab|dark|hacker|retro | color bg|text|accent|card <#hex|tên> | font 12-24 | '
        'title <chữ> | hero <chữ> | replace "a" -> "b" | whoami id pwd ls uname')

def run(cmd):
    m = re.match(r"^(\w+)\s*(.*)$", cmd, re.S)
    if not m: return {"ok": False, "out": "Lệnh rỗng hoặc sai cú pháp. Gõ help."}
    name, arg = m.group(1).lower(), m.group(2).strip()
    ok = lambda out, *fx: {"ok": True, "out": out, "fx": list(fx)}
    if name == "help": return ok(HELP)
    if name == "reset": return ok("Đã reset giao diện.", {"t": "reset"})
    if name == "theme" and arg in THEMES: return ok(f"Theme: {arg}", {"t": "vars", "v": THEMES[arg]})
    if name == "color":
        p = arg.split()
        if len(p) == 2 and p[0] in SLOTS and COLOR.match(p[1]):
            return ok(f"{p[0]} = {p[1]}", {"t": "vars", "v": {SLOTS[p[0]]: p[1]}})
    if name == "font" and arg.isdigit() and 12 <= int(arg) <= 24: return ok(f"Cỡ chữ {arg}px", {"t": "font", "v": int(arg)})
    if name in ("title", "hero") and 0 < len(arg) <= 60: return ok(f"Đã đổi {name}.", {"t": name, "v": arg})
    if name == "replace":
        r = re.match(r'^"(.{1,40})"\s*->\s*"(.{0,40})"$', arg)
        if r: return ok(f'Thay "{r[1]}" bằng "{r[2]}"', {"t": "replace", "a": r[1], "b": r[2]})
    if name in FAKE: return ok(FAKE[name])
    return {"ok": False, "out": f"'{name}' không tồn tại hoặc sai cú pháp. Gõ help."}

# [S05] API diễn đàn: danh sách (3 bài gần nhất + filter), đăng bài/ảnh, comment, like
@app.get("/")
def index(): return render_template("index.html")

@app.get("/api/posts")
def list_posts():
    f, q, a = request.args.get("filter", "all"), "SELECT * FROM posts", ()
    if f in ("text", "image"): q, a = q + " WHERE kind=?", (f,)
    rows = db().execute(q + " ORDER BY id DESC LIMIT ?", a + (MAX_VISIBLE,)).fetchall()
    out = []
    for r in rows:
        cm = db().execute("SELECT body FROM comments WHERE post_id=? ORDER BY id DESC LIMIT 5", (r["id"],)).fetchall()
        out.append({**dict(r), "comments": [c["body"] for c in cm]})
    return jsonify(out)

@app.post("/api/posts")
def new_post():
    if limited(10): return jsonify(error="Đăng quá nhanh, thử lại sau."), 429
    body, img = (request.form.get("body") or "").strip()[:500], None
    f = request.files.get("image")
    if f and f.filename:                            # kiểm magic bytes, đặt tên ngẫu nhiên
        head = f.read(12); f.seek(0)
        ext = next((v for k, v in MAGIC.items() if head.startswith(k)), None)
        if not ext or (ext == "webp" and head[8:12] != b"WEBP"): return jsonify(error="Chỉ nhận png/jpg/gif/webp."), 400
        img = f"{uuid.uuid4().hex}.{ext}"; f.save(os.path.join(UP, img))
    elif not body: return jsonify(error="Bài đăng đang trống."), 400
    if hit := scan(body): log_event("post_suspicious", rule=hit, body=body[:200])
    db().execute("INSERT INTO posts(kind,body,image,ts) VALUES(?,?,?,?)", ("image" if img else "text", body, img, time.time()))
    db().commit(); return jsonify(ok=True)

@app.post("/api/posts/<int:pid>/comments")
def comment(pid):
    if limited(20): return jsonify(error="Quá nhanh."), 429
    body = ((request.get_json(silent=True) or {}).get("body") or "").strip()[:200]
    if body: db().execute("INSERT INTO comments(post_id,body,ts) VALUES(?,?,?)", (pid, body, time.time())); db().commit()
    return jsonify(ok=True)

@app.post("/api/posts/<int:pid>/like")
def like(pid):  # chỉ bài text mới có like
    db().execute("UPDATE posts SET likes=likes+1 WHERE id=? AND kind='text'", (pid,)); db().commit()
    return jsonify(ok=True)

@app.get("/uploads/<path:name>")
def uploads(name): return send_from_directory(UP, name)

# [S06] API thực thi lệnh: WAF -> parser -> log; xem log; chạy server
@app.post("/api/exec")
def api_exec():
    if limited(30): return jsonify(ok=False, out="Chậm lại chút (rate limit)."), 429
    text = (request.get_json(silent=True) or {}).get("input", "")
    text = text if isinstance(text, str) else ""
    blocked, bypass = waf(text)
    if blocked:
        log_event("blocked", rule=blocked, level=WAF_LEVEL, input=text[:MAX_INPUT])
        return jsonify(ok=False, out=f"WAF chặn: {blocked}"), 403
    res = run(text.strip())
    log_event("exec", ok=res["ok"], bypass_suspected=bypass, input=text[:MAX_INPUT])
    return jsonify(res)

@app.get("/__log")
def view_log():
    if not ADMIN_TOKEN or not hmac.compare_digest(request.args.get("token", ""), ADMIN_TOKEN): abort(404)
    with open(LOG, encoding="utf-8") as f: lines = f.readlines()[-200:]
    return "".join(lines), 200, {"Content-Type": "text/plain; charset=utf-8"}

init_db()
if __name__ == "__main__":
    app.run(host=os.environ.get("HOST", "127.0.0.1"), port=5000)
