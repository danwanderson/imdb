#!/usr/bin/env python3

# pip3 install Cinemagoer termcolor tabulate
from imdb import Cinemagoer
from tabulate import tabulate
from termcolor import colored

# create an instance of the IMDb class
ia = Cinemagoer()

# get a TV show

# Print debug info?
debug = False

series_list = [
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
