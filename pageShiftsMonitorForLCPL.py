#!/usr/bin/env python3

import re
from bs4 import BeautifulSoup

import sqlite3

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


urls = [
    "http://www.signupgenius.com/go/4090d4aaeaf2ba7f58-page5",
    "http://www.signupgenius.com/go/4090d4aaeaf2ba7f58-page6",
    "http://www.signupgenius.com/go/4090d4aaeaf2ba7f58-page7",
    "http://www.signupgenius.com/go/4090d4aaeaf2ba7f58-page8"]

def exit(exitCode):
    conn.close()
    sys.exit(exitCode)


conn = sqlite3.connect("lcpl_page_shifts.db")
c = conn.cursor()
c.execute("""create table if not exists shifts (shift_date text, location text,
start_time text, end_time text, description text,
status text)""")
conn.commit()

html = None
with open("4090d4aaeaf2ba7f58-page8", "r") as f:
    html = f.readlines()

if html is None:
    print("Error: No html data.")
    exit(1)

data = []


#for url in urls:


soup = BeautifulSoup(html, 'html5lib')
mainTable = soup.body.table

isFirstRow = True
for tr in mainTable.children:
    print("DEBUG_rluu: a tr of mainTable is: " + tr)
    if isFirstRow:
        isFirstRow = False
        continue

    spans = tr.find_all('span')

    if (len(spans) != 5):
        print("Error: Unexpected number of spans: " + len(spans))
        exit(1)

    col = 0

    # Date.
    dateText = spans[col].contents.strip()
    if (len(dateText) < 8):
        print("Error: Unexpected length of date text: " + dateText)
        exit(1)
    dateText = dateText[:8]
    if dateText[2] != "/" or \
            dateText[5] != "/" or \
            (not dateText[:2].isdigit()) or \
            (not dateText[3:5].isdigit()) or \
            (not dateText[6:].isdigit()):

        print("Error: Date text is not MM/dd/yyyy.  Date text is: " + dateText)
        exit(1)

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

    data.append(shift)


newShiftsAvailableForSignup = []

for shift in data:
    c.execute("select * from shifts where " + \
            "shift_date = ? " + \
            "and location = ? " + \
            "and start_time = ? " + \
            "and end_time = ? " + \
            "and description = ?",
            shift.date, 
            shift.location,
            shift.startTime,
            shift.endTime,
            shift.description)

    numRows = c.getCount();
    if numRows == 0:
        # Never seen this value before.
        print("shift.status is: " + shift.status)
        if re.search("sign up", shift.status, re.IGNORECASE):
            newShiftsAvailableForSignup.append(shift)

        values = (self.date, self.location, self.startTime, self.endTime,
                self.description, self.status)
        c.execute("insert into shifts values (?, ?, ?, ?, ?, ?)", values)
        c.commit()

    elif numRows == 1:
        tup = c.fetchone()
        # Compare status.
        oldStatus = tup[5]
        if shift.status != oldStatus:
            print("DEBUG_rluu: Status changed from " + oldStatus + " to " + shift.status)
            if re.search("sign up", shift.status, re.IGNORECASE):
                newShiftsAvailableForSignup.append(shift)

            values = (self.status, \
                    self.date, self.location, self.startTime, self.endTime, self.description)
            c.execute("update shifts set " + \
                    "status = ? " + \
                    "where " + \
                    "shift_date = ? " + \
                    "and location = ? " + \
                    "and start_time = ? " + \
                    "and end_time = ? " + \
                    "and description = ?",
                    values)
            c.commit()
    else:
        print("Error: Unexpected number of rows for shift.  numRows == " + numRows + ", shift == " + str(shift))
        exit(1)

# TODO_rluu: Go through newShiftsAvailableForSignup and if there is
# anything in it, construct a meaningful concise message and a longer
# message.  The concise one for sending text message and a longer one for
# email.  

# TODO_rluu: Look into SES in AWS.  I am currently in a sandbox with that
# feature, with 200 emails sent allowed per 24-hour.  I may need to verify
# email addresses that I want to send to.

#To send a message to a Verizon Wireless phone from a personal computer,
#enter the person's mobile number followed by @vtext.com in the “to” field
#of your e-mail message – for example, 5551234567@vtext.com. Type an e-mail
#message as you would normally and send it. For more information, please
#visit www.vtext.com.Jul 25, 2007





