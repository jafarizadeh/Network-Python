import socket
import http.server
import urllib.parse
from udpchat.protocol import make_packet, PUBLIC_MSG, JOIN

# Configuration
CHAT_SERVER_IP = "192.168.1.46"   # Replace with actual server IP if needed
CHAT_SERVER_PORT = 5000        # Default UDP chat server port


class MessageHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(b"""
            <!DOCTYPE html>
            <html lang='en'>
            <head>
                <meta charset='UTF-8'>
                <title>UDP Web Chat</title>
            </head>
            <body style='font-family: sans-serif;'>
                <h2>Send Message to UDP Chat</h2>
                <form method='POST'>
                    <input name='msg' placeholder='Enter message' size='40'>
                    <input type='submit' value='Send'>
                </form>
            </body>
            </html>
        """)

    def do_POST(self):
        content_length = int(self.headers.get('Content-Length', 0))
        post_data = self.rfile.read(content_length).decode()
        data = urllib.parse.parse_qs(post_data)

        message = data.get("msg", [""])[0].strip()

        if message:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            try:
                # First register the WebUser in the chat server
                join_packet = make_packet(JOIN, name="WebUser")
                sock.sendto(join_packet, (CHAT_SERVER_IP, CHAT_SERVER_PORT))

                # Then send the actual chat message
                msg_packet = make_packet(PUBLIC_MSG, name="WebUser", text=message)
                sock.sendto(msg_packet, (CHAT_SERVER_IP, CHAT_SERVER_PORT))

            finally:
                sock.close()

        # Redirect back to GET page
        self.send_response(303)
        self.send_header("Location", "/")
        self.end_headers()


def run(port=8080):
    server_address = ('', port)
    httpd = http.server.HTTPServer(server_address, MessageHandler)
    print(f"Web interface available at http://localhost:{port}/")
    httpd.serve_forever()


if __name__ == "__main__":
    run()
