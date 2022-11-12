#!/usr/bin/env python3

from imdb import Cinemagoer
# from tabulate import tabulate
from termcolor import colored

# create an instance of the IMDb class
ia = Cinemagoer()

# Print debug info?
debug = False

mcu_list = [
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
    {'id': '9376612', 'name': 'Shang-Chi and the Legend Of The Ten Rings (2021)'},
    {'id': '9032400', 'name': 'Eternals (2021)'},
    {'id': '10872600', 'name': 'Spider-Man: No Way Home (2021)'},
    {'id': '9419884', 'name': 'Doctor Strange in the Multiverse Of Madness (2022)'},
    {'id': '10648342', 'name': 'Thor: Love and Thunder (2022)'},
]

data = {}

# Get ratings for each movie in the list
for movie_id in mcu_list:
    movie = ia.get_movie(movie_id['id'])
    movie.infoset2keys

    try:
        rating = movie.get('rating')
    except KeyError:
        rating = 0.0
    if debug:
        print(f"Rating for {movie['title']}: {rating}")
    title = movie['title']
    data.update({title: rating})

if debug:
    print(data)

sorted_by_rating = sorted(data, key=data.get, reverse=True)

if debug:
    print(sorted_by_rating)

print("Marvel Cinematic Universe films sorted by IMDB user rating")
print("\tgreen >= 8.0\n\tyellow >= 6.5\n\tblue >=5.0\n\tred < 5.0\n")
max_title_len = len(max(sorted_by_rating, key=len))
for title in sorted_by_rating:
    rating = data[title]
    if float(rating) >= 8.0:
        rating = colored(rating, 'green')
    elif float(rating) >= 6.5 and float(rating) < 8.0:
        rating = colored(rating, 'yellow')
    elif float(rating) >= 5.0 and float(rating) < 6.5:
        rating = colored(rating, 'blue')
    else:
        rating = colored(rating, 'red')
    print(f"{title: <{max_title_len}}: {rating}")
