import asyncio
import aiohttp

# Top 10 US-listed companies by market capitalization.
SYMBOLS = [
    "AAPL",   # Apple
    "MSFT",   # Microsoft
    "NVDA",   # NVIDIA
    "GOOGL",  # Alphabet
    "AMZN",   # Amazon
    "META",   # Meta Platforms
    "BRK-B",  # Berkshire Hathaway
    "TSLA",   # Tesla
    "AVGO",   # Broadcom
    "LLY",    # Eli Lilly
]

CHART_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
HEADERS = {"User-Agent": "Mozilla/5.0"}


async def fetch_price(session: aiohttp.ClientSession, symbol: str) -> dict:
    """Fetch the latest price for a single symbol."""
    async with session.get(CHART_URL.format(symbol=symbol)) as response:
        response.raise_for_status()
        data = await response.json()
        meta = data["chart"]["result"][0]["meta"]
        return {
            "symbol": symbol,
            "price": meta["regularMarketPrice"],
            "currency": meta["currency"],
        }


async def main() -> None:
    async with aiohttp.ClientSession(headers=HEADERS) as session:
        # Fetch all symbols concurrently.
        quotes = await asyncio.gather(
            *(fetch_price(session, symbol) for symbol in SYMBOLS)
        )

    print(f"{'Symbol':<8}{'Price':>12}  Currency")
    print("-" * 30)
    for quote in quotes:
        print(f"{quote['symbol']:<8}{quote['price']:>12,.2f}  {quote['currency']}")


if __name__ == "__main__":
    asyncio.run(main())
