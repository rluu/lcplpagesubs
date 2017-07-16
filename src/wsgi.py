#!/usr/bin/env python3

from serverstatus import app as application

if __name__ == "__main__":
    application.run(host="0.0.0.0", debug=False)

