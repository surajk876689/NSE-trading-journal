import sqlite3
import os
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, g, jsonify

app = Flask(__name__)
DATABASE = 'trades.db'


def get_db():
    """Return a sqlite3 connection to trades.db."""
    db = getattr(g, '_database', None)
    if db is None:
        db = g._database = sqlite3.connect(DATABASE)
        db.row_factory = sqlite3.Row
    return db


def init_db():
    """Create the trades table if not exists, and migrate old schema."""
    db = sqlite3.connect(DATABASE)
    db.execute('''
        CREATE TABLE IF NOT EXISTS trades (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            stock_name   TEXT    NOT NULL,
            buy_price    REAL    NOT NULL,
            sell_price   REAL    NOT NULL,
            quantity     REAL    NOT NULL,
            buy_date     TEXT    NOT NULL,
            sell_date    TEXT    NOT NULL,
            holding_days INTEGER,
            profit       REAL,
            pct_return   REAL
        )
    ''')
    # Migrate: add new columns to existing DB if missing
    cols = [r[1] for r in db.execute("PRAGMA table_info(trades)").fetchall()]
    for col, defn in [
        ('buy_date',     "TEXT NOT NULL DEFAULT ''"),
        ('sell_date',    "TEXT NOT NULL DEFAULT ''"),
        ('holding_days', "INTEGER DEFAULT 0"),
    ]:
        if col not in cols:
            db.execute(f'ALTER TABLE trades ADD COLUMN {col} {defn}')
    db.commit()
    db.close()


def calculate_pnl(buy, sell, qty):
    """Return (profit, pct_return) for a trade."""
    profit = (sell - buy) * qty
    pct_return = (profit / (buy * qty)) * 100
    return profit, pct_return


def holding_days(buy_date_str, sell_date_str):
    """Return number of days between buy and sell date."""
    try:
        b = datetime.strptime(buy_date_str, '%Y-%m-%d')
        s = datetime.strptime(sell_date_str, '%Y-%m-%d')
        return max(0, (s - b).days)
    except ValueError:
        return 0


def get_all_trades():
    """Return all trades ordered by sell_date DESC as a list of dicts."""
    db = get_db()
    rows = db.execute('SELECT * FROM trades ORDER BY sell_date DESC').fetchall()
    return [dict(row) for row in rows]


def get_summary(trades):
    """Compute summary stats from a list of trade dicts."""
    total_profit = sum(t['profit'] for t in trades if t['profit'] > 0)
    total_loss = sum(t['profit'] for t in trades if t['profit'] < 0)
    win_count = sum(1 for t in trades if t['profit'] > 0)
    loss_count = sum(1 for t in trades if t['profit'] < 0)
    win_loss_ratio = win_count / loss_count if loss_count != 0 else win_count
    return {
        'total_profit': total_profit,
        'total_loss': total_loss,
        'win_count': win_count,
        'loss_count': loss_count,
        'win_loss_ratio': win_loss_ratio,
    }


@app.route('/')
def index():
    trades = get_all_trades()
    summary = get_summary(trades)
    message = request.args.get('message')
    error = request.args.get('error')
    return render_template('index.html', trades=trades, summary=summary, message=message, error=error)


@app.route('/add', methods=['POST'])
def add_trade():
    stock_name    = request.form.get('stock_name', '').strip()
    buy_price_raw = request.form.get('buy_price', '').strip()
    sell_price_raw= request.form.get('sell_price', '').strip()
    quantity_raw  = request.form.get('quantity', '').strip()
    buy_date      = request.form.get('buy_date', '').strip()
    sell_date     = request.form.get('sell_date', '').strip()

    if not all([stock_name, buy_price_raw, sell_price_raw, quantity_raw, buy_date, sell_date]):
        trades = get_all_trades()
        summary = get_summary(trades)
        return render_template('index.html', trades=trades, summary=summary,
                               error='All fields are required.')

    try:
        buy_price  = float(buy_price_raw)
        sell_price = float(sell_price_raw)
        quantity   = float(quantity_raw)
    except ValueError:
        trades = get_all_trades()
        summary = get_summary(trades)
        return render_template('index.html', trades=trades, summary=summary,
                               error='Buy price, sell price, and quantity must be valid numbers.')

    if buy_price <= 0 or sell_price <= 0 or quantity <= 0:
        trades = get_all_trades()
        summary = get_summary(trades)
        return render_template('index.html', trades=trades, summary=summary,
                               error='Buy price, sell price, and quantity must be positive.')

    if sell_date < buy_date:
        trades = get_all_trades()
        summary = get_summary(trades)
        return render_template('index.html', trades=trades, summary=summary,
                               error='Sell date cannot be before buy date.')

    profit, pct_return = calculate_pnl(buy_price, sell_price, quantity)
    days = holding_days(buy_date, sell_date)
    db = get_db()
    db.execute(
        'INSERT INTO trades (stock_name, buy_price, sell_price, quantity, buy_date, sell_date, holding_days, profit, pct_return) '
        'VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)',
        (stock_name, buy_price, sell_price, quantity, buy_date, sell_date, days, profit, pct_return)
    )
    db.commit()
    return redirect(url_for('index', message=f'Trade added. Held for {days} day(s).'))


KNOWN_STOCKS = [
    # Nifty 50
    "RELIANCE","TCS","HDFCBANK","INFY","ICICIBANK","HINDUNILVR","SBIN","BAJFINANCE",
    "BHARTIARTL","KOTAKBANK","LT","AXISBANK","ASIANPAINT","MARUTI","SUNPHARMA",
    "TITAN","ULTRACEMCO","NESTLEIND","WIPRO","POWERGRID","NTPC","ONGC","TATAMOTORS",
    "TATASTEEL","ADANIENT","ADANIPORTS","HCLTECH","TECHM","DRREDDY","CIPLA",
    "DIVISLAB","EICHERMOT","HEROMOTOCO","BAJAJFINSV","BPCL","COALINDIA","GRASIM",
    "INDUSINDBK","IOC","JSWSTEEL","M&M","SBILIFE","SHREECEM","TATACONSUM","UPL",
    "VEDL","BRITANNIA","APOLLOHOSP","HDFCLIFE","BAJAJ-AUTO",
    # Nifty Next 50
    "ADANIGREEN","ADANITRANS","AMBUJACEM","AUROPHARMA","BANDHANBNK","BERGEPAINT",
    "BIOCON","BOSCHLTD","CHOLAFIN","COLPAL","DABUR","DLF","GAIL","GODREJCP",
    "GODREJPROP","HAVELLS","ICICIGI","ICICIPRULI","IGL","INDUSTOWER","IRCTC",
    "JINDALSTEL","JUBLFOOD","LICI","LUPIN","MARICO","MCDOWELL-N","MUTHOOTFIN",
    "NAUKRI","NMDC","PAGEIND","PIDILITIND","PIIND","PNBHOUSING","RECLTD","SAIL",
    "SIEMENS","SRF","TORNTPHARM","TRENT","TVSMOTOR","UNITDSPR","VOLTAS","WHIRLPOOL",
    "ZOMATO","NYKAA","PAYTM","POLICYBZR","DELHIVERY",
    # Banking & Finance
    "PNB","BANKBARODA","CANBK","UNIONBANK","IDFCFIRSTB","FEDERALBNK","RBLBANK",
    "YESBANK","KARURVYSYA","DCBBANK","LAKSHVILAS","SOUTHBANK","TMVFINANCE",
    "EQUITASBNK","UJJIVANSFB","SURYODAY","ESAFSFB","AUBANK","FINOPB","UTKARSHBNK",
    "HDFCAMC","NIPPONLIFE","ABSLAMC","ICICIPRAMC","SBIMF","KOTAKMF","AXISMF",
    "BAJAJHLDNG","BAJAJFIN","MANAPPURAM","IIFL","IIFLWAM","IIFLSEC","ANGELONE",
    "ICICIlombard","NIACL","ORIENTINS","STARHEALTH","GODIGIT","MAXFINSERV",
    "PIRAMALENT","SHRIRAMFIN","MAHINDRAFIN","SUNDARMFIN","LTFH","RECLTD","PFC",
    "IRFC","HUDCO","NABARD","SIDBI","EXIMBANKIND","LICHOUSING","GRUH","CANFINHOME",
    "REPCO","APTUS","AAVAS","HOMEFIRST","CREDITACC","SPANDANA","ARMANFIN",
    # IT & Technology
    "MPHASIS","LTIM","LTTS","PERSISTENT","COFORGE","HEXAWARE","NIIT","KPITTECH",
    "TATAELXSI","ZENSAR","MASTEK","CYIENT","BIRLASOFT","RAMSARUP","SONATSOFTW",
    "INTELLECT","NUCLEUS","TANLA","ROUTE","ONMOBILE","SUBEX","SAKSOFT","DATAMATICS",
    "ECLERX","INFOEDGE","JUSTDIAL","INDIAMART","CARTRADE","EASEMYTRIP","IXIGO",
    "ZOMATO","SWIGGY","BLINKIT","MEESHO","UDAAN","RAZORPAY","ZEPTO","GROWW",
    "POLICYBZR","PAYTM","MOBIKWIK","PHONEPE","GPAY","BHARATPE","CRED","SLICE",
    # Pharma & Healthcare
    "ASTRAZEN","PFIZER","ABBOTINDIA","SANOFI","GLAXO","NOVARTIS","ALKEM","TORNTPHARM",
    "IPCALAB","NATCOPHARM","GRANULES","LAURUSLABS","DIVIS","STRIDES","GLENMARK",
    "WOCKHARDT","AJANTPHARM","JBCHEPHARM","SOLARA","SEQUENT","SUVEN","DRREDDYS",
    "SUNPHARMA","CIPLA","LUPIN","AUROPHARMA","CADILAHC","BIOCON","PIRAMALPH",
    "FORTIS","APOLLOHOSP","MAXHEALTH","NARAYNAHLT","ASTER","METROPOLIS","THYROCARE",
    "LALPATHLAB","KRSNAA","VIJAYADIAG","HEALTHIUM","POLY","NUVOCO","SHALBY",
    # Auto & Auto Ancillaries
    "TATAMOTORS","MARUTI","M&M","BAJAJ-AUTO","HEROMOTOCO","EICHERMOT","TVSMOTOR",
    "ASHOKLEY","FORCEMOT","SMLISUZU","MAHINDCIE","MOTHERSON","BOSCHLTD","EXIDEIND",
    "AMARAJABAT","MINDA","UNOMINDA","SUPRAJIT","ENDURANCE","SUNDRMFAST","GABRIEL",
    "SUBROS","UCALFUEL","SETCO","JAMNA","WHEELS","TIINDIA","CRAFTSMAN","RAMKRISHNA",
    "SCHAEFFLER","SKF","TIMKEN","GREAVESCOT","ESCORTS","SONACOMS","SANSERA",
    "HAPPYFORGE","RAMASTEEL","KALYANKJIL","SHANKARA","NRBBEARING","FAGBEARINGS",
    # FMCG & Consumer
    "HINDUNILVR","NESTLEIND","BRITANNIA","DABUR","MARICO","GODREJCP","COLPAL",
    "EMAMILTD","BAJAJCON","JYOTHYLAB","VENKYS","ZYDUSWELL","TATACONSUM","ITC",
    "VSTIND","GODFRYPHLP","PATANJALI","RUCHI","KRBL","LTFOODS","KOHINOOR","AVANTI",
    "BIKAJI","PRATAAP","DFOODS","TASTYBIT","AGROPHOS","HERITGFOOD","PARAG",
    "PRABHAT","DODLA","HATSUN","AARTI","VADILALIND","CREAMLINE","KWALITY",
    # Metals & Mining
    "TATASTEEL","JSWSTEEL","SAIL","HINDALCO","VEDL","NMDC","COALINDIA","MOIL",
    "NATIONALUM","HINDCOPPER","WELCORP","RATNAMANI","MAHASTEEL","ISMT","SUNFLAG",
    "KALYANI","MIDHANI","MISHRA","TINPLATE","TATAMET","JSPL","BHUSHAN","ELECTCAST",
    "GRAPHITE","HEG","PHILIPCARB","RAIN","DCAL","MAITHANALL","SHYAMMET",
    "APARINDS","APLAPOLLO","HISAR","MANAKSIA","PRAKASH","SARDA","GALLANTT",
    # Energy & Power
    "NTPC","POWERGRID","ADANIGREEN","ADANITRANS","TATAPOWER","CESC","TORNTPOWER",
    "JSWENERGY","GREENKO","RENEW","INOXWIND","SUZLON","RPOWER","NHPC","SJVN",
    "THDC","NEEPCO","KSEB","TANGEDCO","MSEDCL","BSES","TORNTPOWER","GUJRATGAS",
    "IGL","MGL","ATGL","GSPL","GAIL","PETRONET","HINDPETRO","BPCL","IOC","MRPL",
    "CPCL","NRL","HPCL","ONGC","OIL","CAIRN","SELAN","HOEC","GPPL","AEGISCHEM",
    # Infrastructure & Construction
    "LT","DLF","GODREJPROP","OBEROIRLTY","PRESTIGE","BRIGADE","SOBHA","MAHLIFE",
    "KOLTEPATIL","PURAVANKARA","SUNTECK","LODHA","MACROTECH","NCLIND","ARVSMART",
    "NBCC","RITES","IRCON","HGINFRA","KNR","PNCINFRA","SADBHAV","ASHOKA","DILIPBUILDCON",
    "GPPL","ADANIPORTS","CONCOR","GATEWAY","ALLCARGO","MAHLOG","BLUEDART","DELHIVERY",
    "GATI","SAFEXPRESS","DTDC","XPRESSBEES","ECOM","SHADOWFAX","PORTER","DUNZO",
    # Cement
    "ULTRACEMCO","SHREECEM","AMBUJACEM","ACC","DALMIACEM","RAMCOCEM","JKCEMENT",
    "HEIDELBERG","BIRLACORPN","PRISMCEM","NUVOCO","MANGCEM","KESORAMIND","BURNPUR",
    "STARCEMENT","MEGHMANI","ORIENT","DECCAN","SAURASHTRA","KAKATIYA","MALABAR",
    # Chemicals & Fertilizers
    "PIDILITIND","AARTI","DEEPAKNTR","NAVINFLUOR","ALKYLAMINE","BALCHEMLTD",
    "FINEORG","GALAXYSURF","VINATIORG","TATACHEM","GNFC","GSFC","CHAMBAL","COROMANDEL",
    "ZUARI","PARADEEP","IFFCO","KRIBHCO","NFL","RCF","FACT","SPIC","MADRASFERT",
    "BASF","LANXESS","HUNTSMAN","CLARIANT","AKZONOBEL","BERGER","KANSAINER","INDIGO",
    "ASIANPAINT","SHEENLAC","JENSENCOL","SHALPAINTS","SNOWCEM","NIPPONPAINT",
    # Textiles & Apparel
    "PAGEIND","RAYMOND","ARVIND","WELSPUN","TRIDENT","VARDHMAN","NAHARSPG",
    "SPENTEX","ALOKIND","BOMBAY","GRASIM","CENTURY","JKIL","SUTLEJ","NITIN",
    "HIMATSEIDE","RSWM","BANSWARA","DONEAR","SIYARAM","MAFATLAL","BOMBDYEING",
    "KEWAL","CANTABIL","VEDANT","BATA","RELAXO","LIBERTY","MIRZA","LEHAR",
    # Retail & E-commerce
    "DMART","TRENT","SHOPERSTOP","VMART","SPENCERS","FUTURERETAIL","BIGBAZAAR",
    "ZOMATO","SWIGGY","NYKAA","MEESHO","FLIPKART","AMAZON","MYNTRA","AJIO",
    "FIRSTCRY","BABYOYE","HOPSCOTCH","LIMEROAD","JABONG","SNAPDEAL","PAYTMMALL",
    # Media & Entertainment
    "ZEEL","SUNTV","NETWORK18","TV18BRDCST","NDTV","TVTODAY","JAGRAN","DBCORP",
    "HTMEDIA","DISHTV","TATASKY","AIRTELDIGITAL","JIOCINEMA","HOTSTAR","SONYLIV",
    "VOOT","MXPLAYER","ALTBALAJI","EROSNOW","HUNGAMA","GAANA","SAAVN","WYNK",
    # Hospitality & Tourism
    "INDHOTEL","EIHOTEL","TAJGVK","ORIENTHOTEL","MAHINDRAHOLIDAY","THOMASCOOK",
    "COX","SOTC","YATRA","MAKEMYTRIP","CLEARTRIP","IXIGO","EASEMYTRIP","GOIBIBO",
    "OYO","TREEBO","FABHOTELS","ZOSTEL","MERU","OLA","UBER","RAPIDO","BOUNCE",
    # Telecom
    "BHARTIARTL","RJIO","VODAIDEA","BSNL","MTNL","TATACOMM","HFCL","STERLITE",
    "TEJAS","VINDHYATEL","RAILTEL","BBNL","PGCIL","POWERGRID","INDUS","GTLINFRA",
    "BROOKFIELD","AMERICANTOWER","SBACOMM","CROWN","CELLNEX","VANTAGE",
    # Aviation
    "INDIGO","SPICEJET","AIRINDIA","VISTARA","AKASAAIR","STARAIR","BLUEDARAIR",
    "AIRASIAIND","GOAIR","JETAIRWAYS","TRUJET","FLYBIG","ALLIANCE","PAWAN",
    # Shipping & Logistics
    "SCI","ESSAR","GREATSHIP","SEAMEC","VARUN","SHREYAS","TRANSCON","MAHLOG",
    "CONCOR","GATEWAY","ALLCARGO","GATI","SAFEXPRESS","DTDC","BLUEDART","DELHIVERY",
    # Agriculture
    "UPL","BAYER","SYNGENTA","CORTEVA","FMC","RALLIS","DHANUKA","INSECTICIDES",
    "GHCL","COROMANDEL","CHAMBAL","ZUARI","PARADEEP","IFFCO","KRIBHCO","NFL",
    "KAVERI","NUZIVEEDU","MAHYCO","PIONEER","MONSANTO","ADVANTA","ANKUR","BIOSEED",
    # Real Estate
    "DLF","GODREJPROP","OBEROIRLTY","PRESTIGE","BRIGADE","SOBHA","MAHLIFE",
    "KOLTEPATIL","PURAVANKARA","SUNTECK","LODHA","MACROTECH","NCLIND","ARVSMART",
    "PHOENIXLTD","INDIABULLS","UNITECH","PARSVNATH","OMAXE","ANSAL","ELDECO",
    # Diversified Conglomerates
    "RELIANCE","TATAMOTORS","ADANIENT","MAHINDRA","BIRLA","BAJAJ","GODREJ","TATA",
    "HINDUJA","ESSAR","MAFATLAL","WADIA","SHAPOORJI","PIRAMAL","MURUGAPPA","TVS",
    "KIRLOSKAR","THERMAX","CUMMINS","ABB","SIEMENS","BHEL","BEL","HAL","BEML",
    # PSU & Government
    "ONGC","BPCL","IOC","HPCL","GAIL","NTPC","POWERGRID","COALINDIA","SAIL",
    "NMDC","MOIL","NALCO","HINDCOPPER","RECLTD","PFC","IRFC","HUDCO","NBCC",
    "RITES","IRCON","CONCOR","RAILTEL","BBNL","MTNL","BSNL","AIRINDIA","SCI",
    "HAL","BEL","BEML","BHEL","BDL","MIDHANI","GRSE","MDL","GSL","COCHIN",
    # Small & Midcap Popular
    "DIXON","AMBER","VOLTAS","BLUESTAR","WHIRLPOOL","HAVELLS","POLYCAB","FINOLEX",
    "KEIIND","RRKABEL","STERLITETECH","APAR","INOXLEISUR","PVRINOX","CINELINE",
    "UFLEX","HUHTAMAKI","MOLD-TEK","ASTRAL","SUPREME","NILKAMAL","CEAT","MRF",
    "APOLLOTYRE","BALKRISIND","GOODYEAR","FALKENTYRES","TVSSRICHAK","GABRIEL",
    "SUPRAJIT","ENDURANCE","SUNDRMFAST","MINDA","UNOMINDA","MOTHERSON","BOSCHLTD",
    # Indices (for reference)
    "NIFTY50","NIFTY100","NIFTY200","NIFTY500","SENSEX","BANKNIFTY","FINNIFTY",
    "NIFTYMIDCAP","NIFTYSMALLCAP","NIFTYMETAL","NIFTYPHARMA","NIFTYIT","NIFTYFMCG",
    "NIFTYAUTO","NIFTYREALTY","NIFTYENERGY","NIFTYINFRA","NIFTYMEDIA","NIFTYPSE",
]

@app.route('/suggest')
def suggest():
    q = request.args.get('q', '').strip().upper()
    if not q:
        return jsonify([])
    db = get_db()
    rows = db.execute(
        'SELECT DISTINCT stock_name FROM trades WHERE UPPER(stock_name) LIKE ? LIMIT 8',
        (f'{q}%',)
    ).fetchall()
    from_db = [r['stock_name'].upper() for r in rows]
    from_list = [s for s in KNOWN_STOCKS if s.startswith(q) and s not in from_db]
    combined = from_db + from_list
    return jsonify(combined[:8])


@app.route('/edit/<int:trade_id>', methods=['POST'])
def edit_trade(trade_id):
    stock_name     = request.form.get('stock_name', '').strip()
    buy_price_raw  = request.form.get('buy_price', '').strip()
    sell_price_raw = request.form.get('sell_price', '').strip()
    quantity_raw   = request.form.get('quantity', '').strip()
    buy_date       = request.form.get('buy_date', '').strip()
    sell_date      = request.form.get('sell_date', '').strip()

    if not all([stock_name, buy_price_raw, sell_price_raw, quantity_raw, buy_date, sell_date]):
        return redirect(url_for('index', error='All fields are required.'))

    try:
        buy_price  = float(buy_price_raw)
        sell_price = float(sell_price_raw)
        quantity   = float(quantity_raw)
    except ValueError:
        return redirect(url_for('index', error='Invalid numeric values.'))

    if buy_price <= 0 or sell_price <= 0 or quantity <= 0:
        return redirect(url_for('index', error='Prices and quantity must be positive.'))

    if sell_date < buy_date:
        return redirect(url_for('index', error='Sell date cannot be before buy date.'))

    profit, pct_return = calculate_pnl(buy_price, sell_price, quantity)
    days = holding_days(buy_date, sell_date)
    db = get_db()
    db.execute(
        '''UPDATE trades SET stock_name=?, buy_price=?, sell_price=?, quantity=?,
           buy_date=?, sell_date=?, holding_days=?, profit=?, pct_return=? WHERE id=?''',
        (stock_name, buy_price, sell_price, quantity, buy_date, sell_date, days, profit, pct_return, trade_id)
    )
    db.commit()
    return redirect(url_for('index', message='Trade updated successfully.'))


@app.route('/delete/<int:trade_id>', methods=['POST'])
def delete_trade(trade_id):
    db = get_db()
    db.execute('DELETE FROM trades WHERE id = ?', (trade_id,))
    db.commit()
    return redirect(url_for('index'))


@app.route('/ai/insight/<int:trade_id>')
def ai_insight(trade_id):
    """Rule-based AI insight for a single trade."""
    db = get_db()
    row = db.execute('SELECT * FROM trades WHERE id=?', (trade_id,)).fetchone()
    if not row:
        return jsonify({'insight': 'Trade not found.'})
    t = dict(row)
    tips = []

    pct = t['pct_return']
    days = t['holding_days']
    profit = t['profit']
    buy = t['buy_price']
    sell = t['sell_price']

    # Return quality
    if pct >= 20:
        tips.append(f"Excellent trade! {pct:.1f}% return is outstanding.")
    elif pct >= 10:
        tips.append(f"Strong return of {pct:.1f}%. Well executed.")
    elif pct >= 5:
        tips.append(f"Decent return of {pct:.1f}%. Solid trade.")
    elif pct >= 0:
        tips.append(f"Small gain of {pct:.1f}%. Consider if risk was worth it.")
    elif pct >= -5:
        tips.append(f"Small loss of {pct:.1f}%. Manageable, review your entry.")
    elif pct >= -10:
        tips.append(f"Moderate loss of {pct:.1f}%. Consider tighter stop-loss next time.")
    else:
        tips.append(f"Significant loss of {pct:.1f}%. Review your risk management strategy.")

    # Holding period
    if days == 0:
        tips.append("Intraday trade — high risk, ensure you have a clear strategy.")
    elif days <= 3:
        tips.append(f"Short-term trade ({days}d). Good for momentum plays.")
    elif days <= 15:
        tips.append(f"Swing trade ({days}d). Typical for technical setups.")
    elif days <= 90:
        tips.append(f"Medium-term hold ({days}d). Good for trend-following.")
    else:
        tips.append(f"Long-term hold ({days}d). Patience paid off." if profit > 0 else f"Long hold ({days}d) with a loss — review your exit strategy.")

    # Risk/reward
    move_pct = abs((sell - buy) / buy * 100)
    if move_pct < 2 and profit < 0:
        tips.append("Tight price move but still a loss — check brokerage costs.")
    elif move_pct > 15:
        tips.append(f"High volatility trade ({move_pct:.1f}% price move) — size positions carefully.")

    return jsonify({'insight': ' '.join(tips)})


@app.route('/ai/summary')
def ai_summary():
    """Rule-based AI performance summary across all trades."""
    trades = get_all_trades()
    if not trades:
        return jsonify({'summary': 'No trades recorded yet. Start adding trades to get insights.'})

    summary = get_summary(trades)
    tips = []

    total = len(trades)
    wins = summary['win_count']
    losses = summary['loss_count']
    ratio = summary['win_loss_ratio']
    net = summary['total_profit'] + summary['total_loss']

    tips.append(f"You have {total} trade(s) — {wins} profitable, {losses} at a loss.")

    if ratio >= 2:
        tips.append(f"Excellent profit/loss ratio of {ratio:.2f}. You win more than you lose.")
    elif ratio >= 1:
        tips.append(f"Good ratio of {ratio:.2f}. More wins than losses — keep it up.")
    elif losses == 0:
        tips.append("No losing trades yet — great start!")
    else:
        tips.append(f"Ratio of {ratio:.2f} — you're losing more trades than winning. Focus on entry quality.")

    if net > 0:
        tips.append(f"Net P&L is positive at ₹{net:.2f}. You're in profit overall.")
    elif net < 0:
        tips.append(f"Net P&L is negative at ₹{net:.2f}. Review your losing trades.")
    else:
        tips.append("Net P&L is breakeven.")

    # Avg holding days
    avg_days = sum(t['holding_days'] for t in trades) / total
    if avg_days <= 1:
        tips.append("You mostly do intraday trades — manage risk carefully.")
    elif avg_days <= 7:
        tips.append(f"Average holding of {avg_days:.1f} days — you're a swing trader.")
    else:
        tips.append(f"Average holding of {avg_days:.1f} days — positional trading style.")

    # Best and worst trade
    best = max(trades, key=lambda t: t['pct_return'])
    worst = min(trades, key=lambda t: t['pct_return'])
    tips.append(f"Best trade: {best['stock_name']} at +{best['pct_return']:.1f}%. Worst: {worst['stock_name']} at {worst['pct_return']:.1f}%.")

    return jsonify({'summary': ' '.join(tips)})


@app.teardown_appcontext
def close_connection(exception):
    db = getattr(g, '_database', None)
    if db is not None:
        db.close()


if __name__ == '__main__':
    init_db()
    app.run(debug=True)
