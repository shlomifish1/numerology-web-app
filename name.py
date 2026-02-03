

class NamesData:
    def __init__(self):
        self.test = None

    def aiv(self,let):
        if let == "א" or let == "ה" or let == "ו" or let == "י" or let == "ע" or let == "a" or let == "i" or let == "v":
            return let

    def itzurim(self, e):
        if e == 'ב' or e == 'ג' or e == 'ד' or e == 'ז' or e == 'ח' or e == 'ט' or e == 'כ' or e == 'ל' or e == 'מ' or e == 'נ' or\
                e == 'ס' or e == 'פ' or e == 'צ' or e == 'ק' or e == 'ר' or e == 'ש' or e == 'ת' or e == 'ף' or e == 'ץ' or e == 'ם' or e == 'ן'\
                or e == "b" or e == "c" or e == "d" or e == "e" or e == "f" or e == "g" or e == "h" or e == "j" or e == "k" or e == "l"\
                or e == "m" or e == "n" or e == "o" or e == "p" or e == "q" or e == "r" or e == "s" or e == "t" or e == "u" or e == "w"\
                or e == "x" or e == "y" or e == "z":
            return e

    def sum_l(self, name_gimatriha):
        sum_letter = sum(name_gimatriha)
        while sum_letter > 9:
            sum_letter_name_list = [x for x in str(sum_letter)]
            sum_letter_name_map = map(int, sum_letter_name_list)
            sum_letter_name_convert_list = list(sum_letter_name_map)
            sum_letter = sum(sum_letter_name_convert_list)
        return sum_letter

    def sum_num(self, numbers):
        while numbers > 9:
            sum_numbers_list = [x for x in str(numbers)]
            sum_numbers_list_map = map(int, sum_numbers_list)
            sum_numbers_convert_list = list(sum_numbers_list_map)
            numbers = sum(sum_numbers_convert_list)
        return numbers

    def letter(self, client_name):
        letters = {'א': 1,
                   'ב': 2,
                   'ג': 3,
                   'ד': 4,
                   'ה': 5,
                   'ו': 6,
                   'ז': 7,
                   'ח': 8,
                   'ט': 9,
                   'י': 1,
                   'כ': 2,
                   'ל': 3,
                   'מ': 4,
                   'ם': 4,
                   'נ': 5,
                   'ן': 5,
                   'ס': 6,
                   'ע': 7,
                   'פ': 8,
                   'ף': 8,
                   'צ': 9,
                   'ץ': 9,
                   'ק': 1,
                   'ר': 2,
                   'ש': 3,
                   'ת': 4,
                   'ך': 2,

                   "a": 1,
                   "s": 1,
                   "j": 1,
                   "b": 2,
                   "k": 2,
                   "t": 2,
                   "c": 3,
                   "l": 3,
                   "u": 3,
                   "d": 4,
                   "m": 4,
                   "v": 4,
                   "e": 5,
                   "n": 5,
                   "w": 5,
                   "f": 6,
                   "o": 6,
                   "x": 6,
                   "g": 7,
                   "p": 7,
                   "y": 7,
                   "h": 8,
                   "q": 8,
                   "z": 8,
                   "i": 9,
                   "r": 9,

                   }
        name_gimatriha = []
        for letter in client_name:
            if letter in letters:
                name_gimatriha.append(letters[letter])
        return self.sum_l(name_gimatriha=name_gimatriha)


