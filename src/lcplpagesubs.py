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
from requests.exceptions import RequestException
from requests.exceptions import ConnectionError
import time
import boto3
import botocore
from botocore.exceptions import EndpointConnectionError
from twilio.rest import Client
from twilio.base.exceptions import TwilioException
from twilio.base.exceptions import TwilioRestException
from bs4 import BeautifulSoup

##############################################################################
# Global variables
##############################################################################

__version__ = "1.2.0"
__date__ = "Sat Jul  1 16:56:44 EDT 2017"


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

# Seed URL on the very first load of the application
# (when the 'urls' database table has not been created yet).
# The 'seedUrl' should be the earliest in time (left-most tab URL).
baseUrl = "http://www.signupgenius.com/go/"
seedUrl = baseUrl + "4090D4AAEAF2BA7F58-page8"

# For logging.
# Logging config file specifies the log filename relative to the current
# directory, so we need to chdir to the SRC_DIR before loading the logging
# config.
os.chdir(SRC_DIR)
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
        self.url = None
        self.rowNumber = None
        self.status = None

    def __str__(self):
        rv = "Shift(url=" + str(self.url) + "," + \
                "rowNumber=" + str(self.rowNumber) + "," + \
                "status=" + str(self.status) + ")"
        return rv

##############################################################################
# Methods
##############################################################################

def sendAdminNotificationEmail(emailSubject = "", emailBodyHtml = ""):
    global adminErrorEmailSendingEnabled
    global adminFromEmailAddress
    global adminToEmailAddress
    
    if adminErrorEmailSendingEnabled == True and \
            adminFromEmailAddress is not None and \
            adminToEmailAddress is not None:

        fromEmailAddress = adminFromEmailAddress
        toEmailAddress = adminToEmailAddress
        
        log.info("Sending notice email to administrator (" + \
                 str(toEmailAddress) + \
                 ").")
        log.debug("emailSubject: " + emailSubject + \
                ", emailBodyHtml: " + emailBodyHtml)

        shouldTryAgain = True
        while shouldTryAgain:
            shouldTryAgain = False
            try:
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
            except EndpointConnectionError as e:
                log.error("Caught EndpointConnectionError: " + str(e))
                
                shouldTryAgain = True
                numSeconds = 60
                log.info("Retry in " + str(numSeconds) + " seconds ...")
                time.sleep(numSeconds)
                
                
def shutdown(rc):
    """
    Exits the script, but first flushes all logging handles, etc.
    """

    global adminErrorEmailSendingEnabled
    global conn

    if conn is not None:
        log.info("Closing database connection ...")
        conn.close()
        log.info("Done closing database connection.")

    if rc != 0 and adminErrorEmailSendingEnabled == True:
        emailSubject = \
            "Shutdown Notification for Application '" + APP_NAME + "' "
        endl = "<br />"
        emailBodyHtml = "Hi," + endl + endl + \
            "This is a notification to the site Admin that application '" + \
            APP_NAME + "' has quit unexpectedly with non-zero return code: " + \
            str(rc) + ".  " + \
            "Please investigate at your earliest convenience.  Thank you." + \
            endl + endl
        emailBodyHtml += "-" + APP_NAME

        sendAdminNotificationEmail(emailSubject, emailBodyHtml)
        
    log.info("Shutdown (rc=" + str(rc) + ").")
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
        "url text, " +
        "row_number text, " +
        "status text)")
    conn.commit()
    cursor.execute("create table if not exists urls " +
        "(crte_utc_dttm text, " +
        "upd_utc_dttm text, " +
        "url text, " +
        "active_ind text)")
    conn.commit()

    # If the 'urls' table is empty, then add a seed URL.
    activeInd = "1"
    values = (activeInd,)
    cursor.execute("select * from urls where " + \
                   "active_ind = ?",
                   values)
    tups = cursor.fetchall()
    log.debug("Fetched " + str(len(tups)) + " rows from the database.")
    
    if len(tups) == 0:
        log.info("Seeding active URLs with initial URL: " + seedUrl)
        
        crteUtcDttm = datetime.datetime.utcnow().isoformat()
        updUtcDttm = crteUtcDttm
        activeInd = "1"
        values = (crteUtcDttm, updUtcDttm, seedUrl, activeInd)
        cursor.execute("insert into urls values (?, ?, ?, ?)",
                       values)
        conn.commit()
        log.debug("Done.")
        
    
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
    Returns a list of tuples.  
    Each tuple contains the following:
      - str containing the URL
      - str containing the contents of a HTML page.
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
    # Old style way of hard-coding URLs.
    if False:
        urls = [
            #"http://www.signupgenius.com/go/4090d4aaeaf2ba7f58-page5",
            #"http://www.signupgenius.com/go/4090d4aaeaf2ba7f58-page6",
            "http://www.signupgenius.com/go/4090d4aaeaf2ba7f58-page7",
            "http://www.signupgenius.com/go/4090d4aaeaf2ba7f58-page8",
            "http://www.signupgenius.com/go/4090d4aaeaf2ba7f58-page11",
            "http://www.signupgenius.com/go/4090d4aaeaf2ba7f58-page12",
            "http://www.signupgenius.com/go/4090d4aaeaf2ba7f58-page13",
            ]
    ######################
    
    # Get list of active URLs from the database.
    activeInd = "1"
    values = (activeInd,)
    cursor.execute("select * from urls where " + \
                   "active_ind = ? " + \
                   "order by upd_utc_dttm asc",
                   values)
    tups = cursor.fetchall()
    log.debug("Fetched " + str(len(tups)) + \
              " rows from the 'urls' database table.")
    
    if len(tups) == 0:
        log.error("No active URLs were found in the database.  " + \
                  "Please investigate.")
        shutdown(1)

    urls = []
    for tup in tups:
        log.debug("Looking at 'urls' row: " + str(tup))
        crteUtcDttm = tup[0]
        updUtcDttm = tup[1]
        url = tup[2]
        activeInd = tup[3]

        urls.append(url)

    #log.debug("List of active URLs is: " + str(urls))
        
    for url in urls:
        shouldTryAgain = True
        while shouldTryAgain:
            shouldTryAgain = False
            try:
                log.info("Fetching webpage from URL: " + url)
                r = requests.get(url)
                log.debug("HTTP status code: " + str(r.status_code))
                numSeconds = 2
                time.sleep(numSeconds)
                if 200 <= r.status_code < 300:
                    html = r.text
                    tup = (url, html)
                    htmls.append(tup)
                elif r.status_code in [500, 502, 503, 504]:
                    log.warn("URL: " + url)
                    log.warn("Unexpected HTTP status code: " + str(r.status_code))
                    log.warn("Response text is: " + str(r.text))
    
                    shouldTryAgain = True
                    numSeconds = 60
                    log.info("Retry in " + str(numSeconds) + " seconds ...")
                    time.sleep(numSeconds)
                else:
                    log.error("URL: " + url)
                    log.error("Unexpected HTTP status code: " + str(r.status_code))
                    log.error("Response text is: " + str(r.text))
                    
                    emailSubject = \
                        "Admin Notification for Application '" + APP_NAME + "' "
                    endl = "<br />"
                    emailBodyHtml = "Hi," + endl + endl + \
                        "This is a notification to the site Admin that " + \
                        "application '" + APP_NAME + \
                        "' encountered an unexpected HTTP status code.  " + \
                        "Please investigate at your earliest convenience.  " + \
                        "Thank you." + \
                        endl + endl + \
                        "URL was: " + url + \
                        endl + endl + \
                        "Unexpected HTTP status code: " + str(r.status_code) + \
                        endl + endl + \
                        "Response text was: " + str(r.text) + \
                        endl + endl + \
                        "-" + APP_NAME
                    
                    sendAdminNotificationEmail(emailSubject, emailBodyHtml)
                    shutdown(1)
                    
            except ConnectionError as e:
                log.error("Caught ConnectionError: " + str(e))
                
                shouldTryAgain = True
                numSeconds = 60
                log.info("Retry in " + str(numSeconds) + " seconds ...")
                time.sleep(numSeconds)
                
            except RequestException as e:
                log.error("URL: " + url)
                log.error("Caught RequestException: " + str(e))
                
                emailSubject = \
                    "Admin Notification for Application '" + APP_NAME + "' "
                endl = "<br />"
                emailBodyHtml = "Hi," + endl + endl + \
                    "This is a notification to the site Admin that " + \
                    "application '" + APP_NAME + \
                    "' encountered an unexpected RequestException.  " + \
                    "Please investigate at your earliest convenience.  " + \
                    "Thank you." + \
                    endl + endl + \
                    "URL was: " + url + \
                    endl + endl + \
                    "RequestException was: " + str(e) + \
                    endl + endl + \
                    "-" + APP_NAME
                    
                sendAdminNotificationEmail(emailSubject, emailBodyHtml)
                shutdown(1)

    return htmls


def updateActiveUrlsFromHtml(htmlTup, isFirstURL):
    """
    Reads the input html str, and from the contents, does the following:

      - Determines the URLs that should be active.
      - Determines the URLs that should not be active.
      - Update the database table 'urls' to be representative of the 
        desired active and inactive URLs.

    Arguments:

    htmlTup - tuple containing two entries.  
        First entry is the URL
        Second entry is the HTML text to parse.

    isFirstURL - bool containing True if it is the 
                 first URL being analyzed in the list.
    """
    
    url = htmlTup[0]
    html = htmlTup[1]

    log.debug("URL is: " + url)
    
    soup = BeautifulSoup(html, 'html5lib')
    mainTable = soup.find("table", {"class" : "SUGtableouter"})
    if mainTable == None and isFirstURL == True:
        # URL should be set to inactive.
        #
        # Could not find a HTML table with class SUGtableouter
        # which is our main table which contains all the shifts.
        # Since this is the first URL for this iteration of
        # parsing URLs, this URL will be marked as inactive in
        # future loops.  If further investigation is desired,
        # please see the HTML log for the HTML encountered.
        #
        log.debug("URL is active and should be inactive.")
        log.info("Setting URL to inactive: " + url)
        htmlLog.info("HTML text is: " + html)
        updUtcDttm = datetime.datetime.utcnow().isoformat()
        activeInd = "0"
        values = (updUtcDttm, activeInd, url)
        cursor.execute("update urls set upd_utc_dttm = ?, active_ind = ? " + \
                       "where url = ?",
                        values)
        conn.commit()
        log.info("Done setting URL to inactive.")
    
    elif mainTable is not None:
        # URL is still active.
        log.debug("Found mainTable, therefore this URL is still active.")
        log.debug("Now examining URLs in the nav tabs ...")
        
        # Get URLs from the page.
        navTabs = soup.find("ul", {"class" : "nav-tabs"})
        if navTabs == None:
            log.error("Could not find a <ul> element with CSS class " + \
                      "'nav-tabs' when one was expected.  " + \
                      "Please investigate further.  " + \
                      "HTML will be logged to the HTML log.")
            htmlLog.error("HTML text is: " + html)
            shutdown(1)
        else:
            aElements = []
            for li in navTabs.findAll("li", recursive=False):
                htmlLog.debug("A <li> of navTabs is: " + li.prettify())
                for a in li.findAll("a", recursive=False):
                    htmlLog.debug("A <a> of <li> is: " + a.prettify())
                    aElements.append(a)

            for a in aElements:
                htmlLog.debug("Looking at <a>: " + a.prettify())
                onClickValue = a["onclick"]

                if onClickValue.find("checkFormChanges") == -1:
                    log.error("Could not find the expected javascript " + \
                              "method name in the 'onclick' attribute.  " + \
                              "Please investigate further.  " + \
                              "Logging HTML to the HTML log.")
                    htmlLog.error(html)
                    shutdown(1)
                    
                splittedValues = onClickValue.split("'")
                if len(splittedValues) == 3:
                    pageName = splittedValues[1]
                    navTabUrl = baseUrl + pageName
                    log.debug("URL assembled from the nav tab is: " + navTabUrl)

                    values = (navTabUrl,)
                    
                    cursor.execute("select * from urls where " + \
                                   "url = ? " + \
                                   "order by upd_utc_dttm desc limit 1",
                                   values)

                    tups = cursor.fetchall()
                    
                    if len(tups) == 0:
                        # Initial time seeing this URL.
                        log.debug("Initial time seeing this URL.")
                        log.info("Setting URL to active: " + navTabUrl)
                        crteUtcDttm = datetime.datetime.utcnow().isoformat()
                        updUtcDttm = crteUtcDttm
                        activeInd = "1"
                        values = (crteUtcDttm, updUtcDttm, navTabUrl, activeInd)
                        cursor.execute("insert into urls values (?, ?, ?, ?)",
                                       values)
                        conn.commit()
                        log.info("Done setting URL to active.")
                        
                    elif len(tups) == 1:
                        # URL was stored previously.
                        log.debug("URL was stored previously.")
                        tup = tups[0]
                        activeIndColumn = 3
                        activeInd = tup[activeIndColumn]
                        if str(activeInd) == "1":
                            log.debug("URL is active and should stay active.")
                        elif str(activeInd) == "0":
                            log.debug("URL is inactive and should be active.")
                            log.info("Setting URL to active: " + navTabUrl)
                            
                            updUtcDttm = datetime.datetime.utcnow().isoformat()
                            activeInd = "1"
                            values (updUtcDttm, activeInd, navTabUrl)
                            cursor.execute("update urls set " + \
                                            "upd_utc_dttm = ?, " + \
                                            "active_ind = ? " + \
                                            "where url = ?",
                                            values)
                            conn.commit()
                            log.info("Done setting URL to active.")
                        else:
                            log.error("Unknown activeInd encountered: " + 
                                        str(activeInd))
                            shutdown(1)
                    else:
                        log.error("Unexpected number of rows for urls.  " + \
                                  "len(tups) == " + str(len(tups)))
                        shutdown(1)

    else:
        log.debug("After examining the HTML for this page, we determined " + \
                  "there's no need to take any action updating any URLs " + \
                  "to active status or to inactive status.")
        
    
def getShiftsFromHtml(htmlTup, isFirstURL=False):
    """
    Reads the input html str, and extracts the shifts.

    Arguments:
    htmlTup - tuple containing two entries.  
        First entry is the URL
        Second entry is the HTML text to parse.

    Returns:
    list of Shift objects
    """
    
    shifts = []
    
    url = htmlTup[0]
    html = htmlTup[1]
    
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
    
    currRow = 0
    for tr in mainTableBody.findAll("tr", recursive=False):
        htmlLog.debug("A <tr> of mainTableBody is: " + tr.prettify())
        log.debug("There are " + str(len(tr.findAll("td"))) + \
                  " <td> inside this <tr>")
        log.debug("There are " + str(len(tr.findAll("span"))) + \
                  " <span> inside this <tr>")
            
        if currRow == 0:
            log.debug("Skipping first row.")
            currRow += 1
            continue
        else:
            log.debug("Not first row.  Parsing...")
            currRow += 1

        trLowered = tr.prettify().lower()

        # Status.
        if re.search("already filled", trLowered, re.IGNORECASE):
            statusText = "ALREADY FILLED"
        elif re.search("sign up", trLowered, re.IGNORECASE):
            statusText = "SIGN UP"
        else:
            log.error("Unexpected span text: " + spanText)
            htmlLog.error("<tr> contents is: " + tr.prettify())
            htmlLog.error("HTML text is: " + html)
            shutdown(1)
        log.debug("statusText == " + statusText)

        shift = Shift()
        shift.url = url
        shift.rowNumber = currRow
        shift.status = statusText
    
        shifts.append(shift)
        log.debug("Created a Shift.  " + \
                  "There are now " + str(len(shifts)) + " shifts.")

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
        
        values = (shift.url, 
                  shift.rowNumber)
        
        cursor.execute("select * from shifts where " + \
                "url = ? " + \
                "and row_number = ? " + \
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
                    shift.url,
                    shift.rowNumber,
                    shift.status)
            cursor.execute("insert into shifts values (?, ?, ?, ?)",
                           values)
            conn.commit()
    
        elif len(tups) == 1:
            # Status was stored previously for this shift.
            # Compare status.
            tup = tups[0]
            statusColumn = 3
            oldStatus = tup[statusColumn]
            if shift.status != oldStatus:
                log.info("Status changed from " + oldStatus + \
                         " to " + shift.status + " for: " + \
                         str(shift))
                         
                if re.search("sign up", shift.status, re.IGNORECASE):
                    newShiftsAvailableForSignup.append(shift)

                crteUtcDttm = datetime.datetime.utcnow().isoformat()
                values = (crteUtcDttm,
                        shift.url,
                        shift.rowNumber,
                        shift.status)
                cursor.execute("insert into shifts values (?, ?, ?, ?)",
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
        APP_NAME + "' that there "
    if len(newShiftsAvailableForSignup) == 1:
        emailBodyHtml += "is " + str(len(newShiftsAvailableForSignup)) + \
            " new shift available for signup.  "
    else:
        emailBodyHtml += "are " + str(len(newShiftsAvailableForSignup)) + \
            " new shifts available for signup.  "
    emailBodyHtml += "Please visit the below URL(s) to see them:" + endl + endl

    # Extract unique URLs in a sorted list.
    urls = []
    for shift in newShiftsAvailableForSignup:
        if shift.url not in urls:
            urls.append(shift.url)
    urls.sort()
    
    emailBodyHtml += "<table>" + endl
    for url in urls:
        emailBodyHtml += "  <tr>" + endl
        emailBodyHtml += "    <td>" + endl
        emailBodyHtml += "      <a href='" + url + "'>" + url + "</a>" + endl
        emailBodyHtml += "    </td>" + endl
        emailBodyHtml += "  </tr>" + endl
    emailBodyHtml += "</table>" + endl

    emailBodyHtml += endl
    emailBodyHtml += "-" + APP_NAME

    log.info("Sending notice email to: " + str(toEmailAddresses))
        
    shouldTryAgain = True
    while shouldTryAgain:
        shouldTryAgain = False
        try:
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
        except EndpointConnectionError as e:
            log.error("Caught EndpointConnectionError: " + str(e))
                
            shouldTryAgain = True
            numSeconds = 60
            log.info("Retry in " + str(numSeconds) + " seconds ...")
            time.sleep(numSeconds)
                
    
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
            " new shift available for signup." + endl
    else:
        msg += "There are " + str(len(newShiftsAvailableForSignup)) + \
            " new shifts available for signup." + endl
    
    # Send text message via Twilio.
    global twilioAccountSid
    global twilioAuthToken
    global sourcePhoneNumber
    global destinationPhoneNumber

    if twilioAccountSid is None or twilioAccountSid.strip() == "":
        log.error("twilioAccountSid may not be empty.")
        shutdown(1)

    if twilioAuthToken is None or twilioAuthToken.strip() == "":
        log.error("twilioAuthToken may not be empty.")
        shutdown(1)

    try:
        client = Client(twilioAccountSid, twilioAuthToken)
    
        log.info("Sending text message from phone number " +
                    sourcePhoneNumber + " to phone number " +
                    destinationPhoneNumber + " with message body: " + msg)

        client.messages.create(from_=sourcePhoneNumber,
                               to=destinationPhoneNumber,
                               body=msg)
        
        log.info("Sending text message done.")
        
    except TwilioRestException as e:
        log.error("Caught TwilioRestException: " + str(e))
        shutdown(1)
    except TwilioException as e:
        log.error("Caught TwilioException: " + str(e))
        shutdown(1)
    except BaseException as e:
        log.error("Caught BaseException: " + str(e))
        shutdown(1)
        


##############################################################################
# Main
##############################################################################

if __name__ == "__main__":
    log.info("##########################################################")
    log.info("# Starting " + APP_NAME + \
             " (" + sys.argv[0] + "), version " + APP_VERSION)
    log.info("##########################################################")

    initializeAdminEmailAddresses()
    initializeAlertEmailAddresses()
    initializeDatabase()
    initializeTwilio()
    
    while True:
        try:
            log.info("Fetching HTML pages ...")
            htmlPages = getHtmlPages()
            log.info("Fetching HTML pages done.  " + \
                     "Got " + str(len(htmlPages)) + " HTML pages total.")
            
            newShiftsAvailableForSignup = []

            for i in range(len(htmlPages)):
                htmlPage = htmlPages[i]
                url = htmlPage[0]
                
                log.info("Getting shifts from HTML page (i == " + \
                         str(i) + ") (url == " + url + ")...")
                         
                shifts = getShiftsFromHtml(htmlPage)
            
                newShiftsAvailableForSignup.extend(\
                    getNewShiftsAvailableForSignup(shifts))
                
                log.info("Checking in this HTML page for any changes " + \
                         "to what URLs are active (i == " + \
                         str(i) + ") (url == " + url + ")...")

                isFirstUrl = None
                if i == 0:
                    isFirstUrl = True
                else:
                    isFirstUrl = False
                    
                updateActiveUrlsFromHtml(htmlPage, isFirstUrl)
                
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
            if now.hour == 4 and now.minute > 25:
                numSeconds = 60 * 70
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
