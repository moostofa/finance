import os

from cs50 import SQL
from flask import Flask, flash, redirect, render_template, request, session
from flask_session import Session
from tempfile import mkdtemp
from werkzeug.exceptions import default_exceptions, HTTPException, InternalServerError
from werkzeug.security import check_password_hash, generate_password_hash

from helpers import apology, login_required, lookup, usd

# Configure application
app = Flask(__name__)

# Ensure templates are auto-reloaded
app.config["TEMPLATES_AUTO_RELOAD"] = True


# Ensure responses aren't cached
@app.after_request
def after_request(response):
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Expires"] = 0
    response.headers["Pragma"] = "no-cache"
    return response


# Custom filter
app.jinja_env.filters["usd"] = usd

# Configure session to use filesystem (instead of signed cookies)
app.config["SESSION_FILE_DIR"] = mkdtemp()
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Configure CS50 Library to use SQLite database
db = SQL("sqlite:///finance.db")

# Make sure API key is set
if not os.environ.get("API_KEY"):
    raise RuntimeError("API_KEY not set")


@app.route("/")
@login_required
def index():
    """Show portfolio of stocks"""
    portfolio = db.execute("SELECT symbol, shares FROM portfolio where user_id = ? ORDER BY symbol", session["user_id"])
    for company in portfolio:
        #lookup real-time data for the stock
        company_lookup = lookup(company["symbol"])  

        #append stock information to the dictionary
        company["name"] = company_lookup["name"]
        company["price"] = (company_lookup["price"])
        company["TOTAL"] = round((company["shares"] * company["price"]), 2)
    
    #get cash balance of current user
    cash = round((db.execute("SELECT cash FROM users WHERE id = ?", session["user_id"])[0]["cash"]), 2)

    #pass in the portfolio details and cash balance into a JS file
    with open("static/info.js", "w") as file:
        file.write(f"let portfolio = {portfolio};\nlet cash = {cash};")  
    return render_template("index.html", cash = cash)

@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():
    """Buy shares of stock"""
    if request.method == "POST":
        #validate symbol
        symbol = request.form.get("symbol")                     
        if symbol.strip() == "" or not symbol:
            return apology("please enter a symbol", 403)
                                                              
        #check if ticket symbol exists
        if not lookup(symbol):
            return apology("ticker symbol does not exist", 403) 
        
        #validate shares
        shares = request.form.get("shares")
        if not shares:
            return apology("please enter a number of shares to purchase", 403)
            
        if int(shares) < 0:
            return apology("please enter a positive number", 403)

        #get all the data required
        user_id = session["user_id"]
        symbol = symbol.upper()
        name = lookup(symbol)["name"]
        shares = int(shares)
        price = lookup(symbol)["price"]
        cash = db.execute("SELECT cash FROM users WHERE id = ?", session["user_id"])[0]["cash"]

        #validate purchase
        purchase = shares * price
        if purchase > cash:
            return apology("insufficient funds", 403)
        cash -= purchase

        #update cash balance of the user
        db.execute("UPDATE users SET cash = cash - ? WHERE id = ?", purchase, user_id)

        #insert stock details to user portfolio
        #execute query to check if user already owns shares of chosen stock
        SQL_exists_value = list(db.execute("SELECT EXISTS (SELECT symbol FROM portfolio WHERE user_id = ? AND symbol = ?)", user_id, symbol)[0].values())[0]

        #if user already showns share of this stock, update share count
        if SQL_exists_value == 0:       
            db.execute("INSERT INTO portfolio VALUES (?, ?, ?, ?)", user_id, symbol, name, shares)
        #otherwise, create a new row for the shares
        else:                           
            db.execute("UPDATE portfolio SET shares = shares + ? WHERE user_id = ? AND symbol = ?", shares, user_id, symbol)

        #insert transaction details
        db.execute("INSERT INTO transaction_data VALUES (?, ?, ?, datetime('now'))", user_id, symbol, shares)

        return redirect("/")
    else:       #if method is GET
        return render_template("buy.html")


@app.route("/history")
@login_required
def history():
    """Show history of transactions"""
    transactions = db.execute("SELECT symbol, shares, time FROM transaction_data WHERE user_id = ? ORDER BY time", session["user_id"])
    for transaction in transactions:
        transaction["price"] = lookup(transaction["symbol"])["price"]

    with open("static/info.js", "w") as file:
        file.write(f"let transactions = {transactions}")  
    return render_template("history.html")

@app.route("/login", methods=["GET", "POST"])
def login():
    """Log user in"""

    # Forget any user_id
    session.clear()

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        # Ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username", 403)

        # Ensure password was submitted
        elif not request.form.get("password"):
            return apology("must provide password", 403)

        # Query database for username
        rows = db.execute("SELECT * FROM users WHERE username = ?", request.form.get("username"))

        # Ensure username exists and password is correct
        if len(rows) != 1 or not check_password_hash(rows[0]["hash"], request.form.get("password")):
            return apology("invalid username and/or password", 403)

        # Remember which user has logged in
        session["user_id"] = rows[0]["id"]

        # Redirect user to home page
        return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("login.html")


@app.route("/logout")
def logout():
    """Log user out"""

    # Forget any user_id
    session.clear()

    # Redirect user to login form
    return redirect("/")


@app.route("/quote", methods=["GET", "POST"])
@login_required
def quote():
    """Get stock quote."""
    if request.method == "POST":        #when user fills in and submits the form
        #get ticker symbol
        symbol = request.form.get("symbol")                     
        if symbol.strip() == "" or not symbol:
            return apology("please enter a symbol", 403)
                                                              
        #look up ticker symbol and get quote
        quote = lookup(symbol)
        if not quote:
            return apology("ticker symbol does not exist", 403) 
        
        return render_template("quoted.html", stock_info = quote)
    else:       #else: GET request for quote.html
        return render_template("quote.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    """Register user"""
    #consider doing this part in javascript
    #get a list of existing usernames
    existing_usernames = db.execute("SELECT username FROM users")
    
    #if the form is submitted
    if request.method == "POST":
        #check for valid username
        name = request.form.get("username")
        if not name:
            return apology("must provide username", 403)
        if name in existing_usernames:
            return apology("username already exists", 403)
            
        password = request.form.get("password")
        confirm_password = request.form.get("confirm-password")
        
        #check for valid password
        if not password: 
            return apology("please provide a password", 403)
        if password != confirm_password:
            return apology("passwords do not match", 403)
            
        #add new user to database
        db.execute("INSERT INTO users (username, hash) VALUES (?, ?)", name, generate_password_hash(password))
        return redirect("/")
    else:       
        return render_template("register.html")     #GET request: display register.html to user     


@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    """Sell shares of stock"""
    return apology("TODO")


def errorhandler(e):
    """Handle error"""
    if not isinstance(e, HTTPException):
        e = InternalServerError()
    return apology(e.name, e.code)


# Listen for errors
for code in default_exceptions:
    app.errorhandler(code)(errorhandler)

"""
CREATE TABLE portfolio (
    user_id INTEGER,
    symbol TEXT NOT NULL,
    name TEXT NOT NULL,
    shares INTEGER, 
    FOREIGN KEY(user_id) REFERENCES users(id)
);

CREATE UNIQUE INDEX user_id ON portfolio(user_id)
"""