# Valuebet Scanner for European Sportsbooks

This repository contains an automated **valuebet detection bot** for sports betting markets.  
The bot continuously scrapes odds from multiple European bookmakers, normalises them into implied probabilities and flags situations where a single book is offering a **statistically mispriced line** relative to the market consensus. Detected valuebets are pushed to Telegram and logged in Google Sheets.

---

## 1. High-level idea

For each game and market, different bookmakers quote slightly different odds.  
If most books agree on a “fair” price but one book is significantly higher, that line likely has **positive expected value (EV)**.

The bot implements this idea in a systematic way:

1. Pull odds for upcoming and live games from The Odds API.
2. Group prices by:
   - market type: **h2h**, **spreads**, **totals**
   - outcome: team / side / total number
3. Use the **median** of the market as a proxy for the “fair” odds.
4. Look for bookmakers that are offering odds ≥15–20% above that fair level on reasonably liquid outcomes.
5. Send a **Telegram alert** and **log the bet to Google Sheets** whenever such a valuebet is detected.

The goal is not to forecast sports results, but to exploit *relative mispricing* across books.

---

## 2. Data sources & markets

The bot uses:

- **The Odds API** (`https://api.the-odds-api.com/v4/sports/upcoming/odds`)
  - region: `eu`
  - markets: `h2h`, `spreads`, `totals`
- It splits the raw response into:
  - `upcoming` games (pre-match)
  - `live` games (in-play)

Supported markets:

- **H2H** (2 or 3 outcomes: home, away, and optionally draw)
- **Spreads** (handicap lines)
- **Totals** (over/under lines)

Only a subset of books is configured for alerts (e.g. `williamhill`, `betfair_ex_eu`, `winamax_fr`, `sport888`), but **all** books are used to build the consensus.

---

## 3. Modelling odds and probabilities

### 3.1. From odds to implied probabilities

Given decimal odds `o_i` for outcome `i`, the **naive implied probability** is:

- `p_i = 1 / o_i`

The sum of these naive probabilities, `S = sum_i (1 / o_i)`, is greater than 1 due to the **bookmaker margin** (overround).

The helper `normalizar_cuotas` checks the overround:

- Compute `S = sum_i (1 / o_i)`.
- If `1 < S <= 1.15` (reasonable margin), the function rescales the odds to a “normalised” set.  
  These normalised odds are later used to compare books on a common footing.

If the overround is outside this band, the original odds are used to avoid over-correcting ill-formed markets.

### 3.2. Market consensus via median odds

For each outcome (e.g. *Home team*, *Over 2.5*, *+3.5 spread*) the bot:

1. Collects the **normalised odds** quoted by all books.
2. Computes the **median** odds:

   - `omed = median(o_b for o_b in odds_of_all_books)`

   This acts as a robust estimator of the market consensus / fair price.

3. For each bookmaker `b`, it evaluates the relative edge:

   - `edge_b = o_b / omed`

---

## 4. Valuebet definition

A valuebet is triggered when a single bookmaker is **meaningfully above** the consensus price on non-extreme odds.

### 4.1. Pre-match (upcoming)

For upcoming games:

- For each outcome, compute the median normalised odds `omed`.
- For each bookmaker:

  - If  
    `o_b / omed >= 1.15`  
    **and** `omed <= 4.0` (to avoid very long shots),

    then we flag a **valuebet**.

- This rule is applied independently to:
  - **h2h** (2-outcome and 3-outcome markets),
  - **spreads**,
  - **totals**.

The 15% threshold is a heuristic balance between **statistical edge** and **signal frequency**.

### 4.2. Live markets

For live (in-play) games the logic is the same, but the edge threshold is stricter:

- `o_b / omed >= 1.20`

reflecting the higher noise and faster-moving prices in live betting.

(At the moment, live valuebets are printed to console; the Telegram call is left commented out and can be enabled if desired.)

### 4.3. Expected value intuition

For a decimal price `o` and true win probability `q`, the expected value per unit stake is:

- `EV = q * (o - 1) - (1 - q)`

If the “true” fair odds implied by the median are `omed`, then a bookmaker offering `o_b = 1.15 * omed` is effectively assuming a lower win probability than the market consensus. Under mild assumptions, this leads to **EV > 0** if the consensus itself is approximately efficient.

---

## 5. Alerting & logging

### 5.1. Telegram alerts

When a valuebet is detected on an **upcoming** game:

- The bot constructs a message detailing:
  - book,
  - market type (h2h 2/3 outcomes, spread, total),
  - specific selection,
  - raw odds,
  - teams and sport,
  - internal game ID.
- It checks a `sent_messages` set to avoid **duplicate alerts**.
- If the bookmaker is in `casas_avisar`, it sends the message via the Telegram Bot API to a configured `chat_id`.

Example (simplified):

```text
🎯 Valuebet detected
🏠 Book: williamhill
🎫 Market: h2h_2outcomes
🏅 Selection: Home
💰 Odds: 2.30
🗣 Match: Team A vs Team B
🏃‍➡️ Sport: soccer_xxx
🕹 ID: 123456
