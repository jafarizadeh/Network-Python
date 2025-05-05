# 🛰️ Python File Transfer HTTP Server

A simple yet powerful Python-based HTTP server that supports file uploads and downloads via a web interface — ideal for local network file transfers without third-party tools.

## 📦 Features

- ✅ Upload files through a browser
- ✅ Download any file or directory listed
- ✅ Clean directory listing in HTML format
- ✅ MIME type detection for accurate content serving
- ✅ Logging of all HTTP requests and file operations
- ✅ Easy to run — no dependencies beyond the Python Standard Library

---

## 🚀 Getting Started

### 🔧 Prerequisites

- Python 3.6 or later
- No additional libraries required

---

### 🖥️ Run the Server

1. Clone the repository or download `server.py`
2. Open a terminal and navigate to the script directory
3. Run the script:

```bash
python server.py
```

4. After starting, you’ll see output like:

```
🚀 Server started at http://192.168.1.100:8000
Press CTRL + C to stop the server.
```

5. Open that URL in any browser on the same network to access the file server.

---

### 🌐 Upload Files

- Use the upload form at the top of the directory listing to upload files.
- Files are saved in the current working directory of the server.

---

## 📁 Folder Structure

```bash
.
├── server.py            # Main Python HTTP server
├── server.log           # Log file (auto-generated)
└── uploads/             # (Optional) Directory for received files
```

You can customize the target folder by modifying the `translate_path()` method.

---

## 📓 Logging

- All server activity is logged in `server.log`
- Includes IP addresses, request types, file uploads, and errors

---

## 🔐 Security Notice

This tool is designed for **local network use only**.
It does not include authentication or TLS encryption.
Do **not** expose it directly to the internet unless behind a secured reverse proxy.

---

## 📃 License

This project is open-source and licensed under the MIT License.

---

## 🤝 Contributions

Contributions are welcome! Feel free to submit issues or pull requests to improve functionality or compatibility.