#!/usr/bin/env python3
"""Fetch and display IMDb ratings for Marvel Cinematic Universe films.

This script retrieves IMDb ratings for all MCU films and displays them
sorted by rating with color coding. Supports both sequential and parallel
processing modes, with automatic retry logic for handling HTTP 503 errors.

Features:
    - Sequential (default) or parallel processing with ThreadPoolExecutor
    - Exponential backoff retry logic for 503 Service Unavailable errors
    - Color-coded output (green >= 8.0, yellow >= 6.5, blue >= 5.0, red < 5.0)
    - Debug logging for troubleshooting
    - Title validation against expected values

Usage:
    python imdb_mcu_ratings.py [--debug] [--max-workers N]

Examples:
    python imdb_mcu_ratings.py                    # Sequential mode
    python imdb_mcu_ratings.py --max-workers 5    # Parallel with 5 workers
    python imdb_mcu_ratings.py --debug            # With debug logging
"""

import sys
import argparse
import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

# Check if running in a virtual environment
if not (sys.prefix != sys.base_prefix):
    print("Warning: Not running in a virtual environment!")
    print("Please activate the venv first: source .venv/bin/activate")
    sys.exit(1)

from imdb import Cinemagoer  # type: ignore
from imdb.Movie import Movie  # type: ignore
from imdb._exceptions import IMDbDataAccessError  # type: ignore
# from tabulate import tabulate
from termcolor import colored
from typing import Callable, Any


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
        error_dict: dict[str, Any] = error.args[0] if error.args else {}
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
        except Exception as e:
            if is_503_error(e):
                if attempt < max_retries - 1:
                    wait_time: int = min(
                        backoff_seconds * (2 ** attempt), max_backoff
                    )
                    logging.warning(
                        f"503 error encountered "
                        f"(attempt {attempt + 1}/{max_retries}). "
                        f"Backing off for {wait_time}s. Consider "
                        f"reducing --max-workers to avoid rate limiting."
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
    raise Exception("Unexpected retry loop exit")


def parse_arguments() -> argparse.Namespace:
    """Parse command line arguments.

    Returns:
        Namespace with parsed arguments:
            - debug: bool, enable debug logging
            - max_workers: int or None, number of parallel workers
    """
    parser: argparse.ArgumentParser = argparse.ArgumentParser(
        description='Get IMDb ratings for Marvel Cinematic Universe films'
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
    return parser.parse_args()


def fetch_movie_rating(
    ia: "Cinemagoer", movie_id: dict[str, str]  # type: ignore
) -> tuple[str, float]:
    """Fetch rating for a single movie with retry logic.

    Worker function for parallel processing. Retrieves movie data from IMDb,
    validates the title matches expected value, and extracts the rating.
    Uses retry_with_backoff to handle 503 errors automatically.

    Args:
        ia: Cinemagoer instance for API access
        movie_id: Dictionary with 'id' (IMDb ID) and 'name' (expected title)

    Returns:
        Tuple of (title, rating) where rating is 0.0 if unavailable

    Note:
        Logs warnings if title mismatch or missing rating detected
    """
    logging.debug(f"Fetching movie ID: {movie_id['id']}")
    movie: Movie = retry_with_backoff(
        ia.get_movie, movie_id['id']  # type: ignore
    )
    _ = movie.infoset2keys  # type: ignore

    imdb_title: str = movie.get('title', 'Unknown')  # type: ignore[assignment]
    year_value: int | None = movie.get('year', 0)  # type: ignore[assignment]
    imdb_year: int = (
        int(year_value) if year_value else 0  # type: ignore[arg-type]
    )
    imdb_title_with_year: str = f"{imdb_title} ({imdb_year})"
    expected_title: str = movie_id['name']
    logging.debug(
        f"Title comparison - IMDb: '{imdb_title_with_year}' | "
        f"Expected: '{expected_title}'"
    )
    if imdb_title_with_year.lower() != expected_title.lower():
        logging.warning(
            f"Title mismatch for ID {movie_id['id']}: "
            f"'{imdb_title_with_year}' != '{expected_title}'"
        )

    try:
        rating: float = movie.get('rating')
    except KeyError:
        rating = 0.0
        logging.warning(f"No rating found for {movie_id['name']}")

    title: str = movie['title']
    logging.debug(f"Rating for {title}: {rating}")
    return (title, rating)


def main() -> None:
    """Main function to fetch and display MCU movie ratings from IMDb.

    Orchestrates the entire process:
    1. Parse command line arguments
    2. Configure logging based on debug flag
    3. Initialize Cinemagoer client
    4. Fetch ratings (sequential or parallel based on --max-workers)
    5. Sort by rating and display with color coding

    The function exits early with helpful message if not in a virtual
    environment. Uses retry logic to handle transient 503 errors.
    """
    args: argparse.Namespace = parse_arguments()

    # Configure logging
    log_level: int = logging.DEBUG if args.debug else logging.INFO
    logging.basicConfig(
        level=log_level,
        format='%(asctime)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

    logging.info("Starting MCU ratings fetcher")

    # Create Cinemagoer instance for IMDb API access
    ia: Cinemagoer = Cinemagoer()

    mcu_list: list[dict[str, str]] = [
        {'id': '0371746', 'name': 'Iron Man (2008)'},
        {'id': '0800080', 'name': 'The Incredible Hulk (2008)'},
        {'id': '1228705', 'name': 'Iron Man 2 (2010)'},
        {'id': '0800369', 'name': 'Thor (2011)'},
        {'id': '0458339', 'name': 'Captain America: The First Avenger (2011)'},
        {'id': '0848228', 'name': 'The Avengers (2012)'},
        {'id': '1300854', 'name': 'Iron Man 3 (2013)'},
        {'id': '1981115', 'name': 'Thor: The Dark World (2013)'},
        {'id': '1843866', 'name': 'Captain America: The Winter Soldier (2014)'},
        {'id': '2015381', 'name': 'Guardians of the Galaxy (2014)'},
        {'id': '2395427', 'name': 'Avengers: Age of Ultron (2015)'},
        {'id': '0478970', 'name': 'Ant-Man (2015)'},
        {'id': '3498820', 'name': 'Captain America: Civil War (2016)'},
        {'id': '1211837', 'name': 'Doctor Strange (2016)'},
        {'id': '3896198', 'name': 'Guardians of the Galaxy Vol. 2 (2017)'},
        {'id': '2250912', 'name': 'Spider-Man: Homecoming (2017)'},
        {'id': '3501632', 'name': 'Thor: Ragnarok (2017)'},
        {'id': '1825683', 'name': 'Black Panther (2018)'},
        {'id': '4154756', 'name': 'Avengers: Infinity War (2018)'},
        {'id': '5095030', 'name': 'Ant-Man and the Wasp (2018)'},
        {'id': '4154664', 'name': 'Captain Marvel (2019)'},
        {'id': '4154796', 'name': 'Avengers: Endgame (2019)'},
        {'id': '6320628', 'name': 'Spider-Man: Far From Home (2019)'},
        {'id': '3480822', 'name': 'Black Widow (2021)'},
        {
            'id': '9376612',
            'name': 'Shang-Chi and the Legend Of The Ten Rings (2021)'
        },
        {'id': '9032400', 'name': 'Eternals (2021)'},
        {'id': '10872600', 'name': 'Spider-Man: No Way Home (2021)'},
        {
            'id': '9419884',
            'name': 'Doctor Strange in the Multiverse Of Madness (2022)'
        },
        {'id': '10648342', 'name': 'Thor: Love and Thunder (2022)'},
        {'id': '9114286', 'name': 'Black Panther: Wakanda Forever (2022)'},
        {'id': '10954600', 'name': 'Ant-Man and the Wasp: Quantumania (2023)'},
        {'id': '6791350', 'name': 'Guardians of the Galaxy Vol. 3 (2023)'},
        {'id': '10676048', 'name': 'The Marvels (2023)'},
        {'id': '6263850', 'name': 'Deadpool & Wolverine (2024)'},
        {'id': '14513804', 'name': 'Captain America: Brave New World (2025)'},
        {'id': '10676052', 'name': 'The Fantastic Four: First Steps (2025)'},
        {'id': '20969586', 'name': 'Thunderbolts* (2025)'},
    ]

    data: dict[str, float] = {}

    # Fetch ratings: sequential by default, parallel if --max-workers specified
    if args.max_workers is None:
        # Sequential mode: process one movie at a time (no threading overhead)
        logging.info("Fetching ratings (sequential mode)")
        for movie_id in mcu_list:
            logging.debug(f"Fetching movie ID: {movie_id['id']}")
            # Fetch movie data with automatic retry on 503 errors
            movie: Movie = retry_with_backoff(ia.get_movie, movie_id['id'])  # type: ignore
            _ = movie.infoset2keys  # type: ignore  # Ensure all data sets are loaded

            # Validate title matches expected value
            imdb_title: str = movie.get('title', 'Unknown')
            year_value: int | None = movie.get('year', 0)  # type: ignore[assignment]
            imdb_year: int = int(year_value) if year_value else 0  # type: ignore[arg-type]
            imdb_title_with_year: str = f"{imdb_title} ({imdb_year})"
            expected_title: str = movie_id['name']
            logging.debug(
                f"Title comparison - IMDb: '{imdb_title_with_year}' | "
                f"Expected: '{expected_title}'"
            )
            if imdb_title_with_year != expected_title:
                logging.warning(
                    f"Title mismatch for ID {movie_id['id']}: "
                    f"'{imdb_title_with_year}' != '{expected_title}'"
                )

            # Extract rating, default to 0.0 if not available
            try:
                rating: float = movie.get('rating')
            except KeyError:
                rating = 0.0
                logging.warning(f"No rating found for {movie_id['name']}")
            title: str = movie['title']
            logging.debug(f"Rating for {title}: {rating}")
            data.update({title: rating})
    else:
        # Parallel mode: use ThreadPoolExecutor for I/O-bound concurrency
        logging.info(
            f"Fetching ratings using {args.max_workers} parallel workers"
        )
        with ThreadPoolExecutor(max_workers=args.max_workers) as executor:
            futures = {
                executor.submit(
                    fetch_movie_rating, ia, movie_id
                ): movie_id for movie_id in mcu_list
            }

            for future in as_completed(futures):
                try:
                    title: str
                    rating: float
                    title, rating = future.result()
                    data[title] = rating
                    logging.debug(f"Successfully retrieved: {title}")
                except Exception as e:
                    movie_id = futures[future]
                    logging.error(
                        f"Error fetching {movie_id['name']}: {e}"
                    )

    logging.debug(f"All ratings data: {data}")

    sorted_by_rating: list[str] = sorted(data, key=data.get, reverse=True)

    logging.debug(f"Sorted titles: {sorted_by_rating}")
    logging.info(f"Successfully fetched ratings for {len(data)} movies")

    print("Marvel Cinematic Universe films sorted by IMDB user rating")
    print("\tgreen >= 8.0\n\tyellow >= 6.5\n\tblue >=5.0\n\tred < 5.0\n")
    max_title_len: int = len(max(sorted_by_rating, key=len))
    for title in sorted_by_rating:
        rating_value: float = data[title]
        rating_str: str
        if float(rating_value) >= 8.0:
            rating_str = colored(rating_value, 'green')
        elif float(rating_value) >= 6.5 and float(rating_value) < 8.0:
            rating_str = colored(rating_value, 'yellow')
        elif float(rating_value) >= 5.0 and float(rating_value) < 6.5:
            rating_str = colored(rating_value, 'blue')
        else:
            rating_str = colored(rating_value, 'red')
        print(f"{title: <{max_title_len}}: {rating_str}")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nInterrupted by user. Exiting...")
        sys.exit(0)
