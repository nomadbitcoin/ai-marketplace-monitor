"""Console script for ai-marketplace-monitor."""

import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Annotated, List, Optional

import rich
import typer
from rich.logging import RichHandler

from . import __version__
from .utils import CacheType, amm_home, cache, counter, hilight

app = typer.Typer()


def version_callback(value: bool) -> None:
    """Callback function for the --version option.

    Parameters:
        - value: The value provided for the --version option.

    Raises:
        - typer.Exit: Raises an Exit exception if the --version option is provided,
        printing the Awesome CLI version and exiting the program.
    """
    if value:
        typer.echo(f"AI Marketplace Monitor, version {__version__}")
        raise typer.Exit()


@app.command()
def main(
    config_files: Annotated[
        List[Path] | None,
        typer.Option(
            "-r",
            "--config",
            help="Path to one or more configuration files in TOML format. `~/.ai-marketplace-monitor/config.toml will always be read.",
        ),
    ] = None,
    headless: Annotated[
        Optional[bool],
        typer.Option("--headless", help="If set to true, will not show the browser window."),
    ] = False,
    clear_cache: Annotated[
        Optional[str],
        typer.Option(
            "--clear-cache",
            help=(
                "Remove all or selected category of cached items and treat all queries as new. "
                f"""Allowed cache types are {", ".join([x.value for x in CacheType])} and all """
            ),
        ),
    ] = None,
    verbose: Annotated[
        Optional[bool],
        typer.Option("--verbose", "-v", help="If set to true, will show debug messages."),
    ] = False,
    items: Annotated[
        List[str] | None,
        typer.Option(
            "--check",
            help="""Check one or more cached items by their id or URL,
                and list why the item was accepted or denied.""",
        ),
    ] = None,
    for_item: Annotated[
        Optional[str],
        typer.Option(
            "--for",
            help="Item to check for URLs specified --check. You will be prmopted for each URL if unspecified and there are multiple items to search.",
        ),
    ] = None,
    version: Annotated[
        Optional[bool], typer.Option("--version", callback=version_callback, is_eager=True)
    ] = None,
) -> None:
    """Console script for AI Marketplace Monitor."""
    logging.basicConfig(
        level="DEBUG",
        # format="%(name)s %(message)s",
        format="%(message)s",
        handlers=[
            RichHandler(
                markup=True,
                rich_tracebacks=True,
                show_path=False if verbose is None else verbose,
                level="DEBUG" if verbose else "INFO",
            ),
            RotatingFileHandler(
                amm_home / "ai-marketplace-monitor.log",
                encoding="utf-8",
                maxBytes=1024 * 1024,
                backupCount=5,
            ),
        ],
    )

    # remove logging from other packages.
    for logger_name in (
        "asyncio",
        "openai._base_client",
        "httpcore.connection",
        "httpcore.http11",
        "httpx",
    ):
        logging.getLogger(logger_name).setLevel(logging.ERROR)

    logger = logging.getLogger("monitor")
    logger.info(
        f"""{hilight("[VERSION]", "info")} AI Marketplace Monitor, version {hilight(__version__, "name")}"""
    )

    if clear_cache is not None:
        if clear_cache == "all":
            cache.clear()
        elif clear_cache in [x.value for x in CacheType]:
            cache.evict(tag=clear_cache)
        else:
            logger.error(
                f"""{hilight("[Clear Cache]", "fail")} {clear_cache} is not a valid cache type. Allowed cache types are {", ".join([x.value for x in CacheType])} and all """
            )
            sys.exit(1)
        logger.info(f"""{hilight("[Clear Cache]", "succ")} Cache cleared.""")
        sys.exit(0)

    # make --version a bit faster by lazy loading of MarketplaceMonitor
    from .monitor import MarketplaceMonitor

    if items is not None:
        try:
            monitor = MarketplaceMonitor(config_files, headless, logger)
            monitor.check_items(items, for_item)
        except Exception as e:
            logger.error(f"""{hilight("[Check]", "fail")} {e}""")
            raise
        finally:
            monitor.stop_monitor()

        sys.exit(0)

    try:
        monitor = MarketplaceMonitor(config_files, headless, logger)
        monitor.start_monitor()
    except KeyboardInterrupt:
        rich.print("Exiting...")
        sys.exit(0)
    except Exception as e:
        logger.error(f"""{hilight("[Monitor]", "fail")} {e}""")
        raise
        sys.exit(1)
    finally:
        monitor.stop_monitor()
        rich.print(counter)


@app.command()
def export(
    output: Annotated[
        Optional[Path],
        typer.Option(
            "--output",
            "-o",
            help="Output CSV file path. Defaults to exports/nz_cars_YYYYMMDD_HHMMSS.csv",
        ),
    ] = None,
    cities: Annotated[
        List[str] | None,
        typer.Option(
            "--city",
            "-c",
            help="Filter by specific cities (can be specified multiple times)",
        ),
    ] = None,
    max_price: Annotated[
        Optional[float],
        typer.Option("--max-price", help="Filter by maximum price"),
    ] = None,
    require_wof: Annotated[
        bool,
        typer.Option("--require-wof", help="Only export listings with WOF mention"),
    ] = False,
    require_rego: Annotated[
        bool,
        typer.Option("--require-rego", help="Only export listings with Rego mention"),
    ] = False,
) -> None:
    """Export scraped car listings to CSV file.

    Examples:
        aimm export --output cars.csv
        aimm export --require-wof --require-rego --max-price 2000
        aimm export --city Auckland --city Hamilton
    """
    from datetime import datetime

    from .database import DatabaseManager

    # Default output path with timestamp
    if output is None:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output = amm_home() / "exports" / f"nz_cars_{timestamp}.csv"

    # Initialize database manager
    db = DatabaseManager()

    # Get stats before export
    stats = db.get_stats()

    # Export to CSV
    count = db.export_to_csv(
        output_path=output,
        require_wof=require_wof,
        require_rego=require_rego,
        max_price=max_price,
        cities=cities,
    )

    # Print summary
    rich.print(f"\n[bold green]✓[/bold green] Exported {count} listings to {output}")
    rich.print(f"\n[bold]Database Statistics:[/bold]")
    rich.print(f"  Total listings: {stats['total_listings']}")
    rich.print(f"  WOF mentions: {stats['wof_mentions']}")
    rich.print(f"  Rego mentions: {stats['rego_mentions']}")
    rich.print(f"  Both WOF & Rego: {stats['wof_and_rego']}")

    if stats["by_city"]:
        rich.print(f"\n[bold]By City:[/bold]")
        for city, count_city in stats["by_city"].items():
            rich.print(f"  {city}: {count_city}")


if __name__ == "__main__":
    app()  # pragma: no cover
