#!/usr/bin/env python3

from imdb import IMDb
from tabulate import tabulate
from termcolor import colored

# create an instance of the IMDb class
ia = IMDb()

# get a TV show

# Print debug info?
debug = False

series_list = [
    {'id': '0118401', 'name': 'Midsomer Murders'},
    {'id': '0096697', 'name': 'The Simpsons'},
    {'id': '1466074', 'name': 'Columbo'},
    {'id': '0098904', 'name': 'Seinfeld'},
]

for series_id in series_list:
    series = ia.get_movie(series_id['id'])

    ia.update(series, 'episodes')
    # ia.update(series, 'episodes rating')

    data = {}

    print("------\n")

    print(f"Ratings information for {series['title']}\n")

    print("\tgreen >= 8.0\n\tyellow >= 6.5\n\tblue >=5.0\n\tred < 5.0\n")

    for season in sorted(series['episodes'].keys()):
        if debug:
            print(f"Ratings for season {season}")
        ratings = []
        for episode in series['episodes'][season].keys():
            try:
                rating = series['episodes'][season][episode]['rating']
                # truncate to 2 decimal places
                rating = f"{rating:.2f}"
                if float(rating) >= 8.0:
                    rating = colored(rating, 'green')
                elif float(rating) >= 6.5 and float(rating) < 8.0:
                    rating = colored(rating, 'yellow')
                elif float(rating) >= 5.0 and float(rating) < 6.5:
                    rating = colored(rating, 'blue')
                else:
                    rating = colored(rating, 'red')
                ratings.append(rating)
                title = series['episodes'][season][episode]['title']
            except KeyError:
                rating = 0.0
                title = "Unknown"
            if debug:
                print(f"Rating for S{season:02}E{episode:02}: {rating:0.2f}")
        season = f"{season:2d}"
        data.update({season: ratings})

    if debug:
        print(data)

    print(tabulate(data, headers="keys", tablefmt="pretty"))
