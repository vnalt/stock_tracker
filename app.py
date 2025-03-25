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

app = Flask(__name__)

# Load environment variables (for email credentials)
load_dotenv()
print("Loaded .env - EMAIL_ADDRESS:", os.getenv("EMAIL_ADDRESS"))  # Debug line
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
            stock_symbol = stock_symbol.upper() + ".BO"  # Add .BO for BSE stocks
            watchlist.append(stock_symbol)
            # Send confirmation email
            send_email(
                subject="Stock Subscription Confirmation",
                body=f"You have subscribed to updates for {stock_symbol}. You’ll receive notifications for price changes >5% or BSE announcements."
            )
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
    print(f"Attempting to send email: {subject}")
    print(f"Using EMAIL_ADDRESS: {EMAIL_ADDRESS}")
    print(f"Using EMAIL_PASSWORD: {EMAIL_PASSWORD}")
    msg = MIMEText(body)
    msg["Subject"] = subject
    msg["From"] = EMAIL_ADDRESS
    msg["To"] = EMAIL_ADDRESS

    try:
        with smtplib.SMTP("smtp.gmail.com", 587) as server:
            print("Connecting to SMTP server...")
            server.starttls()
            print("Starting TLS...")
            server.login(EMAIL_ADDRESS, EMAIL_PASSWORD)
            print("Logged in successfully")
            server.send_message(msg)
            print("Email sent successfully")
    except Exception as e:
        print(f"Failed to send email: {e}")

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
        
        time.sleep(300)  # Check every 5 minutes

if __name__ == "__main__":
    # Start monitoring in a separate thread
    monitor_thread = threading.Thread(target=monitor_stocks)
    monitor_thread.daemon = True
    monitor_thread.start()
    # Run the Flask app
    app.run(host="0.0.0.0", port=5000)
