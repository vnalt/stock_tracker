from flask import Flask, request, render_template
import yfinance as yf
import requests
from bs4 import BeautifulSoup
import smtplib
from email.mime.text import MIMEText
import os
from dotenv import load_dotenv
import time

app = Flask(__name__)

# Load environment variables (for email credentials)
load_dotenv()
EMAIL_ADDRESS = os.getenv("EMAIL_ADDRESS")
EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD")

# Watchlist stored in memory (simple for now)
watchlist = []

@app.route("/", methods=["GET", "POST"])
def home():
    global watchlist
    if request.method == "POST":
        stock_symbol = request.form.get("stock_symbol")
        if stock_symbol and stock_symbol not in watchlist:
            watchlist.append(stock_symbol.upper() + ".BO")  # Add .BO for BSE stocks
    return render_template("index.html", watchlist=watchlist)

def get_stock_data(stock_symbol):
    stock = yf.Ticker(stock_symbol)
    data = stock.history(period="2d")  # Get 2 days of data
    if len(data) >= 2:
        prev_close = data["Close"].iloc[-2]
        current_price = data["Close"].iloc[-1]
        percent_change = ((current_price - prev_close) / prev_close) * 100
        return prev_close, current_price, percent_change
    return None, None, None

def get_bse_announcements(stock_symbol):
    url = "https://www.bseindia.com/data/xml/notices.xml"
    response = requests.get(url)
    soup = BeautifulSoup(response.content, "xml")
    items = soup.find_all("item")
    for item in items:
        title = item.find("title").text
        if stock_symbol.split(".")[0] in title:  # Check if stock is mentioned
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
        
        time.sleep(300)  # Check every 5 mins

if __name__ == "__main__":
    # Start monitoring in a separate thread
    import threading
    monitor_thread = threading.Thread(target=monitor_stocks)
    monitor_thread.daemon = True
    monitor_thread.start()
    # Run the Flask app
    app.run(host="0.0.0.0", port=5000)
    