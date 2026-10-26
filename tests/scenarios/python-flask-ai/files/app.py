import subprocess
from flask import Flask, request
from openai import OpenAI

app = Flask(__name__)
client = OpenAI()

@app.route("/ping")
def ping():
    host = request.args.get("host")
    # PLANTED: user input passed to a shell.
    return subprocess.check_output("ping -c 1 " + host, shell=True)
