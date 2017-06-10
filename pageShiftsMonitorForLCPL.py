#!/usr/bin/env python3
##############################################################################

##############################################################################

import os
import logging
import logging.handlers
import logging.config
import re
import sqlite3
import requests
import time
from bs4 import BeautifulSoup
from twilio.rest import TwilioRestClient
 
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
    conn = sqlite3.connect("lcpl_page_shifts.db")
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

    if destinationPhoneNumber is None:
        log.error("Environment variable was not set: TWILIO_DEST_PHONE_NUMBER")
        shutdown(1)

        
def getHtmlPages():
    """
    Returns a list of str.  Each str contains the contents of a HTML page.
    """
    
    htmls = []

    # Temporary code for just reading straight from a file.
    html = None
    with open("4090d4aaeaf2ba7f58-page8", "r") as f:
        html = f.readlines()
    if html is None:
        log.error("Error: No html data.")
        shutdown(1)
    else:
        htmls.add(html)
        return htmls
    
    urls = [
        "http://www.signupgenius.com/go/4090d4aaeaf2ba7f58-page5",
        "http://www.signupgenius.com/go/4090d4aaeaf2ba7f58-page6",
        "http://www.signupgenius.com/go/4090d4aaeaf2ba7f58-page7",
        "http://www.signupgenius.com/go/4090d4aaeaf2ba7f58-page8"]

    for url in urls:
        log.info("Fetching webpage from URL: " + url)
        r = requests.get(url)
        log.debug("HTTP status code: " + r.status_code)
        if 200 <= r.status_code < 300:
            html = r.text
            htmls.append(html)
        else
            log.error("Unexpected HTTP status code: " + r.status_code)
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
    mainTable = soup.body.table
    
    isFirstRow = True
    for tr in mainTable.children:
        log.debug("A <tr> of mainTable is: " + tr)
        if isFirstRow:
            isFirstRow = False
            continue
    
        spans = tr.find_all('span')
    
        if (len(spans) != 5):
            log.error("Unexpected number of spans: " + len(spans))
            shutdown(1)
    
        col = 0
    
        # Date.
        dateText = spans[col].contents.strip()
        if (len(dateText) < 8):
            log.error("Unexpected length of date text: " + dateText)
            shutdown(1)
        dateText = dateText[:8]
        if dateText[2] != "/" or \
                dateText[5] != "/" or \
                (not dateText[:2].isdigit()) or \
                (not dateText[3:5].isdigit()) or \
                (not dateText[6:].isdigit()):

            log.error("Date text is not MM/dd/yyyy.  Date text is: " + dateText)
            shutdown(1)
    
        # Location.
        col += 1
        locationText = spans[col].contents.replace("&nbsp;", " ")
        locationText = locationText.strip()
    
        # Start Time and End Time.
        col += 1
        timeText = spans[col].contents.replace("&nbsp;", " ")
        timeText = timeText.strip()
        timeTexts = timeText.split(" - ")
        startTimeText = timeTexts[0]
        endTimeText = timeTexts[1]
    
        # Description.
        col += 1
        descriptionText = spans[col].contents.replace("&nbsp;", " ")
        descriptionText = descriptionText.strip()
    
    
        # Status.
        col += 1
        statusText = spans[col].contents.replace("&nbsp;", " ")
        statusText = statusText.strip()
    
        shift = Shift()
        shift.date = dateText
        shift.location = locationText
        shift.startTime = startTimeText
        shift.endTime = endTimeText
        shift.description = descriptionText
        shift.status = statusText
    
        shifts.append(shift)
        
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
        cursor.execute("select * from shifts where " + \
                "shift_date = ? " + \
                "and location = ? " + \
                "and start_time = ? " + \
                "and end_time = ? " + \
                "and description = ? " + \
                "order by crte_utc_dttm desc limit 1",
                shift.date, 
                shift.location,
                shift.startTime,
                shift.endTime,
                shift.description)
    
        numRows = c.getCount();
        if numRows == 0:
            # Never seen this value before.
            log.debug("shift.status is: " + shift.status)
            if re.search("sign up", shift.status, re.IGNORECASE):
                newShiftsAvailableForSignup.append(shift)

            crteUtcDttm = datetime.datetime.utcnow().isoformat()
            values = (crteUtcDttm,
                    self.date,
                    self.location,
                    self.startTime,
                    self.endTime,
                    self.description,
                    self.status)
            cursor.execute("insert into shifts values (?, ?, ?, ?, ?, ?, ?)",
                           values)
            conn.commit()
    
        elif numRows == 1:
            tup = c.fetchone()
            # Compare status.
            statusColumn = 6
            oldStatus = tup[statusColumn]
            if shift.status != oldStatus:
                log.debug("Status changed from " + oldStatus +
                          " to " + shift.status)
                if re.search("sign up", shift.status, re.IGNORECASE):
                    newShiftsAvailableForSignup.append(shift)

                crteUtcDttm = datetime.datetime.utcnow().isoformat()
                values = (crteUtcDttm,
                        self.date,
                        self.location,
                        self.startTime,
                        self.endTime,
                        self.description,
                        self.status)
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
    msg = "LCPL Page Shift Update: " + endl + \
        "There are " + str(len(newShiftsAvailableForSignup)) + \
        " new shifts available for signup at these locations: " + endl

    # Extract unique locations.
    locations = []
    for shift in newShiftsAvailableForSignup:
        if shift.location not in locations:
            locations.append(shift.location)

    # Append locations to the msg string.
    isFirstLocation = True
    for location in locations:
        if isFirstLocation:
            msg += location
            isFirstLocation = False
        else:
            msg += ", " + location
            
    # Send text message via Twilio.
    global twilioAccountSid
    global twilioAuthToken
    global sourcePhoneNumber
    global destinationPhoneNumber
    
    client = TwilioRestClient(twilioAccountSid, twilioAuthToken)

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
                
            if len(newShiftsAvailableForSignup) > 0:
                sendNotificationMessage(newShiftsAvailableForSignup)
    
            numSeconds = 60
            time.sleep(numSeconds)
        except KeyboardInterrupt:
            log.info("Caught KeyboardInterrupt.  Shutting down cleanly ...")
            shutdown(0)
        

##############################################################################
