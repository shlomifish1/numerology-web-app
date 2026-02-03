from datetime import date
import name
today = date.today()


class This_Year:
    def __init__(self):
        # self.this_month = None
        # self.this_year = None
        self.shana_nisteret_calc = None
        self.shana_ishit_calc = None
        self.final_short_this_year = None
        self.this_year_list = None
        self.this_year = int(today.strftime("%Y"))
        self.this_month = int(today.strftime("%m"))
        self.this_year_list = [x for x in str(self.this_year)]
        self.final_short_this_year = map(int, self.this_year_list)
        self.final_short_this_year = sum(self.final_short_this_year)
        self.first_quarter = None
        self.second_quarter = None
        self.third_quarter = None
        self.forth_quarter = None
        self.year_code = None



    def shana_ishit(self, day, month, bd_month):
        self.shana_ishit_calc = int(day + month + self.final_short_this_year)
        if bd_month > int(self.this_month):
            self.shana_ishit_calc -= 1
        self.check_for_month(bd_month)
        if self.shana_ishit_calc > 9:
            self.shana_ishit_calc = name.NamesData().sum_num(self.shana_ishit_calc)
        return self.shana_ishit_calc

    def check_for_month(self, bd_month):
        if bd_month > 6:
            self.shana_ishit_calc += 1

    def shana_nisteret(self, destiny, ishit, day, month, bd_month):
        # אני מייצר קודם כל שנה אישית הפעם ללא חישוב של חודש יולי עד דצמבר
        self.shana_ishit_calc = int(day + month + self.final_short_this_year)
        if bd_month > int(self.this_month):
            self.shana_ishit_calc -= 1
        if self.shana_ishit_calc > 9:
            self.shana_ishit_calc = name.NamesData().sum_num(self.shana_ishit_calc)
        # return self.shana_ishit_calc

        self.shana_nisteret_calc = int(self.shana_ishit_calc + destiny)
        if self.shana_nisteret_calc > 9:
            self.shana_nisteret_calc = name.NamesData().sum_num(self.shana_nisteret_calc)
        return self.shana_nisteret_calc

    def calculet_age(self, year_of_birth, bd_month):
        age = int(self.this_year - year_of_birth)
        if bd_month > int(self.this_month):
            age -= 1
        return age

    def f_quarters(self, destiny):
        self.first_quarter = destiny + self.final_short_this_year
        # Ensure the sum is always between 0 and 9
        self.first_quarter_single_digit = (self.first_quarter - 1) % 9 + 1
        return self.first_quarter_single_digit

    def s_quarters(self, destiny, day, month, bd_month):
        self.second_quarter = destiny + self.shana_ishit(day=day, month=month, bd_month=bd_month)
        self.second_quarter_single_digit = (self.second_quarter -1) % 9 + 1
        return self.second_quarter_single_digit

    def frth_quarters(self, destiny, day, month, bd_month):
        self.forth_quarter = self.shana_ishit(day=day, month=month, bd_month=bd_month) + (self.final_short_this_year)
        self.forth_quarter_single_digit = (self.forth_quarter -1) %9 + 1
        return self.forth_quarter_single_digit



