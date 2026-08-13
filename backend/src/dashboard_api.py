from http.server import BaseHTTPRequestHandler, HTTPServer
import json

from memory import get_call_analytics


class AnalyticsHandler(BaseHTTPRequestHandler):

    def do_GET(self):
        if self.path != "/analytics":
            self.send_response(404)
            self.end_headers()
            return

        data = get_call_analytics()

        body = json.dumps(data).encode("utf-8")

        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()

        self.wfile.write(body)

    def log_message(self, format, *args):
        pass


if __name__ == "__main__":
    server = HTTPServer(("127.0.0.1", 8001), AnalyticsHandler)

    print("Analytics API running at http://127.0.0.1:8001")

    server.serve_forever()
