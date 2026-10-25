from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import random
from pathlib import Path


class Handler(BaseHTTPRequestHandler):

    def send_json(self, data, status=200):
        body = json.dumps(data).encode()

        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()

        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/api/random":
            score = random.randint(0, 100)

            self.send_json({
                "score": score,
                "message": "Tục à nhen." if score > 50 else "Hài vậy ba."
            })
            return

        if self.path == "/health":
            self.send_json({
                "status": "ok"
            })
            return

        if self.path == "/" or self.path == "/index.html":
            self.send_file("ihateyou.html")
            return

        self.send_json({"error": "Not found"}, 404)

    def do_POST(self):
        if self.path != "/api/rate":
            self.send_json({"error": "Not found"}, 404)
            return

        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length)

        data = json.loads(body)

        name = data.get("name", "").strip()

        score = random.randint(0, 100)

        self.send_json({
            "name": name,
            "score": score,
            "message": "Đỉnh cao tục." if score >= 80
                       else "Tục vừa đủ." if score >= 40
                       else "Chưa đủ tục."
        })

    def send_file(self, filename, content_type="text/html"):
        path = Path(filename)

        if not path.exists():
            self.send_json({"error": "File not found"}, 404)
            return

        body = path.read_bytes()

        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()

        self.wfile.write(body)


server = HTTPServer(("127.0.0.1", 8000), Handler)

print("Server running at http://127.0.0.1:8000")

server.serve_forever()