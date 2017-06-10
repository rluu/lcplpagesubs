# Page Shifts Monitor For LCPL

Author: Ryan Luu  
Email: ryanluu@gmail.com  
GitHub URL: https://github.com/rluu/lcplpagesubs  
Git Repository URL: https://github.com/rluu/lcplpagesubs.git  

## Description:

Monitors the LCPL Page Subs website, sending text message notifications when there are newly available signup slots.

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

export TWILIO_ACCOUNT_SID='YOUR_ACCOUNT_SID'
export TWILIO_AUTH_TOKEN='YOUR_AUTH_TOKEN'

python3 main.py
```

## Dependencies

- python3

The following python3 dependencies are installed via pip from the pip_requirements.txt file:
- beautifulsoup4
- twilio
- requests

