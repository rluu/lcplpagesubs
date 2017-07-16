#!/usr/bin/env python3

import html
import datetime
import sh
import subprocess
import sys
import os
import os.path
from flask import Flask, redirect, url_for

# Location of the source directory, based on this script file.
SRC_DIR = os.path.abspath(sys.path[0])

LOG_DIR = \
    os.path.abspath(os.path.join(SRC_DIR,
                                 ".." + os.sep + "logs"))

global app
app = Flask(__name__)

def tail(filename, n):
    cmd = ["tail", "-n", str(n), filename]
    lines = subprocess.check_output(cmd).decode("UTF-8").split("\n")
    return lines

def getHtmlHead():
    htmlStr = "<head>"
    htmlStr += "  <style>"
    htmlStr += "    html {"
    htmlStr += "      font-family: Courier New;"
    htmlStr += "      font-size: small;"
    htmlStr += "    }"
    htmlStr += "  </style>"
    htmlStr += "</head>"
    return htmlStr

@app.route("/")
def index():
    return redirect(url_for("serverstatus"))

@app.route("/serverstatus")
def serverstatus():
    endl = "<br />"
    htmlStr = "<html>"
    htmlStr += getHtmlHead()
    htmlStr += "<body>"
    htmlStr += "<p>Welcome to my server status page!</p>"
    htmlStr += endl
    htmlStr += endl

    url = url_for("lcplpagesubs_status") 
    htmlStr += "<a href=" + url + ">" + url + "</a>" + endl

    htmlStr += "</body>"
    htmlStr += "</html>"

    return htmlStr


@app.route("/serverstatus/lcplpagesubs/status")
def lcplpagesubs_status():
    endl = "<br />"
    indent = "&nbsp;&nbsp;&nbsp;&nbsp;"

    nowLocal = datetime.datetime.now()

    lcplpagesubsLogsPath = LOG_DIR
    lcplpagesubsLogFilename = lcplpagesubsLogsPath + os.sep + "lcplpagesubs.log"

    startupDttm = None
    shutdownDttm = None

    filenames = []
    if os.path.isfile(lcplpagesubsLogFilename):
        filenames.append(lcplpagesubsLogFilename)
    for i in range(100):
        filename = lcplpagesubsLogFilename + "." + str(i)
        if os.path.isfile(filename):
            filenames.append(filename)

    for filename in filenames:
        if startupDttm is not None and shutdownDttm is not None:
            break
        with open(filename) as f:
            lines = f.readlines()
            lines.reverse()
            for line in lines:
                if startupDttm is not None and shutdownDttm is not None:
                    break
                if line.find("Starting Page Shifts Monitor For LCPL") != -1:
                    firstDashPos = line.find(" - ")
                    if firstDashPos != -1:
                        startupDttm = line[:firstDashPos].strip()
                elif line.find("Shutdown") != -1 and line.find("rc=") != -1:
                    firstDashPos = line.find(" - ")
                    if firstDashPos != -1:
                        shutdownDttm = line[:firstDashPos].strip()

    startupStatusMessage = ""
    if startupDttm is None:
        startupStatusMessage += "Unknown"
    else:
        startupStatusMessage += html.escape(startupDttm)

    shutdownStatusMessage = ""
    if shutdownDttm is None:
        shutdownStatusMessage += "Unknown"
    else:
        shutdownStatusMessage += html.escape(shutdownDttm)

    psInfoLines = []
    for line in sh.grep(sh.ps('aux', _piped=True), 'python3'):
        if line.find("grep python3") == -1:
            psInfoLines.append(html.escape(line.strip()))

    tailLines = []
    if os.path.isfile(lcplpagesubsLogFilename):
        numLines = 20
        lines = tail(lcplpagesubsLogFilename, numLines)
        for i in range(len(lines)):
            line = lines[i]
            escapedLine = html.escape(line)
            tailLines.append(escapedLine)

    htmlStr = "<html>"
    htmlStr += getHtmlHead()
    htmlStr += "<body>"
    htmlStr += "<hr />"
    htmlStr += "<h3>Application LCPL Page Subs</h3>"
    htmlStr += "<hr />"
    htmlStr += "<table cellpadding='5'>"
    htmlStr += "  <tr>"
    htmlStr += "    <td>Current status as of: </td>"
    htmlStr += "    <td>" + str(nowLocal) + "</td>"
    htmlStr += "  </tr>"
    htmlStr += "  <tr>"
    htmlStr += "    <td>Last startup was: </td>"
    htmlStr += "    <td>" + startupStatusMessage + "</td>"
    htmlStr += "  </tr>"
    htmlStr += "  <tr>"
    htmlStr += "    <td>Last shutdown was: </td>"
    htmlStr += "    <td>" + shutdownStatusMessage + "</td>"
    htmlStr += "  </tr>"
    htmlStr += "</table>"
    htmlStr += endl
    htmlStr += "<hr />"
    htmlStr += endl
    htmlStr += "Running python3 processes are: " + endl
    for line in psInfoLines:
        htmlStr += indent + line + endl
    htmlStr += endl
    htmlStr += "<hr />"
    htmlStr += endl
    htmlStr += "The last few lines in the lcplpagesubs logs are: " + endl
    htmlStr += endl
    for line in tailLines:
        htmlStr += line + endl
    htmlStr += endl
    htmlStr += "<hr />"
    htmlStr += "</body>"
    htmlStr += "</html>"

    return htmlStr

#@app.route('/serverstatus/lcplpagesubs/shutdown')
#def serverstatus_shutdown():
#    func = request.environ.get('werkzeug.server.shutdown')
#    if func is None:
#        raise RuntimeError('Not running with the Werkzeug Server')
#    func()
#    return 'Server shutting down...'


if __name__ == "__main__":
    app.run(port=5000, debug=False)

