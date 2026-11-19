
"""Lab 5: API demonstrativ pentru Personal Investment Dashboard."""

from datetime import datetime, timedelta, timezone
from typing import Literal

from fastapi import FastAPI, Depends, Header, HTTPException, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

app = FastAPI(
    title="Personal Investment Dashboard API",
    version="1.0.0",
    description="API demonstrativ cu date locale; fără furnizor sau bază de date reală."
)

NOW = datetime.now(timezone.utc)

# Date demonstrative
STOCKS = [
    {
        "symbol": "AAPL",
        "name": "Apple Inc.",
        "exchange": "NASDAQ",
        "sector": "Technology",
        "active": True,
        "change_percent": 1.2
    },
    {
        "symbol": "MSFT",
        "name": "Microsoft Corporation",
        "exchange": "NASDAQ",
        "sector": "Technology",
        "active": True,
        "change_percent": 0.8
    },
    {
        "symbol": "KO",
        "name": "The Coca-Cola Company",
        "exchange": "NYSE",
        "sector": "Consumer Staples",
        "active": True,
        "change_percent": -0.4
    }
]

PRICES = {
    "AAPL": 185.50,
    "MSFT": 420.25,
    "KO": 62.10
}

WATCHLISTS: dict[str, list[str]] = {}


# Modele de date

class ErrorBody(BaseModel):
    code: str
    message: str


class Stock(BaseModel):
    symbol: str
    name: str
    exchange: str
    sector: str
    active: bool
    changePercent: float


class StockPage(BaseModel):
    items: list[Stock]
    page: int
    pageSize: int
    total: int
    nextPage: int | None


class Price(BaseModel):
    symbol: str
    price: float | None
    currency: str = "USD"
    sourceTime: datetime
    freshness: Literal["normal", "delayed", "unavailable"]


class HistoryPoint(BaseModel):
    sourceTime: datetime
    price: float = Field(gt=0)


class History(BaseModel):
    symbol: str
    items: list[HistoryPoint]


class AddStock(BaseModel):
    symbol: str = Field(
        min_length=1,
        max_length=10,
        pattern=r"^[A-Z]{1,10}$",
        examples=["AAPL"]
    )


class Watchlist(BaseModel):
    symbols: list[str]


ERRORS = {
    400: {"model": ErrorBody},
    401: {"model": ErrorBody},
    404: {"model": ErrorBody},
    409: {"model": ErrorBody},
    429: {"model": ErrorBody},
    503: {"model": ErrorBody}
}


# Tratarea erorilor

def fail(status: int, code: str, message: str):
    raise HTTPException(
        status_code=status,
        detail={"code": code, "message": message}
    )


@app.exception_handler(HTTPException)
async def http_error(_: Request, exc: HTTPException):
    return JSONResponse(
        status_code=exc.status_code,
        content=exc.detail if isinstance(exc.detail, dict)
        else {"code": "http_error", "message": str(exc.detail)}
    )


@app.exception_handler(RequestValidationError)
async def validation_error(_: Request, exc: RequestValidationError):
    return JSONResponse(
        status_code=400,
        content={
            "code": "invalid_input",
            "message": "Parametri sau corp de cerere invalide"
        }
    )


# Autentificare demonstrativa

def current_user(
    authorization: str | None = Header(default=None)
) -> str:
    if authorization != "Bearer demo-token":
        fail(401, "unauthorized", "Token lipsă sau invalid")
    return "demo-user"


def stock_or_404(symbol: str):
    if not (
        1 <= len(symbol) <= 10
        and symbol.isalpha()
        and symbol.isupper()
    ):
        fail(400, "invalid_symbol", "Simbol invalid")

    stock = next(
        (s for s in STOCKS if s["symbol"] == symbol),
        None
    )

    if stock is None:
        fail(404, "not_found", "Acțiunea nu există")

    return stock


def stock_out(s):
    return Stock(
        **{
            **{
                k: v for k, v in s.items()
                if k != "change_percent"
            },
            "changePercent": s["change_percent"]
        }
    )


# Endpoint-uri pentru actiuni

@app.get(
    "/api/v1/stocks",
    response_model=StockPage,
    responses=ERRORS,
    tags=["Market"]
)
def list_stocks(
    page: int = Query(1, ge=1),
    page_size: int = Query(10, alias="pageSize", ge=1, le=50),
    search: str | None = Query(None, max_length=50),
    exchange: Literal["NASDAQ", "NYSE"] | None = None,
    sort: Literal["symbol", "trending"] = "symbol"
):
    result = [
        s for s in STOCKS
        if (
            not search
            or search.lower() in s["symbol"].lower()
            or search.lower() in s["name"].lower()
        )
        and (not exchange or s["exchange"] == exchange)
    ]

    if sort == "trending":
        result.sort(
            key=lambda s: (
                -abs(s["change_percent"]),
                s["symbol"]
            )
        )
    else:
        result.sort(key=lambda s: s["symbol"])

    total = len(result)
    start = (page - 1) * page_size

    return StockPage(
        items=[
            stock_out(s)
            for s in result[start:start + page_size]
        ],
        page=page,
        pageSize=page_size,
        total=total,
        nextPage=page + 1
        if start + page_size < total else None
    )


@app.get(
    "/api/v1/stocks/{symbol}",
    response_model=Stock,
    responses=ERRORS,
    tags=["Market"]
)
def stock_detail(symbol: str):
    return stock_out(stock_or_404(symbol))


@app.get(
    "/api/v1/stocks/{symbol}/price",
    response_model=Price,
    responses=ERRORS,
    tags=["Market"]
)
def stock_price(symbol: str):
    stock_or_404(symbol)

    return Price(
        symbol=symbol,
        price=PRICES[symbol],
        sourceTime=NOW,
        freshness="normal"
    )


@app.get(
    "/api/v1/stocks/{symbol}/history",
    response_model=History,
    responses=ERRORS,
    tags=["Market"]
)
def stock_history(
    symbol: str,
    limit: int = Query(3, ge=1, le=100)
):
    stock_or_404(symbol)

    return History(
        symbol=symbol,
        items=[
            HistoryPoint(
                sourceTime=NOW - timedelta(minutes=i),
                price=round(PRICES[symbol] - i * 0.1, 2)
            )
            for i in range(limit)
        ]
    )


# Endpoint-uri pentru Watchlist

@app.get(
    "/api/v1/watchlist",
    response_model=Watchlist,
    responses=ERRORS,
    tags=["Watchlist"]
)
def read_watchlist(
    user: str = Depends(current_user)
):
    return Watchlist(
        symbols=WATCHLISTS.get(user, []).copy()
    )


@app.post(
    "/api/v1/watchlist",
    response_model=Watchlist,
    status_code=201,
    responses=ERRORS,
    tags=["Watchlist"]
)
def add_to_watchlist(
    body: AddStock,
    user: str = Depends(current_user)
):
    stock_or_404(body.symbol)

    symbols = WATCHLISTS.setdefault(user, [])

    if body.symbol in symbols:
        fail(
            409,
            "already_exists",
            "Acțiunea există deja în Watchlist"
        )

    if len(symbols) >= 20:
        fail(
            400,
            "watchlist_full",
            "Limita de 20 de acțiuni a fost atinsă"
        )

    symbols.append(body.symbol)

    return Watchlist(symbols=symbols.copy())


@app.delete(
    "/api/v1/watchlist/{symbol}",
    status_code=204,
    responses=ERRORS,
    tags=["Watchlist"]
)
def remove_from_watchlist(
    symbol: str,
    user: str = Depends(current_user)
):
    stock_or_404(symbol)

    symbols = WATCHLISTS.get(user, [])

    if symbol not in symbols:
        fail(
            404,
            "not_found",
            "Acțiunea nu se află în Watchlist"
        )

    symbols.remove(symbol)
    return None


# Generarea documentatiei OpenAPI

from fastapi.openapi.utils import get_openapi


def custom_openapi():
    if app.openapi_schema:
        return app.openapi_schema

    schema = get_openapi(
        title=app.title,
        version=app.version,
        description=app.description,
        routes=app.routes
    )

    for path in schema["paths"].values():
        for operation in path.values():
            if isinstance(operation, dict) and "responses" in operation:
                operation["responses"].pop("422", None)

    app.openapi_schema = schema
    return schema


app.openapi = custom_openapi
