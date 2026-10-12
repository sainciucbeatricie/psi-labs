# Lab 3: Draw the Dashboard Boundary

## Scope and load targets

The Dashboard lets an authenticated User browse and filter Stocks, read prices and history, and manage a private Watchlist. A Market Data Provider supplies delayed data and can return invalid data, rate limits, or outages.

Load targets from Lab 2 (used to size the design):

| Target | Value from Lab 2 |
|---|---|
| Users (three scales) | 300 / 3,000 / 30,000 |
| Steady read load | 79.2 / 792 / 7,920 RPS |
| Market-open peak (with 10% margin) | 103 / 1,030 / 10,296 RPS |
| Heaviest read (Stock price) | 60 / 600 / 6,000 RPS |
| Latency | p95 of reads under 2 s. A read over 2 s is cut and returns a result clearly marked UNAVAILABLE. |
| Availability | 99.9% in market hours (09:30-16:00, Mon-Fri), 99.5% the rest of the day |
| Price freshness | Up to 15 min: normal. Over 15 min: marked DELAYED. Over 60 min without update: UNAVAILABLE (never 0). |
| Watchlist consistency | Read-your-writes: the same User's next read shows the change immediately |
| Storage | About 5,700 Stocks, about 71.1 MB/day of history, about 17.93 GB per year (252-day retention) |

Design consequences of these targets:
- User reads are served only from our own Database, so read latency does not depend on the Provider. The latest-price set is tiny (about 0.14 MB), so the heaviest read (Stock price) can be answered quickly from the Database.
- The Provider is called only by the Market Data Collector on a schedule, so the number of Users does not change the number of Provider requests.
- The Collector is a separate container, so a Provider failure cannot slow or break the other reads.
- Watchlist reads and writes use the same Database and success is reported only after commit, so read-your-writes holds.

---

## 1. System-context diagram

```mermaid
flowchart LR
    User["User<br/>(authenticated Person)"]
    subgraph Boundary["System boundary"]
        Dashboard["Dashboard<br/>Browse Stocks, read prices and history, manage private Watchlist"]
    end
    Provider["Market Data Provider<br/>(external system, delayed data)"]

    User -->|"Browses and filters Stocks, reads prices and history, manages Watchlist (HTTPS)"| Dashboard
    Dashboard -->|"Requests delayed market data (HTTPS API)"| Provider
    Provider -->|"Returns delayed data, or invalid data, rate limit, outage"| Dashboard
```

**Assumptions**
- Authentication is part of the Dashboard. The User arrives already authenticated, so no separate identity system is drawn.
- Only one external system exists: the Market Data Provider.
- No internal runtime parts are shown on this level.

---

## 2. Container diagram

```mermaid
flowchart LR
    User["User<br/>(authenticated Person)"]
    Provider["Market Data Provider<br/>(external system)"]

    subgraph Boundary["Dashboard system boundary"]
        App["Dashboard Application<br/>Serves the web UI and answers User requests"]
        Collector["Market Data Collector<br/>Fetches, validates and stores Provider data"]
        DB[("Database<br/>Stores Stocks, prices, history, Watchlists")]
    end

    User -->|"Browses, filters, reads prices, manages Watchlist (HTTPS)"| App
    App -->|"Reads Stocks, prices, history and reads or writes Watchlists (SQL)"| DB
    Collector -->|"Writes validated prices and history (SQL)"| DB
    Collector -->|"Requests delayed data with server-side credentials (HTTPS)"| Provider
```

**Responsibilities (one per part)**
- **Dashboard Application**: handles all User requests (identity, input checks, reads, Watchlist changes).
- **Market Data Collector**: runs the sync with the Provider, validates the data, and stores only accepted data.
- **Database**: the single store for Stocks, prices, history, and Watchlists.

**Assumptions**
- This is the smallest set that meets the requirements: separating the Collector from the Application keeps Provider failures away from User reads, and the Database is shared storage between the two.
- The Dashboard Application never calls the Provider. Provider credentials exist only in the Collector configuration on the server.
- The Collector starts syncs from its own schedule.
- No separate cache container is added. The latest-price data is small and the Database serves it. If load tests show p95 above 2 s, a cache is the first change to consider.

---

## 3. Component diagram (Dashboard Application)

```mermaid
flowchart TB
    User["User<br/>(Person)"]

    subgraph DA["Dashboard Application (container)"]
        WI["Web Interface<br/>Receives requests, validates input, renders results"]
        AU["Authentication<br/>Verifies the User identity and session"]
        SB["Stock Browser<br/>Browses and filters Stocks"]
        PR["Price Reader<br/>Reads prices and history, checks data age"]
        WM["Watchlist Manager<br/>Checks permissions and changes the private Watchlist"]
        DAC["Data Access<br/>Reads and writes the Database"]
    end

    DB[("Database<br/>(container)")]

    User -->|"HTTPS requests"| WI
    WI -->|"Verifies session"| AU
    WI -->|"Browse and filter requests"| SB
    WI -->|"Price and history requests"| PR
    WI -->|"Watchlist change requests"| WM
    SB -->|"Reads Stocks"| DAC
    PR -->|"Reads prices and history"| DAC
    WM -->|"Reads and writes Watchlist"| DAC
    DAC -->|"SQL queries and transactions"| DB
```

**Assumptions**
- Only the Dashboard Application is opened. User and Database are the only outside elements that communicate directly with its components.
- The Market Data Collector and the Provider are not shown because they do not communicate directly with the Dashboard Application. The Collector reaches the Application only through data stored in the Database.
- The session is a signed token, so Authentication can verify it without a storage call.

---

## 4. Sequence diagrams

### A. Sync market data

```mermaid
sequenceDiagram
    participant C as Market Data Collector
    participant P as Market Data Provider
    participant D as Database

    Note over C: Sync starts from the Collector schedule
    C->>P: Request delayed prices (API key kept on the server)
    alt Provider timeout or outage
        C->>C: Timeout or 5xx, no usable response
        Note over C,D: Nothing is written. Previously accepted data stays unchanged and readable.
        C->>C: Log the failure and retry at the next scheduled sync
    else Rate limit
        P-->>C: HTTP 429 Too Many Requests
        Note over C,D: Nothing is written. Previously accepted data stays unchanged and readable.
        C->>C: Log the failure and wait before the next sync
    else Response received
        P-->>C: Delayed price batch
        C->>C: Validate batch (known symbols, price above 0, valid timestamp, not older than previous)
        alt Batch invalid
            Note over C,D: The invalid batch is rejected and never stored. Previously accepted data stays unchanged and readable.
            C->>C: Log the rejection
        else Batch valid
            C->>D: Store batch in one transaction (latest prices and history points)
            alt Storage failure
                D-->>C: Write error
                C->>D: Roll back
                Note over C,D: Previously accepted data stays unchanged and readable.
                C->>C: Log the failure and retry at the next scheduled sync
            else Stored
                D-->>C: Commit OK
                Note over C,D: Accepted data becomes available to later reads only after this commit
            end
        end
    end
```

**Assumptions**
- Sync is started by the Collector schedule, not by a User action.
- A batch is accepted or rejected as a whole. A failed or rejected sync never changes previously accepted data, and Users keep reading the last accepted data.
- While syncs keep failing, the kept prices age: after 15 min reads show them as DELAYED, after 60 min without update reads show UNAVAILABLE (never 0).
- Provider credentials stay on the server (Collector configuration). They are never sent to the browser.

### B. Read a Stock price

```mermaid
sequenceDiagram
    actor U as User
    participant W as Web Interface
    participant A as Authentication
    participant R as Price Reader
    participant X as Data Access
    participant D as Database

    U->>W: Request price for a Stock symbol
    W->>A: Verify session
    alt Not authenticated
        A-->>W: Identity rejected
        W-->>U: 401 Sign in required
    else Authenticated
        A-->>W: User identity confirmed
        W->>W: Validate symbol format
        alt Invalid input
            W-->>U: 400 Invalid symbol
        else Valid input
            W->>R: Get latest price for symbol
            R->>X: Read latest price and as-of time
            X->>D: Query stored price
            alt Storage failure or no answer within 2 s
                D-->>X: Error or no answer in time
                X-->>R: Storage error
                R-->>W: Read failed
                W-->>U: 503 Result marked UNAVAILABLE
            else No price stored
                D-->>X: No row found
                X-->>R: Not found
                R-->>W: Price missing
                W-->>U: 404 Price not available
            else Price found
                D-->>X: Price and as-of time
                X-->>R: Price and as-of time
                R->>R: Check data age against the accepted limits (15 min and 60 min)
                alt Age up to 15 min
                    R-->>W: Fresh price
                    W-->>U: 200 Price with as-of time
                else Age over 15 min and up to 60 min
                    R-->>W: Delayed price
                    W-->>U: 200 Last known price marked DELAYED with as-of time
                else Age over 60 min
                    R-->>W: Price too old
                    W-->>U: 200 Result marked UNAVAILABLE, no price value and never 0
                end
            end
        end
    end
    Note over U,D: A User read never calls the Market Data Provider. It reads only stored data.
```

**Assumptions**
- Accepted age limits come from Lab 2: up to 15 min is normal, over 15 min is marked DELAYED, over 60 min without update is UNAVAILABLE (never 0).
- If the read does not finish within 2 s (the Lab 2 latency limit), the request is cut and the User gets a result clearly marked UNAVAILABLE instead of a hanging request.
- A DELAYED price is still shown, clearly marked with its as-of time, so the User is not misled.
- A User read never needs a new Provider request. Only the Market Data Collector talks to the Provider.

### C. Change a private Watchlist

```mermaid
sequenceDiagram
    actor U as User
    participant W as Web Interface
    participant A as Authentication
    participant M as Watchlist Manager
    participant X as Data Access
    participant D as Database

    U->>W: Request to add a Stock to my Watchlist
    W->>A: Verify session
    alt Not authenticated
        A-->>W: Identity rejected
        W-->>U: 401 Sign in required
    else Authenticated
        A-->>W: User identity confirmed
        W->>W: Validate input (symbol format, Stock exists)
        alt Invalid input
            W-->>U: 400 Invalid input, Watchlist unchanged
        else Valid input
            W->>M: Add Stock for the identified User
            M->>M: Permission check (target Watchlist must belong to the identified User)
            alt Unauthorized attempt
                M-->>W: Permission denied
                W-->>U: 403 Forbidden, Watchlist unchanged
            else Permitted
                M->>X: Save change
                X->>D: Write in one transaction
                alt Storage failure
                    D-->>X: Write error
                    X->>D: Roll back
                    X-->>M: Save failed
                    M-->>W: Change failed
                    W-->>U: 503 Not saved, Watchlist unchanged
                else Saved
                    D-->>X: Commit OK
                    Note over X,D: Commit point. Success can be reported only after this.
                    X-->>M: Saved
                    M-->>W: Change done
                    W-->>U: 200 Watchlist updated
                end
            end
        end
    end
    Note over U,D: Read-your-writes. Next read by the same User: after success the Watchlist includes the new Stock. After any rejection or failure it shows the previous Watchlist.
```

**Assumptions**
- The Watchlist owner is taken from the verified session, never from the request body. A User cannot change another User's Watchlist.
- Success is reported only after the Database commit. After a rejected or failed change, the same User's next read shows exactly the Watchlist from before the request.
- Watchlist data is private: it is returned only to its owner.

---

## Checklist

- [x] I included one System Context, one Container, and one Component diagram.
- [x] I included the three required sequence diagrams.
- [x] All six Mermaid blocks render without an error.
- [x] The Component diagram opens only the Dashboard Application.
- [x] My flows show normal results, rejected actions, and failure results.
- [x] The design covers normal reads, private data, provider ingestion, and failures.
