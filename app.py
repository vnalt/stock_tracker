from flask import Flask, request, render_template
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

app = Flask(__name__)

# Load environment variables
load_dotenv()
EMAIL_ADDRESS = os.getenv("EMAIL_ADDRESS")
EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD")

# Load BSE stock list (assumes Equity.csv is in the project folder)
bse_stocks = pd.read_csv("Equity.csv")
stock_dict = bse_stocks.set_index("Security Code").to_dict()["Security Name"]

# Watchlist stored in memory (resets on restart)
watchlist = []

@app.route("/", methods=["GET", "POST"])
def home():
    global watchlist
    if request.method == "POST":
        stock_symbol = request.form.get("stock_symbol")
        if stock_symbol and stock_symbol.upper() + ".BO" not in watchlist:
            stock_symbol = stock_symbol.upper() + ".BO"
            watchlist.append(stock_symbol)
            send_email(
                subject="Stock Subscription Confirmation",
                body=f"You have subscribed to updates for {stock_symbol}."
            )
    return render_template("index.html", watchlist=watchlist)

@app.route("/edit", methods=["POST"])
def edit_stock():
    global watchlist
    old_symbol = request.form.get("old_symbol")
    new_symbol = request.form.get("new_symbol")
    if old_symbol in watchlist and new_symbol:
        new_symbol = new_symbol.upper() + ".BO"
        if new_symbol not in watchlist:
            watchlist[watchlist.index(old_symbol)] = new_symbol
            send_email(
                subject="Stock Updated",
                body=f"Updated {old_symbol} to {new_symbol} in your watchlist."
            )
    return render_template("index.html", watchlist=watchlist)

@app.route("/delete", methods=["POST"])
def delete_stock():
    global watchlist
    symbol = request.form.get("symbol")
    if symbol in watchlist:
        watchlist.remove(symbol)
        send_email(
            subject="Stock Removed",
            body=f"Removed {symbol} from your watchlist."
        )
    return render_template("index.html", watchlist=watchlist)

@app.route("/autocomplete", methods=["GET"])
def autocomplete():
    query = request.args.get("q", "").upper()
    suggestions = [
        {"id": code, "name": name}
        for code, name in stock_dict.items()
        if query in str(code) or query in name.upper()
    ][:10]  # Top 10 matches
    return {"suggestions": suggestions}

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
    