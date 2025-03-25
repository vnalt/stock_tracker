from flask import Flask, request, render_template, jsonify
import yfinance as yf
import requests
from bs4 import BeautifulSoup
import smtplib
from email.mime.text import MIMEText
import os
from dotenv import load_dotenv
import time
import threading
import pandas as pd
from fuzzywuzzy import process
import json

app = Flask(__name__)

# Load environment variables
load_dotenv()
EMAIL_ADDRESS = os.getenv("EMAIL_ADDRESS")
EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD")

# Load BSE stock list
bse_stocks = pd.read_csv("Equity.csv")
stock_dict = {row["Security Name"].upper(): row["Security Code"] for index, row in bse_stocks.iterrows()}
valid_stocks = set(stock_dict.keys())
all_stock_options = [(name.upper(), str(code)) for name, code in stock_dict.items()]

# Watchlist persistence file
WATCHLIST_FILE = "watchlist.json"

# Load watchlist from file (or initialize empty)
def load_watchlist():
    if os.path.exists(WATCHLIST_FILE):
        with open(WATCHLIST_FILE, "r") as f:
            return json.load(f)
    return []

# Save watchlist to file
def save_watchlist(watchlist):
    with open(WATCHLIST_FILE, "w") as f:
        json.dump(watchlist, f)

# Initial watchlist
watchlist = load_watchlist()

@app.route("/", methods=["GET", "POST"])
def home():
    global watchlist
    error = None
    if request.method == "POST":
        stock_symbol = request.form.get("stock_symbol").upper()
        if stock_symbol in valid_stocks:
            stock_with_suffix = stock_symbol + ".BO"
            if stock_with_suffix not in watchlist:
                watchlist.append(stock_with_suffix)
                save_watchlist(watchlist)  # Save after adding
                send_email(
                    subject="Stock Subscription Confirmation",
                    body=f"You have subscribed to updates for {stock_with_suffix}."
                )
        else:
            error = f"Stock '{stock_symbol}' does not exist in the BSE repository. Check suggestions below."
    return render_template("index.html", watchlist=watchlist, error=error)

@app.route("/delete", methods=["POST"])
def delete_stock():
    global watchlist
    symbol = request.form.get("symbol")
    if symbol in watchlist:
        watchlist.remove(symbol)
        save_watchlist(watchlist)  # Save after deleting
        send_email(
            subject="Stock Removed",
            body=f"Removed {symbol} from your watchlist."
        )
    return render_template("index.html", watchlist=watchlist)

@app.route("/autocomplete", methods=["GET"])
def autocomplete():
    query = request.args.get("q", "").upper().strip()
    if not query:
        return jsonify([])

    searchable = [f"{name} ({code})" for name, code in all_stock_options]
    matches = process.extractBests(query, searchable, score_cutoff=50, limit=10)
    
    suggestions = []
    seen_names = set([s.split(".")[0] for s in watchlist])
    for match, score in matches:
        display_text = match
        name = display_text.split(" (")[0]
        if name not in seen_names and query in name:
            suggestions.append({"name": name, "display": display_text})

    return jsonify(suggestions)

def get_stock_data(stock_symbol):
    stock = yf.Ticker(stock_symbol)
    data = stock.history(period="2d")
    if len(data) >= 2:
        prev_close = data["Close"].iloc[-2]
        current_price = data["Close"].iloc[-1]
        percent_change = ((current_price - prev_close) / prev_close) * 100
        return prev_close, current_price, percent_change
    return None, None, None

def get_bse_announcements(stock_symbol):
    url = "https://www.bseindia.com/data/xml/notices.xml"
    response = requests.get(url)
    soup = BeautifulSoup(response.content, "lxml-xml")
    items = soup.find_all("item")
    for item in items:
        title = item.find("title").text
        if stock_symbol.split(".")[0] in title:
            return title
    return None

def send_email(subject, body):
    msg = MIMEText(body)
    msg["Subject"] = subject
    msg["From"] = EMAIL_ADDRESS
    msg["To"] = EMAIL_ADDRESS
    with smtplib.SMTP("smtp.gmail.com", 587) as server:
        server.starttls()
        server.login(EMAIL_ADDRESS, EMAIL_PASSWORD)
        server.send_message(msg)

def monitor_stocks():
    while True:
        updates = []
        for stock in watchlist:
            prev_close, current, percent_change = get_stock_data(stock)
            if percent_change and percent_change > 5:
                updates.append(f"{stock}: {percent_change:.2f}% increase")
            announcement = get_bse_announcements(stock)
            if announcement:
                updates.append(f"{stock} Announcement: {announcement}")
        if updates:
            send_email("Stock Update - " + time.ctime(), "\n".join(updates))
        time.sleep(300)  # Every 5 minutes

if __name__ == "__main__":
    monitor_thread = threading.Thread(target=monitor_stocks)
    monitor_thread.daemon = True
    monitor_thread.start()
    app.run(host="0.0.0.0", port=5000)
    