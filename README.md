------------
lcplpagesubs
------------

## Description:


--

## Installation

To install:

```bash
git clone https://github.com/rluu/lcplpagesubs.git
cd lcplpagesubs

virtualenv --python=`which python3` venv
source venv/bin/activate

pip install -r pip_requirements.txt
```

--

## Running

To run the software:

```bash
cd lcplpagesubs
source venv/bin/activate

export TWILIO_ACCOUNT_SID='YOUR_ACCOUNT_SID'
export TWILIO_AUTH_TOKEN='YOUR_AUTH_TOKEN'

python3 pageShiftsMonitorForLCPL.py
```

--

## Dependencies

python3

The following python3 dependencies are installed via pip:
- beautifulsoup4
- twilio
- requests

--
