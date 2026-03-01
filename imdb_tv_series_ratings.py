#!/usr/bin/env python3
# pylint: disable=import-error,too-many-locals,too-many-branches
# pylint: disable=too-many-statements,logging-fstring-interpolation
# pyright: ignore[reportUnknownMemberType,reportUnknownArgumentType]
# pyright: ignore[reportUnknownVariableType,reportUnknownParameterType]

"""Fetch and display IMDb ratings for TV series episodes organized by season.

This script retrieves IMDb episode ratings for multiple TV series and displays
them in a tabular format organized by season. Supports both sequential and
parallel processing modes with automatic retry logic for handling HTTP 503
errors.

Features:
    - Sequential (default) or parallel processing with ThreadPoolExecutor
    - Exponential backoff retry logic for 503 Service Unavailable errors
    - Color-coded ratings (green >= 8.0, yellow >= 6.5, blue >= 5.0, red < 5.0)
    - Tabulated output showing all episodes by season
    - Debug logging for troubleshooting
    - Processes 24+ TV series including classics and modern shows

Usage:
    python imdb_tv_series_ratings.py [--debug] [--max-workers N]

Examples:
    python imdb_tv_series_ratings.py              # All shows, sequential
    python imdb_tv_series_ratings.py --show Dexter  # Only Dexter
    python imdb_tv_series_ratings.py --show "Doctor Who"  # Both
    python imdb_tv_series_ratings.py --show Archer Daria  # Multiple
    python imdb_tv_series_ratings.py --list-shows  # List available shows
    python imdb_tv_series_ratings.py --max-workers 5  # Parallel mode
    python imdb_tv_series_ratings.py --debug  # With debug logging

Dependencies:
    pip3 install Cinemagoer termcolor tabulate
"""

# pip3 install Cinemagoer termcolor tabulate
import argparse
import logging
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from operator import itemgetter
from typing import Callable, Any

from tabulate import tabulate
from termcolor import colored
from imdb import Cinemagoer  # type: ignore
from imdb.Movie import Movie  # type: ignore
from imdb._exceptions import IMDbDataAccessError  # type: ignore


def is_503_error(error: Exception) -> bool:
    """Check if an exception is a 503 Service Unavailable error from IMDb.

    Inspects an IMDbDataAccessError to determine if the underlying HTTP
    error is a 503 (Service Unavailable), which typically indicates rate
    limiting or temporary service unavailability.

    Args:
        error: Exception to check (typically IMDbDataAccessError)

    Returns:
        True if it's a 503 error, False otherwise
    """
    if isinstance(error, IMDbDataAccessError):
        # type: ignore[assignment, call-overload, arg-type, no-any-return]
        error_dict = error.args[0] if error.args else {}
        if isinstance(error_dict, dict):
            original_exc = error_dict.get('original exception')
            if original_exc and hasattr(original_exc, 'code'):
                return original_exc.code == 503
    return False


def retry_with_backoff(
    func: Callable[..., Any],
    *args: Any,
    max_retries: int = 10,
    **kwargs: Any
) -> Any:
    """Retry a function with exponential backoff on 503 errors.

    Implements exponential backoff starting at 10 seconds and doubling on
    each retry, capped at 15 minutes (900 seconds). Only retries on HTTP
    503 errors; other exceptions are raised immediately. Logs warnings on
    each retry attempt to help users diagnose rate limiting issues.

    Backoff sequence: 10s, 20s, 40s, 80s, 160s, 320s, 640s, 900s (max)

    Args:
        func: Function to call (typically an IMDb API method)
        *args: Positional arguments for func
        max_retries: Maximum number of retry attempts (default: 10)
        **kwargs: Keyword arguments for func

    Returns:
        Result of func call

    Raises:
        Exception: Re-raises the last exception if all retries exhausted,
                   or immediately if not a 503 error
    """
    backoff_seconds = 10  # Start at 10 seconds
    max_backoff = 900  # Cap at 15 minutes

    for attempt in range(max_retries):
        try:
            return func(*args, **kwargs)
        # pylint: disable=broad-exception-caught
        except Exception as e:
            if is_503_error(e):
                if attempt < max_retries - 1:
                    wait_time = min(
                        backoff_seconds * (2 ** attempt), max_backoff
                    )
                    logging.warning(
                        f"503 error encountered "
                        f"(attempt {attempt + 1}/{max_retries}). "
                        f"Backing off for {wait_time}s. "
                        f"Consider reducing --max-workers to avoid "
                        f"rate limiting."
                    )
                    time.sleep(wait_time)
                else:
                    logging.error(
                        f"Max retries ({max_retries}) exceeded for 503 errors"
                    )
                    raise
            else:
                # Not a 503 error, re-raise immediately
                raise

    # Should not reach here, but just in case
    # pylint: disable=broad-exception-raised
    raise Exception("Unexpected retry loop exit")


def parse_arguments() -> argparse.Namespace:
    """Parse command line arguments.

    Returns:
        Namespace with parsed arguments:
            - debug: bool, enable debug logging
            - max_workers: int or None, number of parallel workers
            - show: list of str or None, series names to filter
            - list_shows: bool, list available shows and exit
    """
    parser: argparse.ArgumentParser = argparse.ArgumentParser(
        description='Get IMDb ratings for TV series episodes'
    )
    parser.add_argument(
        '--debug',
        action='store_true',
        help='Enable debug output'
    )
    parser.add_argument(
        '--max-workers',
        type=int,
        default=None,
        help='Enable parallel processing with N workers (default: sequential)'
    )
    parser.add_argument(
        '--show',
        nargs='+',
        metavar='PATTERN',
        help='Filter to specific show(s) by name '
             '(case-insensitive partial match)'
    )
    parser.add_argument(
        '--list-shows',
        action='store_true',
        help='List all available shows and exit'
    )
    return parser.parse_args()


def process_series(
    ia: Cinemagoer,  # type: ignore[valid-type]
    series_id: dict[str, str]
) -> tuple[str, dict[str, list[str]]]:
    """Process a single TV series and return episode ratings by season.

    Worker function for both sequential and parallel processing. Fetches
    series data, retrieves all episodes across all seasons, extracts ratings,
    and applies color coding. Uses retry_with_backoff to handle 503 errors
    automatically on all API calls.

    Ratings are marked with special indicators:
        ** = highest rated episode in the entire show
        -- = lowest rated episode in the entire show
        *  = highest rated episode in the season
        -  = lowest rated episode in the season
    Note: Show-level markers (** and --) take precedence over season markers

    Args:
        ia: Cinemagoer instance for API access
        series_id: Dictionary with 'id' (IMDb ID) and 'name' (series title)

    Returns:
        Tuple of (series_title, season_data_dict) where season_data_dict
        maps season numbers to lists of color-coded rating strings with markers

    Note:
        Episodes without ratings default to "0.00" and log warnings
    """
    logging.debug(f"Fetching series: {series_id['name']}")
    # Fetch series data with automatic retry on 503 errors
    # type: ignore[arg-type]
    series: Movie = retry_with_backoff(ia.get_movie, series_id['id'])

    # Update with episodes data (also with retry protection)
    retry_with_backoff(ia.update, series, 'episodes')  # type: ignore[arg-type]
    # Note: 'episodes rating' infoset not needed for individual episode ratings

    # First pass: collect all ratings to find global and season-level extremes
    season_ratings: dict[int, list[tuple[int, float | None]]] = {}
    all_ratings: list[float] = []

    # type: ignore[attr-defined]
    for season in sorted(series['episodes'].keys()):
        logging.debug(
            f"Processing season {season} of {series['title']}"
        )
        logging.debug(
            f"Episodes in season {season}: "
            # type: ignore[attr-defined]
            f"{list(series['episodes'][season].keys())}"
        )
        season_ratings[season] = []

        # type: ignore[attr-defined]
        for episode in series['episodes'][season].keys():
            logging.debug(f"Processing S{season:02}E{episode:02}")
            try:
                # type: ignore[assignment, index, arg-type]
                episode_data = series['episodes'][season][episode]
                # Fetch episode details with retry protection
                # type: ignore[arg-type]
                retry_with_backoff(ia.update, episode_data, 'main')
                # type: ignore[attr-defined]
                logging.debug(f"Episode data keys: {episode_data.keys()}")
                # type: ignore[assignment, index]
                rating_value: float = episode_data['rating']
                # type: ignore[assignment, index]
                title: str = episode_data['title']
                logging.debug(
                    f"S{season:02}E{episode:02} - {title}: {rating_value:.2f}"
                )
                season_ratings[season].append(
                    (episode, rating_value)  # type: ignore[arg-type]
                )
                all_ratings.append(rating_value)
            except KeyError as e:
                logging.warning(
                    f"KeyError for S{season:02}E{episode:02}: {e}"
                )
                episode_data_str = (
                    str(episode_data)  # type: ignore[arg-type]
                    if 'episode_data' in locals()
                    else 'not found'
                )
                logging.debug(f"Episode data: {episode_data_str}")
                # Store None for missing ratings
                season_ratings[season].append(
                    (episode, None)  # type: ignore[arg-type]
                )

    # Calculate global max/min across entire show
    global_max: float | None = max(all_ratings) if all_ratings else None
    global_min: float | None = min(all_ratings) if all_ratings else None

    # Calculate season max/min for each season
    season_max: dict[int, float] = {}
    season_min: dict[int, float] = {}
    for season, episodes in season_ratings.items():
        valid_ratings: list[float] = [r for _, r in episodes if r is not None]
        if valid_ratings:
            season_max[season] = max(valid_ratings)
            season_min[season] = min(valid_ratings)

    # Second pass: format ratings with color coding and markers
    data: dict[str, list[str]] = {}

    # type: ignore[attr-defined]
    for season in sorted(series['episodes'].keys()):
        ratings_strs: list[str] = []

        # type: ignore[assignment]
        for episode, rating_value in season_ratings[season]:
            if rating_value is None:  # type: ignore[comparison-overlap]
                # Missing rating - pad to match width of ratings with markers
                # and apply red color (0.00 < 5.0)
                ratings_strs.append(colored("0.00  ", 'red'))
                continue

            # Format rating to 2 decimal places
            rating: str = f"{rating_value:.2f}"

            # Add markers: show-level markers take precedence over season-level
            marker: str = ""
            if global_max is not None and rating_value == global_max:
                marker = "**"
            elif global_min is not None and rating_value == global_min:
                marker = "--"
            elif season in season_max and rating_value == season_max[season]:
                marker = "*"
            elif season in season_min and rating_value == season_min[season]:
                marker = "-"

            # Pad marker to 2 characters and add to rating BEFORE coloring
            marker_padded: str = f"{marker:<2}"
            rating_with_marker: str = rating + marker_padded

            # Apply color coding based on rating thresholds
            rating_str: str
            if rating_value >= 8.0:
                rating_str = colored(rating_with_marker, 'green')
            elif rating_value >= 6.5:
                rating_str = colored(rating_with_marker, 'yellow')
            elif rating_value >= 5.0:
                rating_str = colored(rating_with_marker, 'blue')
            else:
                rating_str = colored(rating_with_marker, 'red')

            ratings_strs.append(rating_str)
            logging.debug(
                f"Added rating for S{season:02}E{episode:02}: "
                f"{rating}{marker}"
            )

        logging.debug(
            f"Ratings for season {season}: {len(ratings_strs)} episodes found"
        )
        season_str: str = f"{season:2d}"
        data.update({season_str: ratings_strs})

    logging.debug(f"Season data: {data}")
    return (series['title'], data)  # type: ignore[return-value]


def main() -> None:
    """Main function to fetch and display TV series ratings from IMDb.

    Orchestrates the entire process:
    1. Parse command line arguments
    2. Configure logging based on debug flag
    3. Initialize Cinemagoer client
    4. Fetch episode ratings for all series (sequential or parallel)
    5. Display results in tabular format with color-coded ratings

    Sequential mode processes series one at a time (default). Parallel mode
    uses ThreadPoolExecutor when --max-workers is specified. All API calls
    use retry logic to handle transient 503 errors.
    """
    args: argparse.Namespace = parse_arguments()

    # Configure logging
    log_level: int = logging.DEBUG if args.debug else logging.INFO
    logging.basicConfig(
        level=log_level,
        format='%(asctime)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

    logging.info("Starting TV series ratings fetcher")

    # Create Cinemagoer instance for IMDb API access
    ia: Cinemagoer = Cinemagoer()  # type: ignore[valid-type]

    series_list: list[dict[str, str]] = [
        {'id': '0118401', 'name': 'Midsomer Murders'},
        {'id': '0096697', 'name': 'The Simpsons'},
        {'id': '1466074', 'name': 'Columbo'},
        {'id': '0098904', 'name': 'Seinfeld'},
        {'id': '0898266', 'name': 'The Big Bang Theory'},
        {'id': '0436992', 'name': 'Doctor Who (2005)'},
        {'id': '1486217', 'name': 'Archer'},
        {'id': '0103359', 'name': 'Batman: The Animated Series'},
        {'id': '2215842', 'name': 'Father Brown'},
        {'id': '0098837', 'name': 'Keeping Up Appearances'},
        {'id': '0094525', 'name': 'Poirot'},
        {'id': '0084967', 'name': 'The A-Team'},
        {'id': '0086662', 'name': 'Airwolf'},
        {'id': '0086659', 'name': 'Allo Allo'},
        {'id': '0407362', 'name': 'Battlestar Galactica (2003)'},
        {'id': '1561755', 'name': 'Bob\'s Burgers'},
        {'id': '0810788', 'name': 'Burn Notice'},
        {'id': '0247082', 'name': 'CSI: Crime Scene Investigation'},
        {'id': '0118298', 'name': 'Daria'},
        {'id': '0773262', 'name': 'Dexter'},
        {'id': '0056751', 'name': 'Doctor Who (1963)'},
        {'id': '0106179', 'name': 'The X-Files'},
        {'id': '0141842', 'name': 'The Sopranos'},
        {'id': '0068098', 'name': 'M*A*S*H'},
        {'id': "0086659", 'name': '\'Allo \'Allo'}
    ]

    # Handle --list-shows option
    if args.list_shows:
        print("Available TV series:")
        for series in sorted(series_list, key=itemgetter('name')):
            print(f"  - {series['name']}")
        sys.exit(0)

    # Filter series list based on --show argument
    if args.show:
        filtered_list: list[dict[str, str]] = []
        for pattern in args.show:
            pattern_lower: str = pattern.lower()
            matches: list[dict[str, str]] = [
                s for s in series_list
                if pattern_lower in s['name'].lower()
            ]
            if matches:
                filtered_list.extend(matches)
                logging.info(
                    f"Pattern '{pattern}' matched: "
                    f"{', '.join(s['name'] for s in matches)}"
                )
            else:
                logging.warning(f"No shows matched pattern: '{pattern}'")

        # Remove duplicates while preserving order
        seen: set[str] = set()
        series_list = [
            s for s in filtered_list
            if s['id'] not in seen and not seen.add(s['id'])
        ]

        if not series_list:
            logging.error(
                "No shows matched your criteria. "
                "Use --list-shows to see available shows."
            )
            sys.exit(1)

        show_names = ', '.join(
            s['name'] for s in sorted(series_list, key=itemgetter('name'))
        )
        logging.info(
            f"Processing {len(series_list)} selected show(s): {show_names}"
        )

    # Fetch ratings: sequential by default, parallel if --max-workers specified
    # Sort by series name
    if args.max_workers is None:
        # Sequential mode: process one series at a time (no threading overhead)
        logging.info(
            f"Fetching ratings for {len(series_list)} TV series "
            f"(sequential mode)"
        )
        for series_id in sorted(series_list, key=itemgetter('name')):
            series_title: str
            season_data: dict[str, list[str]]
            series_title, season_data = process_series(
                ia, series_id  # type: ignore[arg-type]
            )

            print("------\n")
            print(f"Ratings information for {series_title}\n")
            print(
                "\tgreen >= 8.0\n\tyellow >= 6.5\n\t"
                "blue >=5.0\n\tred < 5.0\n"
                "\t** = show best, -- = show worst\n"
                "\t* = season best, - = season worst\n"
            )
            print(tabulate(
                season_data, headers="keys", tablefmt="pretty"
            ))
            logging.debug(f"Successfully processed: {series_title}")
    else:
        # Parallel mode: use ThreadPoolExecutor for I/O-bound concurrency
        logging.info(
            f"Fetching ratings for {len(series_list)} TV series "
            f"using {args.max_workers} parallel workers"
        )

        with ThreadPoolExecutor(max_workers=args.max_workers) as executor:
            futures = {
                executor.submit(
                    process_series, ia, series_id  # type: ignore[arg-type]
                ): series_id for series_id in sorted(
                    series_list, key=itemgetter('name')
                )
            }

            for future in as_completed(futures):
                try:
                    series_title: str
                    season_data: dict[str, list[str]]
                    series_title, season_data = future.result()

                    print("------\n")
                    print(f"Ratings information for {series_title}\n")
                    print(
                        "\tgreen >= 8.0\n\tyellow >= 6.5\n\t"
                        "blue >=5.0\n\tred < 5.0\n"
                        "\t** = show best, -- = show worst\n"
                        "\t* = season best, - = season worst\n"
                    )
                    print(tabulate(
                        season_data, headers="keys", tablefmt="pretty"
                    ))
                    logging.debug(f"Successfully processed: {series_title}")
                # pylint: disable=broad-exception-caught
                except Exception as e:
                    series_id = futures[future]
                    logging.error(
                        f"Error processing {series_id['name']}: {e}"
                    )

    logging.info(f"Processed {len(series_list)} TV series")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nInterrupted by user. Exiting...")
        sys.exit(0)
