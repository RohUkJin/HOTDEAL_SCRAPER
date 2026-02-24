from enum import Enum

class Category(str, Enum):
    FOOD = "Food"
    DRINK = "Drink"
    TOILETRIES = "Toiletries"
    OFFICE = "Office"
    OTHERS = "Others" # For valid deals that don't fit major categories
    DROP = "DROP" # For invalid/filtered deals
