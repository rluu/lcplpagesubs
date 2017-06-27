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
import boto3
from twilio.rest import Client
from bs4 import BeautifulSoup
 
##############################################################################
# Global variables
##############################################################################

__version__ = "1.0.0"
__date__ = "Wed Jun 21 20:13:54 EDT 2017"


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
htmlLog = logging.getLogger("html")


# These globals are extracted from environment variables.
# See the method initializeTwilio() below.
twilioAccountSid = None
twilioAuthToken = None
sourcePhoneNumber = None
destinationPhoneNumber = None

# These globals are for sending out admin emails.
# See the method initializeAdminEmailAddresses() below.
adminFromEmailAddress = None
adminToEmailAddress = None
adminErrorEmailSendingEnabled = True

# This global is for sending out alert email addresses.
# See the method initializeAlertEmailAddresses() below.
alertToEmailAddresses = None

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

    global adminErrorEmailSendingEnabled
    global conn
    conn.close()

    if rc != 0 and adminErrorEmailSendingEnabled == True:
        global adminFromEmailAddress
        global adminToEmailAddress
        fromEmailAddress = adminFromEmailAddress
        toEmailAddress = adminToEmailAddress
        emailSubject = "Application '" + APP_NAME + "' shutdown notification"
        endl = "<br />"
        emailBodyHtml = "Hi," + endl + endl + \
            "This is a notification to the site Admin that application '" + \
            APP_NAME + "' has quit unexpectedly with non-zero return code: " + \
            str(rc) + ".  " + \
            "Please investigate at your earliest convenience.  Thank you." + \
            endl + endl
        emailBodyHtml += "-" + APP_NAME

        log.info("Sending notice email to administrator (" + \
                 toEmailAddress + \
                 ") regarding error exit (rc == " + str(rc) + ").")
        
        client = boto3.client('ses')
        response = client.send_email(
            Destination={
                'ToAddresses': [toEmailAddress],
                'CcAddresses': [],
                'BccAddresses': []
                },
            Message={
                'Subject': {
                    'Data': emailSubject,
                    'Charset': 'UTF-8'
                },
                'Body': {
                    'Html': {
                        'Data': emailBodyHtml,
                        'Charset': 'UTF-8'
                        }
                    }
                },
            Source=fromEmailAddress,
            )
        
        log.info("Sending email done.")
        log.info("Response from AWS is: " + str(response))
        log.info("Now exiting ...")
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

def initializeAdminEmailAddresses():
    """
    Initializes the capability of sending admin emails by obtaining the 
    TO and FROM email addresses from environment variables.  
    These must be set prior to running this script.
    """

    global adminFromEmailAddress
    global adminToEmailAddress

    # This is a single email address.
    adminFromEmailAddress = os.environ.get("LCPL_PAGE_SUBS_ADMIN_EMAIL_ADDRESS")
    adminToEmailAddress = os.environ.get("LCPL_PAGE_SUBS_ADMIN_EMAIL_ADDRESS")

    if adminFromEmailAddress is None:
        log.error("Environment variable was not set: LCPL_PAGE_SUBS_ADMIN_EMAIL_ADDRESS")
        shutdown(1)
    else:
        log.info("adminFromEmailAddress is: " + adminFromEmailAddress)
        

    if adminToEmailAddress is None:
        log.error("Environment variable was not set: LCPL_PAGE_SUBS_ADMIN_EMAIL_ADDRESS")
        shutdown(1)
    else:
        log.info("adminToEmailAddress is: " + adminToEmailAddress)

        
def initializeAlertEmailAddresses():
    """
    Initializes the capability of sending alert emails by obtaining the 
    TO and FROM email addresses from environment variables.  
    These must be set prior to running this script.
    """

    global alertToEmailAddresses

    # This is a comma-separated-value string of email addresses.
    alertToEmailAddressesStr = os.environ.get("LCPL_PAGE_SUBS_ALERT_EMAIL_ADDRESSES")

    if alertToEmailAddressesStr is None:
        log.error("Environment variable was not set: LCPL_PAGE_SUBS_ALERT_EMAIL_ADDRESSES")
        shutdown(1)
    else:
        alertToEmailAddresses = alertToEmailAddressesStr.split(",")
        log.info("alertToEmailAddresses is: " + str(alertToEmailAddresses))

        
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
        #"http://www.signupgenius.com/go/4090d4aaeaf2ba7f58-page5",
        "http://www.signupgenius.com/go/4090d4aaeaf2ba7f58-page6",
        "http://www.signupgenius.com/go/4090d4aaeaf2ba7f58-page7",
        "http://www.signupgenius.com/go/4090d4aaeaf2ba7f58-page8",
        "http://www.signupgenius.com/go/4090d4aaeaf2ba7f58-page11",
        "http://www.signupgenius.com/go/4090d4aaeaf2ba7f58-page12",
        ]

    for url in urls:
        log.info("Fetching webpage from URL: " + url)
        r = requests.get(url)
        log.debug("HTTP status code: " + str(r.status_code))
        numSeconds = 2
        time.sleep(numSeconds)
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
    if mainTable == None:
        log.warn("Could not find a HTML table with class SUGtableouter, " + \
                  "which is our main table which contains all the shifts." + \
                  "  Please see the HTML log for the HTML encountered.")
        htmlLog.warn("HTML text is: " + html)
        log.warn("Returning an empty list of shifts for this HTML page.")
        return shifts

    #htmlLog.debug("mainTable is: " + mainTable.prettify())
    mainTableBody = mainTable.find("tbody")

    lastDateText = None
    lastLocationText = None
    
    isFirstRow = True
    for tr in mainTableBody.findAll("tr", recursive=False):
        #htmlLog.debug("A <tr> of mainTableBody is: " + tr.prettify())
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

        col = 0
        
        # Date.
        dateText = None
        spanText = spans[col].text.upper().strip()
        col += 1
        if isSpanTextADateField(spanText):
            dateText = spanText[:10]
            lastDateText = dateText
        elif isSpanTextALocationField(spanText) or isSpanTextATimeField(spanText):
            if lastDateText is not None:
                dateText = lastDateText
                col -= 1
            else:
                log.error("Unexpected number of spans when there was no previous date.  Please see the HTML log for the HTML encountered.")
                htmlLog.error("<tr> contents is: " + tr.prettify())
                htmlLog.error("HTML text is: " + html)
                shutdown(1)
        else:
            log.error("Unexpected span text: " + spanText)
            htmlLog.error("<tr> contents is: " + tr.prettify())
            htmlLog.error("HTML text is: " + html)
            shutdown(1)
        log.debug("dateText == " + dateText)


        # Location.
        locationText = None
        spanText = spans[col].text.upper().strip()
        col += 1
        if isSpanTextALocationField(spanText):
            locationText = spanText.replace("&nbsp;", " ").strip()
            lastLocationText = locationText
        elif isSpanTextATimeField(spanText):
            if lastLocationText is not None:
                locationText = lastLocationText
                col -= 1
            else:
                log.error("Unexpected number of spans when there was no previous location.  Please see the HTML log for the HTML encountered")
                htmlLog.error("<tr> contents is: " + tr.prettify())
                htmlLog.error("HTML text is: " + html)
                log.error("<tr> contents is: " + tr.prettify())
                log.error("HTML text is: " + html)
                shutdown(1)
        else:
            log.error("Unexpected span text: " + spanText)
            htmlLog.error("<tr> contents is: " + tr.prettify())
            htmlLog.error("HTML text is: " + html)
            shutdown(1)
        log.debug("locationText == " + locationText)


        # Start Time and End Time.
        startTimeText = None
        endTimeText = None
        spanText = spans[col].text.upper().strip()
        col += 1
        if isSpanTextATimeField(spanText):
            timeText = spanText.replace("&nbsp;", " ").strip()
            log.debug("timeText == " + timeText)
            timeTexts = timeText.split(" - ")
            startTimeText = timeTexts[0].strip()
            endTimeText = timeTexts[1].strip()
        else:
            log.error("Unexpected span text: " + spanText)
            htmlLog.error("<tr> contents is: " + tr.prettify())
            htmlLog.error("HTML text is: " + html)
            shutdown(1)
        log.debug("startTimeText == " + startTimeText)
        log.debug("endTimeText == " + endTimeText)
    
        # Description.
        descriptionText = None
        spanText = spans[col].text.upper().strip()
        col += 1
        if isSpanTextADescriptionField(spanText):
            descriptionText = spanText.replace("&nbsp;", " ").strip()
        else:
            log.error("Unexpected span text: " + spanText)
            htmlLog.error("<tr> contents is: " + tr.prettify())
            htmlLog.error("HTML text is: " + html)
            shutdown(1)
        log.debug("descriptionText == " + descriptionText)
    
    
        # Status.
        statusText = None
        spanText = spans[col].text.upper().strip()
        col += 1
        if isSpanTextAStatusField(spanText):
            statusText = spanText.replace("&nbsp;", " ").strip()
        else:
            log.error("Unexpected span text: " + spanText)
            htmlLog.error("<tr> contents is: " + tr.prettify())
            htmlLog.error("HTML text is: " + html)
            shutdown(1)
        log.debug("statusText == " + statusText)

        # Do cleanup of the statusText if possible.
        if re.search("sign up", statusText, re.IGNORECASE):
            statusText = "SIGN UP"
            log.debug("Cleaned up the statusText to: " + statusText)
        elif re.search("already filled", statusText, re.IGNORECASE):
            statusText = "ALREADY FILLED"
            log.debug("Cleaned up the statusText to: " + statusText)
        else:
            log.debug("No status text cleanup")

            
        shift = Shift()
        shift.date = dateText
        shift.location = locationText
        shift.startTime = startTimeText
        shift.endTime = endTimeText
        shift.description = descriptionText
        shift.status = statusText
    
        shifts.append(shift)
        log.debug("Created a Shift.  " + \
                  "There are now " + str(len(shifts)) + " shifts.")

    log.debug("Found " + str(len(shifts)) + " total shifts.")
    return shifts


def isSpanTextADateField(spanText):
    dateText = spanText
    if (len(dateText) < 10):
        log.debug("Date text should not be less than 10 characters: " + \
                  dateText)
        return False
    
    dateText = dateText[:10]
    
    if dateText[2] != "/" or \
            dateText[5] != "/" or \
            (not dateText[:2].isdigit()) or \
            (not dateText[3:5].isdigit()) or \
            (not dateText[6:].isdigit()):
        
        log.debug("Date text should be in MM/dd/yyyy.  Date text is: " + \
                  dateText)
        return False

    return True

def isSpanTextALocationField(spanText):
    locationText = spanText.replace("&nbsp;", " ").strip()
    if bool(re.search(r'\d', locationText)):
        log.debug("Location text is not expected to have numbers: " + \
                  locationText)
        return False
    elif locationText.find("-") != -1:
        log.debug("Location text is not expected to have hyphens: " + \
                  locationText)
        return False
    else:
        return True

def isSpanTextATimeField(spanText):
    timeText = spanText.replace("&nbsp;", " ").strip()
    if timeText.find("-") == -1:
        log.debug("Expected to find a hyphen in the time text: " + \
                  timeText)
        return False
        
    timeTexts = timeText.split(" - ")
    if len(timeTexts) != 2:
        log.debug("Expected to split to 2 str objects: " + \
                  timeText)
        return False
        
    startTimeText = timeTexts[0].strip()
    if startTimeText.find(":") == -1:
        log.debug("Expected to find a : in the startTimeText: " + \
                  startTimeText)
        return False
    
    endTimeText = timeTexts[1].strip()
    if endTimeText.find(":") == -1:
        log.debug("Expected to find a : in the endTimeText: " + \
                  endTimeText)
        return False

    return True

def isSpanTextADescriptionField(spanText):
    descriptionText = spanText.replace("&nbsp;", " ").strip()
    if bool(re.search(r'\d', descriptionText)):
        log.debug("Description text is not expected to have numbers: " + \
                  descriptionText)
        return False
    elif descriptionText.find("-") != -1:
        log.debug("Description text is not expected to have hyphens: " + \
                  descriptionText)
        return False
    else:
        if descriptionText not in ("MORNING", "AFTERNOON", "EVENING"):
            log.warn("Unusual descriptionText encountered: " + descriptionText)
        return True

    
def isSpanTextAStatusField(spanText):
    return True


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


def sendEmailNotificationMessage(newShiftsAvailableForSignup):
    global adminFromEmailAddress
    global alertToEmailAddresses
    fromEmailAddress = adminFromEmailAddress
    toEmailAddresses = alertToEmailAddresses
    
    emailSubject = "Application '" + APP_NAME + "' new shifts notification"
    
    endl = "<br />"
    emailBodyHtml = "Hi," + endl + endl + \
        "This is a notification from application '" + \
        APP_NAME + "' that new shifts available for signup.  " + \
        "Below are the new shifts available for signup:  " + endl + endl

    emailBodyHtml += "<table>" + endl
    for shift in newShiftsAvailableForSignup:
        emailBodyHtml += "  <tr>" + endl
        emailBodyHtml += "    <td>" + shift.date + "</td>" + endl
        emailBodyHtml += "    <td>" + shift.location + "</td>" + endl
        emailBodyHtml += "    <td>" + shift.startTime + " - " + shift.endTime + "</td>" + endl
        emailBodyHtml += "  </tr>" + endl
    emailBodyHtml += "</table>" + endl

    emailBodyHtml += endl
    emailBodyHtml += "-" + APP_NAME

    log.info("Sending notice email to: " + str(toEmailAddresses))
        
    client = boto3.client('ses')
    response = client.send_email(
        Destination={
            'ToAddresses': [],
            'CcAddresses': [],
            'BccAddresses': toEmailAddresses
            },
        Message={
            'Subject': {
                'Data': emailSubject,
                'Charset': 'UTF-8'
            },
            'Body': {
                'Html': {
                    'Data': emailBodyHtml,
                    'Charset': 'UTF-8'
                    }
                }
            },
        Source=fromEmailAddress,
        )
        
    log.info("Sending email done.")
    log.info("Response from AWS is: " + str(response))
    
def sendTextNotificationMessage(newShiftsAvailableForSignup):
    """
    Sends out a text message notifying the user that there are 
    new shifts available for signup.

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
    
    client = Client(twilioAccountSid, twilioAuthToken)

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
    initializeAdminEmailAddresses()
    initializeAlertEmailAddresses()
    
    while True:
        try:
            log.info("Fetching HTML pages ...")
            htmlPages = getHtmlPages()
            log.info("Fetching HTML pages done.  " + \
                     "Got " + str(len(htmlPages)) + " HTML pages total.")
            
            newShiftsAvailableForSignup = []

            for i in range(len(htmlPages)):
                htmlPage = htmlPages[i]
                
                log.info("Getting shifts from HTML page (i == " + \
                         str(i) + ") ...")
                         
                shifts = getShiftsFromHtml(htmlPage)
            
                newShiftsAvailableForSignup.extend(\
                    getNewShiftsAvailableForSignup(shifts))
                
            log.info("There are " + str(len(newShiftsAvailableForSignup)) + \
                     " new shifts available for signup since we last checked.")
            
            if len(newShiftsAvailableForSignup) > 0:
                sendTextNotificationMessage(newShiftsAvailableForSignup)
                sendEmailNotificationMessage(newShiftsAvailableForSignup)
            
            # We have been getting HTTP 504 errors at around 4:30 am
            # each morning, which causes our application to quit
            # due to the conservative error-handling code which
            # I have written.
            #
            # This code below is to have the script not make any HTTP requests 
            # to the web server around this time period.
            #
            now = datetime.datetime.now()
            if now.hour == 4 and (25 < now.minute < 50):
                numSeconds = 60 * 25
                log.debug("Sleeping for " + str(numSeconds) + " seconds ...")
                time.sleep(numSeconds)
            else:
                numSeconds = 60
                log.debug("Sleeping for " + str(numSeconds) + " seconds ...")
                time.sleep(numSeconds)

        except KeyboardInterrupt:
            log.info("Caught KeyboardInterrupt.  Shutting down cleanly ...")
            shutdown(0)
        

##############################################################################
