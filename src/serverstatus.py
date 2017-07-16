#!/usr/bin/env python3

import optparse
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

def toHtmlNbspAndHtmlHyphen(strWithSpacesOrDashes):
    """Returns the string with spaces replaced with HTML non-breaking spaces,
    and the hyphens replaced with HTML non-breaking hyphens.
    """
    rv = strWithSpacesOrDashes
    rv = rv.replace(" ", "&nbsp;")
    rv = rv.replace("-", "&#8209;")
    return rv

def getHtmlHead():
    htmlStr = "<head>"
    htmlStr += "  <style>"

    htmlStr += "    body {"
    htmlStr += "      font-family: Courier New;"
    htmlStr += "      font-size: small;"
    htmlStr += "    }"

    htmlStr += "    h1, h2, h3, h4, h5, h6 {"
    htmlStr += "      font-family: Arial;"
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

    htmlStr = "<head>"
    htmlStr += "  <style>"
    htmlStr += "    body {"
    htmlStr += "      font-family: Arial;"
    htmlStr += "      font-size: large;"
    htmlStr += "    }"
    htmlStr += "  </style>"
    htmlStr += "</head>"

    htmlStr += "<body>"

    htmlStr += "<hr />"
    htmlStr += "<h3>Welcome to my server status page!</h3>"
    htmlStr += "<hr />"

    htmlStr += endl
    htmlStr += endl

    url = url_for("lcplpagesubs_status") 
    htmlStr += "<a href=" + url + ">" + url + "</a>" + endl
    htmlStr += endl

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
                        startupDttm = startupDttm.replace(",", ".")
                elif line.find("Shutdown") != -1 and line.find("rc=") != -1:
                    firstDashPos = line.find(" - ")
                    if firstDashPos != -1:
                        shutdownDttm = line[:firstDashPos].strip()
                        shutdownDttm = shutdownDttm.replace(",", ".")

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
    for line in sh.grep(sh.ps('-ef', _piped=True), "--color=none", "python3"):
        if line.find("grep --color=none") == -1:
            username = ""

            splitLine = line.split(" ")
            if len(splitLine) > 0:
                username = splitLine[0]

            usernameReplacement = ""
            for i in range(len(username)):
                usernameReplacement += "&nbsp;"

            escapedLine = html.escape(line[len(username):])
            psInfoLine = usernameReplacement + \
                toHtmlNbspAndHtmlHyphen(escapedLine)
            psInfoLines.append(psInfoLine)

    tailLines = []
    if os.path.isfile(lcplpagesubsLogFilename):
        numLines = 20
        lines = tail(lcplpagesubsLogFilename, numLines)
        for i in range(len(lines)):
            line = lines[i]
            escapedLine = html.escape(line)
            tailLine = toHtmlNbspAndHtmlHyphen(escapedLine)
            tailLines.append(tailLine)

    fixedWidthSize = 22
    desiredFormat = "{:<" + str(fixedWidthSize) + "s}"
    line1 = desiredFormat.format("Current server time: ") + str(nowLocal)
    line1 = toHtmlNbspAndHtmlHyphen(line1)

    line2 = desiredFormat.format("Last startup was: ") + startupStatusMessage
    line2 = toHtmlNbspAndHtmlHyphen(line2)

    line3 = desiredFormat.format("Last shutdown was: ") + shutdownStatusMessage
    line3 = toHtmlNbspAndHtmlHyphen(line3)

    htmlStr = "<html>"
    htmlStr += getHtmlHead()
    htmlStr += "<body>"
    htmlStr += "<hr />"
    htmlStr += "<h3>Application LCPL Page Subs</h3>"
    htmlStr += "<hr />"
    htmlStr += endl
    htmlStr += line1 + endl
    htmlStr += endl
    htmlStr += line2 + endl
    htmlStr += endl
    htmlStr += line3 + endl
    htmlStr += endl
    htmlStr += "<hr />"
    htmlStr += endl
    htmlStr += "Running python3 processes are: " + endl
    for line in psInfoLines:
        htmlStr += line + endl
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



# Below method was adopted from:
#   http://flask.pocoo.org/snippets/133/
#
def flaskrun(app, default_host="127.0.0.1", 
                  default_port="5000"):
    """
    Takes a flask.Flask instance and runs it. Parses 
    command-line flags to configure the app.
    """

    # Set up the command-line options
    parser = optparse.OptionParser()
    parser.add_option("-H", "--host",
                      help="Hostname of the Flask app " + \
                           "[default %s]" % default_host,
                      default=default_host)
    parser.add_option("-P", "--port",
                      help="Port for the Flask app " + \
                           "[default %s]" % default_port,
                      default=default_port)

    # Two options useful for debugging purposes, but 
    # a bit dangerous so not exposed in the help message.
    parser.add_option("-d", "--debug",
                      action="store_true", dest="debug",
                      help=optparse.SUPPRESS_HELP)
    parser.add_option("-p", "--profile",
                      action="store_true", dest="profile",
                      help=optparse.SUPPRESS_HELP)

    options, _ = parser.parse_args()

    # If the user selects the profiling option, then we need
    # to do a little extra setup
    if options.profile:
        from werkzeug.contrib.profiler import ProfilerMiddleware

        app.config['PROFILE'] = True
        app.wsgi_app = ProfilerMiddleware(app.wsgi_app,
                       restrictions=[30])
        options.debug = True

    app.run(
        debug=options.debug,
        host=options.host,
        port=int(options.port)
    )

    
if __name__ == "__main__":
    flaskrun(app)
