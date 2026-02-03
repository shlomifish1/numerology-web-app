
class Pythg:

    def digit_string(self, my_list):
        digit_string = ""
        for digit in range(1, 10):
            count = my_list.count(digit)
            if count > 0:
                digit_string += str(digit) * count
        if digit_string == "":
            return None
        else:
            return int(digit_string)