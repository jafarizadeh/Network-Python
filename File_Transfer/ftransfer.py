import os
import posixpath
import http.server
import urllib.request, urllib.parse, urllib.error
import html
import shutil
import mimetypes
import re
from io import BytesIO
import socket
import logging


logging.basicConfig(
    level=logging.INFO, format='[%(asctime)s] [%(levelname)s] %(message)s',
    handlers=[
        logging.FileHandler('server.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

class SimpleHTTPRequestHandler(http.server.BaseHTTPRequestHandler):

    if not mimetypes.inited:
        mimetypes.init()

    extensions_map = mimetypes.types_map.copy()
    extensions_map.update({
        '': 'application/octet-stream',
        '.py': 'text/plain',
        '.c': 'text/plain',
        '.h': 'text/plain',
    })

    def __init__(self, *args, **kwargs):
        self.extensions_map = self.__class__.extensions_map
        super().__init__(*args, **kwargs)


    def do_GET(self):
        try:
            f = self.send_head()
            if f:
                self.copyfile(f, self.wfile)
                f.close()

                logging.info(f'GET request served: {self.path} from {self.client_address}')
        except Exception as e:
            self.send_error(500, "Internal server error")
            logging.error(f'GET request failed: {self.path} from {self.client_address} | Error: {e}')


    def do_HEAD(self):
        try:
            f = self.send_head()
            if f:
                f.close()
                logging.info(f'HEAD request processed: {self.path} from {self.client_address}')
        except Exception as e:
            self.send_error(500, "Internal server error")
            logging.error(f'HEAD request failed: {self.path} from {self.client_address} | Error: {e}')

    def do_POST(self):
        try:
            r, info = self.deal_post_data()
            client_ip = self.client_address[0]
            status = "Success" if r else "Failed"

            logging.info(f'POST upload {status} from {client_ip} | Info: {info}')
            html_response = f"""
            <!DOCTYPE html>
            <html>
            <head><title>Upload Result</title></head>
            <body>
                <h2>Upload Result</h2>
                <hr>
                <strong>{status}:</strong><br>
                {info}<br>
                <a href="{self.headers.get('referer', '/')}">Back</a>
            </body>
            </html>
            """

            encoded = html_response.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)
        except Exception as e:
            logging.error(f'POST upload failed from {self.client_address} | Error: {e}')
            self.send_error(500, "Upload faild: Internal server error")

    def deal_post_data(self):
        content_type = self.headers.get('content-type', '')
        if not content_type:
            logger.error("Content-Type header doesn't contain boundary")
            return False, "Content-Type header doesn't contain boundary"
        
        try:
            boundary = content_type.split("=")[1].encode()
        except IndexError:
            logger.error("Invalid Content-Type header format")
            return False, "Invalid Content-Type header format"
        
        remainbytes = int(self.headers.get('content-length', 0))
        logger.info(f'Remaining bytes to read: {remainbytes}')

        line = self.rfile.readline()
        remainbytes -= len(line)
        if not boundary in line:
            logger.error("Content NOT begin with boundary")
            return False, "Content NOT begin with boundary"
        
        line = self.rfile.readline()
        remainbytes -= len(line)

        fn = re.findall(r'Content-Disposition.*name="file"; filename="(.*)"', line.decode())

        if not fn:
            logger.error("Can't find out file name")
            return False, "Can't find out file name..."
        
        path = self.translate_path(self.path)
        filename = os.path.basename(fn[0])
        file_path = os.path.join(path, filename)

        line = self.rfile.readline()
        remainbytes -= len(line)
        line = self.rfile.readline()
        remainbytes -= len(line)
        
        try:
            with open(file_path, 'wb') as out:
                logger.info(f"Saving file to {file_path}")

                preline = self.rfile.readline()
                remainbytes -= len(preline)

                while remainbytes > 0:
                    line = self.rfile.readline()
                    remainbytes -= len(line)

                    if boundary in line:
                        preline = preline.rstrip(b'\r\n')
                        out.write(preline)
                        logger.info(f"File '{file_path}' Uploaded successfully")
                        return True, f"File '{file_path}' upload success!"
                    else:
                        out.write(preline)
                        preline = line
        except IOError as e:
            logger.error(f"Can't create file to write, IOError: {str(e)}")
            return False, "Can't create file to write, do you have permission to write?"
        
        except Exception as e:
            logger.exception("Unexpected error while processing POST data")
            return False, f"Unexpected error:{str(e)}"
        
        logger.error("Unexpected end of data")
        return False, "Unexpected end of data"
    
    def send_head(self):
        path = self.translate_path(self.path)
        f = None

        try:
            if os.path.isdir(path):
                if not self.path.endswith('/'):
                    self.send_response(301)
                    self.send_header("Location", self.path + '/')
                    self.end_headers()
                    logger.info(f"Redirecting to: {self.path + '/'}")
                    return None
                
                for index in ("index.html", "index.htm"):
                    index_path = os.path.join(path, index)
                    if os.path.exists(index_path):
                        path = index_path
                        break
                else:
                    return self.list_directory(path)
            ctype = self.guess_type(path)

            f = open(path, 'rb')
            fs = os.fstat(f.fileno())

            self.send_response(200)
            self.send_header("Content-type", ctype)
            self.send_header("Content-Length", str(fs.st_size))
            self.send_header("Last-Modified", self.date_time_string(fs.st_mtime))
            self.end_headers()

            logger.info(f"Serving file: {path} | Size: {fs.st_size} bytes")
            return f
        
        except IOError as e:
            self.send_error(404, "File not found")
            logger.error(f"File not found: {path} | Error: {str(e)}")
            return None
        
        except Exception as e:
            self.send_error(500, "Internal server error")
            logger.exception(f"Unexpected error in send_head() for path: {path}")
            return None

    def list_directory(self, path):
        try:
            entries = os.listdir(path)
        except OSError:
            self.send_error(404, "No permission to list directory")
            logger.error(f"No permission to list directory: {path}")
            return None
        
        entries.sort(key=lambda a: a.lower())
        displaypath = html.escape(urllib.parse.unquote(self.path))

        f = BytesIO()
        f.write(b'<!DOCTYPE html>\n')
        f.write(f"<html><head><title>Directory listing for {displaypath}</title></head>".encode())
        f.write(f"<body><h2>Directory listing for {displaypath}</h2><hr>".encode())

        f.write(b"""
            <form ENCTYPE="multipart/form-data" method="post">
                <input name="file" type="file"/>
                <input type="submit" value="Upload"/>
            </form><hr><ul>
        """)

        for name in entries:
            fullname = os.path.join(path, name)
            displayname = linkname = name

            if os.path.isdir(fullname):
                displayname += "/"
                linkname += "/"

            if os.path.islink(fullname):
                displayname += "@"

            f.write(f'<li><a href="{urllib.parse.quote(linkname)}">{html.escape(displayname)}</a></li>\n'.encode())

        f.write(b"</ul><hr></body></html>")
        length = f.tell()
        f.seek(0)

        self.send_response(200)
        self.send_header("Content-type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(length))
        self.end_headers()

        logger.info(f"Directory listed: {path}")
        return f
    
    def translate_path(self, path):
        try:
            path = path.split('?', 1)[0]
            path = path.split('#', 1)[0]

            path = posixpath.normpath(urllib.parse.unquote(path))
            parts = [p for p in path.split('/') if p not in ('', '.', '..')]

            base_path = os.getcwd()
            for part in parts:
                base_path = os.path.join(base_path, part)

            logger.info(f"Translated URL path '{self.path}' -> local path '{base_path}'")
            return base_path
        
        except Exception as e:
            logger.exception(f"Error while translating path: {path}")
            return os.getcwd()
        
    def copyfile(self, source, outputfile):
        try:
            shutil.copyfileobj(source, outputfile)
            logger.info("File content copied to output stream successfully")
        except Exception as e:
            logger.error(f"Failed to copy file content: {str(e)}")

    def guess_type(self, path):
        base, ext = posixpath.splitext(path)
        ext = ext.lower()
        mime_type = self.extensions_map.get(ext, self.extensions_map[''])

        logger.debug(f"Guessed MIME type for '{path}': {mime_type}")

        return mime_type
    
def test(server_class=http.server.HTTPServer, handler_class=SimpleHTTPRequestHandler, port=8000):

    try:
        host_ip = socket.gethostbyname(socket.gethostname())
        server_address = ('', port)

        httpd = server_class(server_address, handler_class)

        access_url = f"http://{host_ip}:{port}/"
        logger.info(f"Starting HTTP server at {access_url}")
        print(f"\n Server started at {access_url}")
        print("Press CTRL + C to stop the server.\n")

        httpd.serve_forever()
    
    except OSError as e:
        logger.error(f"Failed to start server on port {port} | Error: {e}")
        print(f"Connot start server on port {port}: {e}")
    
    except KeyboardInterrupt:
        logger.info("Server interrupted by user (CTRL + C)")
        print("\nServer stopped by user.")

    except Exception as e:
        logger.exception("Unexpected error while running the serever")
        print(f"Unexpexted error: {e}")
    
    finally:
        try:
            httpd.server_close()
            logger.info("Server closed cleanly.")
            print("Server closed cleanly")
        except:
            pass



if __name__ == '__main__':
    test()
