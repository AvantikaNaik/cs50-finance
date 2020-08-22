import os

from cs50 import SQL
from flask import Flask, flash, jsonify, redirect, render_template, request, session
from flask_session import Session
from tempfile import mkdtemp
from werkzeug.exceptions import default_exceptions, HTTPException, InternalServerError
from werkzeug.security import check_password_hash, generate_password_hash
from datetime import datetime
import datetime

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
    users = db.execute("SELECT cash from users where id= :user_id", user_id=session["user_id"])
    stocks = db.execute("SELECT symbol, SUM(shares) as total_shares FROM history WHERE user_id = :user_id GROUP BY symbol HAVING total_shares > 0", user_id=session["user_id"])

    portfolio = []
    share_tot = 0

    for stock in stocks:
        symbol = stock["symbol"]
        complete_data=lookup(symbol)
        share_price = complete_data["price"]
        shares = stock["total_shares"]
        total = share_price * shares
        share_tot += total
        portfolio.append({'symbol':symbol, 'shares':shares, 'price':share_price, 'total':total})

    cash_remaining = users[0]["cash"]
    grand_tot = share_tot + cash_remaining

    return render_template("portfolio.html", portfolio=portfolio, cash_remaining= cash_remaining, grand_tot=grand_tot)


@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():
    """Buy shares of stock"""
    if request.method == "POST":
        symbol = request.form.get("symbol").upper()
        quote = lookup(symbol)
        shares = int(request.form.get("shares"))

        if not symbol:
            return apology("You must provide a symbol!", 400)

        # check number box is empty
        if not shares:
            return apology("You must a provide the number of shares!", 400)

        # check stock exists
        if not quote:
            return apology("Provide a valid stock symbol!", 400)

        if shares <= 0:
            return apology("Please enter a positive number of shares!", 400)

        rows = db.execute("SELECT cash FROM users WHERE id=:user_id", user_id=session["user_id"])

        cash_remaining = rows[0]["cash"]
        share_price = quote["price"]

        total_price = share_price * shares

        if total_price > cash_remaining:
            return apology("You do not have enough money for this purchase!", 400)

        transaction_datetime = datetime.datetime.now()


        db.execute("UPDATE users SET cash = cash - :price WHERE id = :user_id", price=total_price, user_id=session["user_id"])

        db.execute("INSERT INTO history (user_id, symbol, shares, share_price, transaction_datetime, action_type) VALUES(:user_id, :symbol, :shares, :share_price, :transaction_datetime, 'buy')", user_id=session["user_id"], symbol=symbol, shares=shares, share_price=share_price, transaction_datetime=transaction_datetime)

        flash("Bought!")

        return redirect("/")
    else:
        return render_template("buy.html")

@app.route("/history")
@login_required
def history():
    """Show history of transactions"""

    transactions = db.execute("SELECT symbol, shares, share_price, transaction_datetime FROM history WHERE user_id = :user_id ORDER BY transaction_datetime", user_id=session["user_id"])

    return render_template("history.html", transactions=transactions)

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
        rows = db.execute("SELECT * FROM users WHERE username = :username",
                          username=request.form.get("username"))

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
    if request.method == "POST":

        if not request.form.get("symbol"):
            return apology("Must provide symbol")

        stock = lookup(request.form.get("symbol"))
        if stock == None:
            return apology("Stock could not be found")

        flash("Quoted!")

        return render_template("quoted.html", stock=stock)

    else:
        return render_template("quote.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":

        if len(request.form.get("password")) < 8:
            return apology("Password must be 8 or more characters long", 403)
        if not request.form.get("username"):
            return apology("You must provide a username!", 403)

        if not request.form.get("password"):
            return apology("You must provide a password!", 403)

        if not request.form.get("password") == request.form.get("confirmation"):
            return apology("Password and Confirmation must match!")



        hash = generate_password_hash(request.form.get("password"))

        usernames = db.execute("SELECT username FROM users WHERE username = :username", username=request.form.get("username"))

        if len(usernames) != 0:
            return apology("username taken", 400)

        new_user_id = db.execute("INSERT INTO users (username, hash) VALUES(:username, :hash)",
                                 username=request.form.get("username"),
                                 hash=hash)

        # Remember which user has logged in
        session["user_id"] = new_user_id

        # Display a flash message
        flash("Registered!")

        # Redirect user to home page
        return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("register.html")


@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    """Sell shares of stock"""
    if request.method == "POST":
        symbol = request.form.get("symbol").upper()
        quote = lookup(symbol)
        shares = int(request.form.get("shares"))

        stock = db.execute("SELECT SUM(shares) as total_shares FROM history WHERE user_id = :user_id and symbol = :symbol GROUP BY symbol", user_id = session["user_id"], symbol=request.form.get("symbol").upper())

        if quote == None:
            return apology("Enter a valid stock symbol please", 400)

        if shares <= 0:
            return apology("You can only sell positive shares!", 400)

        if len(stock) != 1:
            return apology("Only sell stocks you own!", 400)

        if stock[0]["total_shares"] <= 0:
            return apology("Please sell a positive number of shares!")

        if stock[0]["total_shares"] < shares:
            return apology("Don't sell more than you have!")

        rows = db.execute("SELECT cash from users where id= :user_id", user_id=session["user_id"])

        cash_remaining=rows[0]["cash"]
        share_price = quote["price"]

        total_price = share_price * shares
        transaction_datetime = datetime.datetime.now()

        shares = shares - (shares * 2)

        db.execute("UPDATE users SET cash = cash + :price WHERE id = :user_id", price=total_price, user_id=session["user_id"])

        db.execute("INSERT INTO history (user_id, symbol, shares, share_price, transaction_datetime, action_type) VALUES(:user_id, :symbol, :shares, :share_price, :transaction_datetime, 'sell')", user_id=session["user_id"], symbol=symbol, shares=shares, share_price=share_price, transaction_datetime=transaction_datetime)


        flash("Sold!")
        return redirect("/")

    else:
        return render_template("sell.html")


    return apology("TODO")


def errorhandler(e):
    """Handle error"""
    if not isinstance(e, HTTPException):
        e = InternalServerError()
    return apology(e.name, e.code)


# Listen for errors
for code in default_exceptions:
    app.errorhandler(code)(errorhandler)
