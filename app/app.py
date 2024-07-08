import os
import time
import threading
import requests
import logging

from flask import Flask, send_from_directory, jsonify, request, render_template
from flask_cors import CORS
from selenium import webdriver
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.chrome.options import Options as ChromeOptions
from screeninfo import get_monitors
import subprocess
import platform

logging.basicConfig(level=logging.INFO)

DIRECTORY = os.path.dirname(os.path.realpath(__file__))
ASSETS_FOLDER = os.path.join(DIRECTORY, "assets")
PORT = 80


def get_local_ip():
    command = "hostname -I | awk '{print $1}'"
    output = subprocess.check_output(command, shell=True).decode("utf-8").strip()
    return output


FILETYPE_WHITELIST = [
    "pdf",
    "mp4",
    "webm",
    "ogg",
    "jpg",
    "jpeg",
    "png",
    "gif",
    "png",
]


class ChromeWindow:

    def __init__(self, window_position, display_id):
        self.window_position = window_position
        self.displayId = display_id
        self.driver = None

    def launch(self, url=None):
        if not url:
            url = f"http://localhost:{PORT}/default.html?displayId={self.displayId}"
            logging.info(f"Launching kiosk on display {self.displayId}: {url}")
        options = ChromeOptions()
        options.add_argument(f"--kiosk")
        options.add_argument(
            f"--window-position={self.window_position[0]},{self.window_position[1]}"
        )
        options.add_argument("--noerrdialogs")  # Suppress error dialogs
        options.add_argument("--disable-infobars")  # Disable infobars
        options.add_experimental_option("useAutomationExtension", False)
        options.add_experimental_option("excludeSwitches", ["enable-automation"])

        if platform.system() == "Linux" and platform.machine() == "aarch64":
            service = ChromeService(executable_path="/usr/bin/chromedriver")
            options.binary_location = "/usr/bin/chromium"
        else:
            service = ChromeService()

        self.driver = webdriver.Chrome(service=service, options=options)
        self.driver.get(url)
        return self.driver

    def refresh(self, url):
        self.driver.get(url)


class WebServer:
    def __init__(self, directory, assets_folder, port, filetype_whitelist):
        self.directory = directory
        self.assets_folder = assets_folder
        self.port = port
        self.filetype_whitelist = filetype_whitelist
        self.app = Flask(__name__, static_folder=directory)
        CORS(self.app)
        self.connected_displays = []
        self.chrome_windows = []
        for i, monitor in enumerate(get_monitors()):
            os.makedirs(os.path.join(self.assets_folder, f"Display {i}"), exist_ok=True)
            self.connected_displays.append(i)

            DISPLAY_COORDINATES = (monitor.x, monitor.y)
            DISPLAY_RESOLUTION = (monitor.width, monitor.height)
            logging.info(
                f"Launching kiosk on display {i}: {DISPLAY_COORDINATES} {DISPLAY_RESOLUTION}"
            )
            self.chrome_windows.append(ChromeWindow(DISPLAY_COORDINATES, i))

        self._setup_routes()

    def _setup_routes(self):

        @self.app.route("/")
        def home():
            return render_template(
                "user_upload.html", my_ip=get_local_ip(), port=self.port
            )

        @self.app.route("/favicon.ico")
        def favicon():
            return send_from_directory(self.directory, "favicon.ico")

        @self.app.route("/<path:filename>")
        def serve_html(filename):
            if not filename.endswith(".html"):
                return "Invalid file type", 400
            return render_template(filename, my_ip=get_local_ip(), port=self.port)

        @self.app.route("/assets/<screen_id>/<path:filename>")
        def serve_assets(screen_id, filename):
            folder_path = f"{self.assets_folder}/{screen_id}"
            return send_from_directory(folder_path, filename)

        @self.app.route("/api/displaynames", methods=["GET"])
        def get_display_names():

            display_names = []
            for i in self.connected_displays:
                display_names.append({"id": i, "name": f"Display {i}"})
            return jsonify(display_names)

        @self.app.route("/api/upload", methods=["POST"])
        def upload_file():
            # Check if the post request has the file part
            if "file" not in request.files:
                return jsonify({"error": "No file part"}), 400

            file = request.files["file"]
            display_name = request.form.get("displayName")
            display_id = request.form.get("displayId")
            if file.filename == "":
                return jsonify({"error": "No selected file"}), 400

            if file.filename.split(".")[-1] not in self.filetype_whitelist:
                return jsonify({"error": "Invalid file type"}), 400

            if file:
                # # Save the file
                file_path = os.path.join(
                    self.assets_folder, display_name, file.filename
                )
                file.save(file_path)

                url = f"http://localhost:{self.port}/kiosk.html?file=/assets/{display_name}/{file.filename}"
                # save as last url to text file
                with open(
                    f"{self.assets_folder}/{display_name}/last_url.txt", "w"
                ) as f:
                    f.write(url)
                self.chrome_windows[int(display_id)].refresh(url)

                return (
                    jsonify(
                        {
                            "message": "File uploaded successfully",
                            "displayName": display_name,
                        }
                    ),
                    200,
                )

            return jsonify({"error": "Failed to upload file"}), 500

    def start(self):
        threading.Thread(
            target=self.app.run, kwargs={"host": "0.0.0.0", "port": self.port}
        ).start()

    def wait_for_server(self):
        url = f"http://localhost:{self.port}/default.html"
        while True:
            try:
                response = requests.get(url)
                if response.status_code == 200:
                    return True
            except requests.ConnectionError:
                time.sleep(1)

    def launch_kiosks(self):
        for window in self.chrome_windows:
            # try to load last url
            try:
                logging.info(f"Found last url for display {window.displayId}")
                with open(
                    f"{self.assets_folder}/Display {window.displayId}/last_url.txt", "r"
                ) as f:
                    url = f.read()
                    window.launch(url)
            except FileNotFoundError:
                window.launch()


def main():
    webserver = WebServer(DIRECTORY, ASSETS_FOLDER, PORT, FILETYPE_WHITELIST)
    webserver.start()
    webserver.wait_for_server()
    logging.info("Kiosk server started")
    webserver.launch_kiosks()

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        logging.info("Shutting down kiosk server")


if __name__ == "__main__":
    main()
