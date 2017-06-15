#!/usr/bin/env python3
##############################################################################

##############################################################################

import sys
import os
import datetime
import logging
import logging.handlers
import logging.config
import re
import sqlite3
import requests
import time
import twilio
from bs4 import BeautifulSoup
 
##############################################################################
# Global variables
##############################################################################

__version__ = "1.0.0"
__date__ = "Sat Jun 10 18:44:23 EDT 2017"


# Application Name
APP_NAME = "Page Shifts Monitor For LCPL"

# Application Version obtained from subversion revision.
APP_VERSION = __version__

# Application Date obtain from last subversion commit date.
APP_DATE = __date__

# Location of the source directory, based on this script file.
SRC_DIR = os.path.abspath(sys.path[0])

# Directory where various data resides.  e.g. sqlite database.
DATA_DIR = \
    os.path.abspath(os.path.join(SRC_DIR,
                                 ".." + os.sep + "data"))

# File path of the sqlite database.
DATABASE_FILENAME = \
    os.path.abspath(os.path.join(DATA_DIR,
                                 "lcpl_page_shifts.db"))

# Directory where log files will be written.
LOG_DIR = \
    os.path.abspath(os.path.join(SRC_DIR,
                                 ".." + os.sep + "logs"))

# Location of the config file for logging.
LOG_CONFIG_FILE = \
    os.path.abspath(os.path.join(SRC_DIR,
                                 ".." + os.sep +
                                 "conf" + os.sep +
                                 "logging.conf"))

# For logging.
logging.config.fileConfig(LOG_CONFIG_FILE)
log = logging.getLogger("main")


# These globals are extracted from environment variables.
# See the method initializeTwilio() below.
twilioAccountSid = None
twilioAuthToken = None
sourcePhoneNumber = None
destinationPhoneNumber = None

##############################################################################
# Classes
##############################################################################

class Shift:
    def __init__(self):
        self.date = None;
        self.location = None;
        self.startTime = None;
        self.endTime = None;
        self.description = None;
        self.status = None;

    def __str__(self):
        rv = "Shift(date=" + self.date + "," + \
                "location=" + self.location + "," + \
                "startTime=" + self.startTime + "," + \
                "endTime=" + self.endTime + "," + \
                "description=" + self.description + "," + \
                "status=" + self.status + ")"
        return rv

##############################################################################
# Methods
##############################################################################

def shutdown(rc):
    """
    Exits the script, but first flushes all logging handles, etc.
    """
    
    global conn
    conn.close()
    logging.shutdown()
    sys.exit(rc)

    
def initializeDatabase():
    """
    Initializes the database (creating tables as needed).
    Globals 'conn' and 'cursor' are set for future use.
    """
    
    global conn
    global cursor
    conn = sqlite3.connect(DATABASE_FILENAME)
    cursor = conn.cursor()
    cursor.execute("create table if not exists shifts " +
        "(crte_utc_dttm text, " +
        "shift_date text, " +
        "location text, " +
        "start_time text, " +
        "end_time text, " +
        "description text, " +
        "status text)")
    conn.commit()

    
def initializeTwilio():
    """
    Initializes Twilio by obtaining the account and auth token variables from 
    environment variables.  These must be set prior to running this script.
    """

    global twilioAccountSid
    global twilioAuthToken
    global sourcePhoneNumber
    global destinationPhoneNumber

    twilioAccountSid = os.environ.get("TWILIO_ACCOUNT_SID")
    twilioAuthToken = os.environ.get("TWILIO_AUTH_TOKEN")
    sourcePhoneNumber = os.environ.get("TWILIO_SRC_PHONE_NUMBER")
    destinationPhoneNumber = os.environ.get("TWILIO_DEST_PHONE_NUMBER")

    if twilioAccountSid is None:
        log.error("Environment variable was not set: TWILIO_ACCOUNT_SID")
        shutdown(1)

    if twilioAuthToken is None:
        log.error("Environment variable was not set: TWILIO_AUTH_TOKEN")
        shutdown(1)

    if sourcePhoneNumber is None:
        log.error("Environment variable was not set: TWILIO_SRC_PHONE_NUMBER")
        shutdown(1)
    else:
        log.info("Source phone number is: " + sourcePhoneNumber)

    if destinationPhoneNumber is None:
        log.error("Environment variable was not set: TWILIO_DEST_PHONE_NUMBER")
        shutdown(1)
    else:
        log.info("Destination phone number is: " + destinationPhoneNumber)

        
def getHtmlPages():
    """
    Returns a list of str.  Each str contains the contents of a HTML page.
    """
    
    htmls = []

    ######################
    # Temporary code for just reading straight from a file.
    if False:
        html = None
        filename = \
            os.path.abspath(os.path.join(DATA_DIR,"4090d4aaeaf2ba7f58-page8"))
        with open(filename, "r") as f:
            html = f.read()
        if html is None:
            log.error("Error: No html data.")
            shutdown(1)
        else:
            htmls.append(html)
            return htmls
    ######################
    
    urls = [
        "http://www.signupgenius.com/go/4090d4aaeaf2ba7f58-page5",
        "http://www.signupgenius.com/go/4090d4aaeaf2ba7f58-page6",
        "http://www.signupgenius.com/go/4090d4aaeaf2ba7f58-page7",
        "http://www.signupgenius.com/go/4090d4aaeaf2ba7f58-page8"]

    for url in urls:
        log.info("Fetching webpage from URL: " + url)
        r = requests.get(url)
        log.debug("HTTP status code: " + str(r.status_code))
        if 200 <= r.status_code < 300:
            html = r.text
            htmls.append(html)
        else:
            log.error("Unexpected HTTP status code: " + str(r.status_code))
            log.error("Response text is: " + r.text)
            shutdown(1)

    return htmls


def getShiftsFromHtml(html):
    """
    Reads the input html str, and extracts the shifts.

    Arguments:
    html - str containing HTML text to parse.

    Returns:
    list of Shift objects
    """
    
    shifts = []
    soup = BeautifulSoup(html, 'html5lib')
    mainTable = soup.find("table", {"class" : "SUGtableouter"})
    #log.debug("mainTable is: " + mainTable.prettify())
    mainTableBody = mainTable.find("tbody")

    lastDateText = None
    lastLocationText = None
    
    isFirstRow = True
    for tr in mainTableBody.findAll("tr", recursive=False):
        #log.debug("A <tr> of mainTableBody is: " + tr.prettify())
        log.debug("There are " + str(len(tr.findAll("td"))) + \
                  " <td> inside this <tr>")
        log.debug("There are " + str(len(tr.findAll("span"))) + \
                  " <span> inside this <tr>")
            
        if isFirstRow:
            log.debug("Skipping first row.")
            isFirstRow = False
            continue
        else:
            log.debug("Not first row.  Parsing...")
    
        spans = tr.find_all("span")
        log.debug("Found " + str(len(spans)) + " spans.")

        if (len(spans) != 3 and len(spans) != 4 and len(spans) != 5):
            log.warn("Unexpected number of spans: " + str(len(spans)))
            log.warn("Skipping this <tr>.")
            continue
        
        col = 0
        
        # Date.
        dateText = None
        if len(spans) == 5:
            dateText = spans[col].text.strip()
            col += 1
            lastDateText = dateText
        elif len(spans) == 3 or len(spans) == 4:
            if lastDateText is not None:
                dateText = lastDateText
            else:
                log.error("Unexpected number of spans when there was no previous date.")
                log.error("HTML text is: " + html)
                shutdown(1)
        if (len(dateText) < 8):
            log.error("Unexpected length of date text: " + dateText)
            log.error("HTML text is: " + html)
            shutdown(1)
        dateText = dateText[:8]
        if dateText[2] != "/" or \
                dateText[5] != "/" or \
                (not dateText[:2].isdigit()) or \
                (not dateText[3:5].isdigit()) or \
                (not dateText[6:].isdigit()):

            log.error("Date text is not MM/dd/yyyy.  Date text is: " + dateText)
            log.error("HTML text is: " + html)
            shutdown(1)

        # Location.
        locationText = None
        if len(spans) == 5 or len(spans) == 4:
            locationText = spans[col].text.replace("&nbsp;", " ").strip()
            col += 1
            lastLocationText = locationText
        elif len(spans) == 3:
            if lastLocationText is not None:
                locationText = lastLocationText
            else:
                log.error("Unexpected number of spans when there was no previous location.")
                log.error("HTML text is: " + html)
                shutdown(1)
        log.debug("locationText == " + locationText)
    
        # Start Time and End Time.
        timeText = spans[col].text.replace("&nbsp;", " ")
        col += 1
        timeText = timeText.strip()
        log.debug("timeText == " + timeText)
        timeTexts = timeText.split(" - ")
        startTimeText = timeTexts[0]
        endTimeText = timeTexts[1]
        log.debug("startTimeText == " + startTimeText)
        log.debug("endTimeText == " + endTimeText)
    
        # Description.
        descriptionText = spans[col].text.replace("&nbsp;", " ").strip()
        col += 1
        log.debug("descriptionText == " + descriptionText)
    
    
        # Status.
        statusText = spans[col].text.replace("&nbsp;", " ").strip()
        col += 1
        log.debug("statusText == " + statusText)
    
        shift = Shift()
        shift.date = dateText
        shift.location = locationText
        shift.startTime = startTimeText
        shift.endTime = endTimeText
        shift.description = descriptionText
        shift.status = statusText
    
        shifts.append(shift)
        log.debug("Created a Shift.")

    log.debug("Found " + str(len(shifts)) + " total shifts.")
    return shifts


def getNewShiftsAvailableForSignup(currShifts):
    """
    This method iterates through the current shifts and 
    returns the new shifts that are available for signup.

    Arguments: 
    currShifts - list of Shift objects containing the current shifts.

    Returns:
    list of Shift objects that are the new shifts available for signup.
    """

    global conn
    global cursor
    newShiftsAvailableForSignup = []
    
    for shift in currShifts:
        
        values = (shift.date, 
                shift.location,
                shift.startTime,
                shift.endTime,
                shift.description)
            
        cursor.execute("select * from shifts where " + \
                "shift_date = ? " + \
                "and location = ? " + \
                "and start_time = ? " + \
                "and end_time = ? " + \
                "and description = ? " + \
                "order by crte_utc_dttm desc limit 1",
                values)

        tups = cursor.fetchall()
        
        if len(tups) == 0:
            # Initial status.
            log.debug("shift.status is: " + shift.status)
            if re.search("sign up", shift.status, re.IGNORECASE):
                newShiftsAvailableForSignup.append(shift)

            crteUtcDttm = datetime.datetime.utcnow().isoformat()
            values = (crteUtcDttm,
                    shift.date,
                    shift.location,
                    shift.startTime,
                    shift.endTime,
                    shift.description,
                    shift.status)
            cursor.execute("insert into shifts values (?, ?, ?, ?, ?, ?, ?)",
                           values)
            conn.commit()
    
        elif len(tups) == 1:
            # Status was stored previously for this shift.
            # Compare status.
            tup = tups[0]
            statusColumn = 6
            oldStatus = tup[statusColumn]
            if shift.status != oldStatus:
                log.info("Status changed from " + oldStatus + \
                         " to " + shift.status + " for: " + \
                         str(shift))
                if re.search("sign up", shift.status, re.IGNORECASE) or \
                    re.search("signup", shift.status, re.IGNORECASE):
                    
                    newShiftsAvailableForSignup.append(shift)

                crteUtcDttm = datetime.datetime.utcnow().isoformat()
                values = (crteUtcDttm,
                        shift.date,
                        shift.location,
                        shift.startTime,
                        shift.endTime,
                        shift.description,
                        shift.status)
                cursor.execute("insert into shifts values (?, ?, ?, ?, ?, ?, ?)",
                               values)
                conn.commit()
        else:
            log.error("Unexpected number of rows for shift.  " + \
                      "numRows == " + numRows + ", shift == " + str(shift))
            shutdown(1)

    return newShiftsAvailableForSignup


def sendNotificationMessage(newShiftsAvailableForSignup):
    """
    Sends out a text message notifying the user that there are 
    new shifts available for signup.

    # TODO_rluu: Look into SES in AWS.  I am currently in a sandbox with that
    # feature, with 200 emails sent allowed per 24-hour.  I may need to verify
    # email addresses that I want to send to.
    
    # To send a message to a Verizon Wireless phone from a personal computer,
    # enter the person's mobile number followed by @vtext.com in the “to” field
    # of your e-mail message – for example, 5551234567@vtext.com. Type an e-mail
    # message as you would normally and send it. For more information, please
    # visit www.vtext.com. Jul 25, 2007
    """

    endl = "\n"
    msg = endl + "LCPL Page Shift Update: " + endl
    if len(newShiftsAvailableForSignup) == 1:
        msg += "There is " + str(len(newShiftsAvailableForSignup)) + \
            " new shift available for signup at: " + endl
    else:
        msg += "There are " + str(len(newShiftsAvailableForSignup)) + \
            " new shifts available for signup at: " + endl
    
    # Extract unique locations.
    locations = []
    for shift in newShiftsAvailableForSignup:
        if shift.location not in locations:
            locations.append(shift.location)
    locations.sort()

    # Append locations to the msg string.
    isFirstLocation = True
    for location in locations:
        if isFirstLocation:
            msg += location
            isFirstLocation = False
        else:
            msg += ", " + location
    msg += "."
    
    # Send text message via Twilio.
    global twilioAccountSid
    global twilioAuthToken
    global sourcePhoneNumber
    global destinationPhoneNumber
    
    client = twilio.rest.Client(twilioAccountSid, twilioAuthToken)

    log.info("Sending text message from phone number " +
                sourcePhoneNumber + " to phone number " +
                destinationPhoneNumber + " with message body: " + msg)
    
    client.messages.create(from_=sourcePhoneNumber,
                           to=destinationPhoneNumber,
                           body=msg)

    log.info("Sending text message done.")

##############################################################################
# Main
##############################################################################

if __name__ == "__main__":
    log.info("##########################################################")
    log.info("# Starting " + APP_NAME + \
             " (" + sys.argv[0] + "), version " + APP_VERSION)
    log.info("##########################################################")

    initializeDatabase()
    initializeTwilio()

    while True:
        try:
            log.info("Getting HTML pages ...")
            htmlPages = getHtmlPages()
            log.info("Getting HTML pages done.")
            
            newShiftsAvailableForSignup = []
            
            for htmlPage in htmlPages:
                shifts = getShiftsFromHtml(htmlPage)
            
                newShiftsAvailableForSignup.extend(\
                    getNewShiftsAvailableForSignup(shifts))
                
            log.info("There are " + str(len(newShiftsAvailableForSignup)) + \
                     " new shifts available for signup since we last checked.")
            
            if len(newShiftsAvailableForSignup) > 0:
                sendNotificationMessage(newShiftsAvailableForSignup)
                
            numSeconds = 60
            log.debug("Sleeping for " + str(numSeconds) + " seconds ...")
            time.sleep(numSeconds)
        except KeyboardInterrupt:
            log.info("Caught KeyboardInterrupt.  Shutting down cleanly ...")
            shutdown(0)
        

##############################################################################
