# Versflip Plinko

A Flask-powered Versflip experience with a pink and purple visual theme. The homepage focuses on a single Plinko board that pays out in the F$ currency. Users can register or log in (including with a `.ROBLOSECURITY` cookie) to keep their F$ balance tied to an account.

## Getting started
1. Create and activate a virtual environment (recommended).
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
3. Run the development server:
   ```bash
   python app.py
   ```
4. Open http://localhost:5000 to view and play Plinko.

### Accounts and database
- A SQLite database (`versflip.db` by default) is created automatically on first request.
- Use the homepage forms to register (starts with 1,000 F$) or log in with either username/password or a `.ROBLOSECURITY` cookie; balances persist per account.
- Roblox players can sign in with their `.ROBLOSECURITY` cookie; the value is hashed server-side, linked to their account for future logins, and surfaces their Roblox username and profile link in the UI.
- Set `VERSFLIP_DB=/custom/path.db` to control where the database is stored.

## Gameplay
- **Balance:** Each account starts with 1000 F$ that update after every play. Guests receive a temporary session balance.
- **Plinko:** Choose a risk lane (safe, balanced, or risky) and place a bet. The server simulates eight peg rows and lands in one of nine slots using the lane’s multipliers to compute your payout.

## Design notes
- Gradient pink and purple palette across buttons, cards, and charts.
- Versflip logo badge built from text for an easily brandable header.
- Responsive grid layout for the hero section, chart preview, and featured game cards.
