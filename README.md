# Page Shifts Monitor For LCPL

Author: Ryan Luu  
Email: ryanluu@gmail.com  
GitHub URL: https://github.com/rluu/lcplpagesubs  
Git Repository URL: https://github.com/rluu/lcplpagesubs.git  

## Description:

Monitors the LCPL Page Subs website, sending text message and email notifications when there are newly available signup slots.

## Installation

To install:

```bash
git clone https://github.com/rluu/lcplpagesubs.git
cd lcplpagesubs

virtualenv --python=`which python3` venv
source venv/bin/activate

pip install -r conf/pip_requirements.txt
```

## Running

To run the software:

```bash
cd lcplpagesubs
source venv/bin/activate

export TWILIO_ACCOUNT_SID="YOUR_ACCOUNT_SID"
export TWILIO_AUTH_TOKEN="YOUR_AUTH_TOKEN"
export TWILIO_SRC_PHONE_NUMBER="+1XXXYYYZZZZ"
export TWILIO_DEST_PHONE_NUMBER="+1XXXYYYZZZZ"

export LCPL_PAGE_SUBS_ADMIN_EMAIL_ADDRESS="username@example.com"
export LCPL_PAGE_SUBS_ALERT_EMAIL_ADDRESSES="user1@example.com,user2@example.com"

# Development and Production environments (can be started from any path):
python3 src/lcplpagesubs.py
```

To run the serverstatus HTTP server:

```bash
cd lcplpagesubs
source venv/bin/activate

# Development environment (can be started from any path):
python3 src/serverstatus.py --host=0.0.0.0 --port=5000 --debug

# Production environment (must be started from src directory):
cd src
gunicorn --workers=2 --timeout=60 --bind=0.0.0.0:5000 --log-config=../conf/logging.conf wsgi
```


## Dependencies

- python3

The following python3 dependencies are installed via pip from the pip_requirements.txt file:
- beautifulsoup4 (For parsing HTML)
- twilio (For sending SMS text messages)
- requests (For making HTTP requests)
- boto3 (AWS SDK library for Python)

- Flask (For running a HTTP status server)
- gunicorn (For running a HTTP status server)
- sh (For running shell commands in the status server)


