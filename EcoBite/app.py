import csv
import io
import re
from pathlib import Path

from flask import Flask, render_template, request

app = Flask(__name__)

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"

# One weekly-specials CSV per store (same columns for each). To add a store,
# drop its CSV in data/ and add a line here.
STORES = {
    "Maxi": "maxi_weekly_grocery_specials-v2.csv",
    "Super C": "superc_weekly_grocery_specials-v2.csv",
    "Walmart": "walmart_weekly_grocery_specials-v2.csv",
}

# Logos shown in the page header (files live in static/; a missing file is skipped).
STORE_LOGOS = {
    "Maxi": "maxi-logo.svg",
    "Super C": "superc-logo.png",
    "Walmart": "walmart-logo.svg",
}


# ---------------------------------------------------------------------------
# 1. Reading the CSV
# ---------------------------------------------------------------------------

def to_number(value):
    """Turn text like '$3.64' or '1.95 (per L)' into a float. 'N/A' -> None."""
    if value is None:
        return None

    value = str(value).strip()
    if not value or value.upper().startswith("N/A"):
        return None

    match = re.search(r"\d+(?:\.\d+)?", value.replace(",", ""))
    return float(match.group()) if match else None


def unit_price_label(raw):
    """Nice label for the 'Item price per kg' column, e.g. '$3.68/kg' or '$1.00/ea'."""
    raw = (raw or "").strip()

    if raw.upper().startswith("N/A"):
        match = re.search(r"\((.+?)\)", raw)  # N/A ($1.00/ea)  ->  $1.00/ea
        return match.group(1) if match else ""

    number = to_number(raw)
    if number is None:
        return ""

    unit = re.search(r"per\s+(\w+)", raw, re.I)  # 1.95 (per L) -> L
    return f"${number:.2f}/{unit.group(1) if unit else 'kg'}"


def clean_name(name):
    """Short, direct product name: drop quantities, sizes and pack wording."""
    name = re.sub(r"\s*\([^)]*\)", "", name)  # (227 g), (1 ea), (Back Attached)
    name = re.sub(r",?\s*\b(Club Pack|Club Size|Pack of \d+|Half Pint|Bunch|Single|Bags?)\b", "", name, flags=re.I)
    name = re.sub(r"\s*,\s*$", "", name.strip())
    return re.sub(r"\s{2,}", " ", name).strip(" ,")


# Short names shown to the user. The first pattern found in the product name
# wins, so keep specific patterns above general ones. Every store's products
# map to the same short names, which is how stores get compared.
SIMPLE_PATTERNS = [
    ("red seedless grapes", "Red Grapes"),
    ("green seedless grapes", "Green Grapes"),
    ("mini cucumber", "Mini Cucumbers"),
    ("cucumber", "Cucumber"),
    ("avocado", "Avocado"),
    ("kiwi", "Kiwis"),
    ("raspberr", "Raspberries"),
    ("cremini", "Cremini Mushrooms"),
    ("white mushroom", "White Mushrooms"),
    ("acorn squash", "Acorn Squash"),
    ("on the vine", "Vine Tomatoes"),
    ("cherry tomato", "Mini Tomatoes"),
    ("variety pack", "Mini Tomatoes"),
    ("tomato", "Tomato"),
    ("potato", "Potato"),
    ("plantain", "Plantains"),
    ("orange", "Oranges"),
    ("cabbage", "Green Cabbage"),
    ("banana", "Bananas"),
    ("coleslaw", "Coleslaw"),
    ("garden salad", "Garden Salad"),
    ("basil", "Basil"),
    ("2% evaporated", "2% Evaporated Milk"),
    ("evaporated", "Evaporated Milk"),
    ("condensed", "Condensed Milk"),
    ("coconut milk", "Coconut Milk"),
    ("chocolate milk", "Chocolate Milk"),
    ("strawberry milk", "Strawberry Milk"),
    ("coffee cream", "Cream"),
    ("1% milk", "1% Milk"),
    ("2% milk", "2% Milk"),
    ("homogenized", "Whole Milk"),
    ("skim milk", "Skim Milk"),
    ("tenderloin", "Pork Tenderloin"),
    ("turkey", "Turkey"),
    ("blade roast", "Blade Roast"),
    ("chicken leg", "Chicken Legs"),
    ("drumsticks", "Chicken Legs"),
    ("bacon", "Bacon"),
    ("broccoli", "Broccoli"),
    ("yellow onion", "Onions"),
    ("bell pepper", "Bell Peppers"),
    ("whipping cream", "Whipping Cream"),
    ("chicken thigh", "Chicken Thighs"),
    ("chicken breast", "Chicken Breasts"),
    ("chicken wings", "Chicken Wings"),
    ("extra lean ground beef", "Extra Lean Ground Beef"),
    ("ground beef", "Ground Beef"),
    ("marinating steak", "Marinating Steak"),
    ("stew cubes", "Beef Stew Cubes"),
    ("pork chops", "Pork Chops"),
    ("back ribs", "Pork Ribs"),
    ("ground pork", "Ground Pork"),
    ("shrimp", "Shrimp"),
    ("montreal chicken seasoning", "Chicken Seasoning"),
    ("steak spice", "Steak Spice"),
    ("soy sauce", "Soy Sauce"),
    ("ham steak", "Ham Steak"),
    ("black forest", "Black Forest Ham"),
    ("old fashioned", "Smoked Ham"),
    ("mild italian", "Mild Italian Sausages"),
    ("hot italian", "Hot Italian Sausages"),
    ("honey garlic", "Honey Garlic Sausages"),
    ("ground chicken", "Ground Chicken"),
    ("trout", "Trout"),
    ("salmon", "Salmon"),
    ("garlic", "Garlic"),
    ("taco seasoning", "Taco Seasoning"),
    ("horseradish", "Horseradish Sauce"),
    ("olive oil", "Olive Oil"),
    ("sesame oil", "Sesame Oil"),
    ("peppercorn", "Peppercorn Sauce"),
    ("hot chicken sauce", "Hot Chicken Sauce"),
    ("bar-b-q", "BBQ Sauce"),
    ("bbq", "BBQ Sauce"),
    ("salad dressing", "Salad Dressing"),
]


def simple_name(full_name):
    lower = full_name.lower()
    for pattern, short in SIMPLE_PATTERNS:
        if pattern in lower:
            return short
    return full_name


# In the ingredient picker, similar products are grouped under one broad name
# (picking "Chicken" counts every kind of chicken). Recipes still name the exact kind.
BROAD_NAMES = {
    "Ground Chicken": "Chicken", "Chicken Legs": "Chicken", "Chicken Thighs": "Chicken",
    "Chicken Breasts": "Chicken", "Chicken Wings": "Chicken",
    "Ground Beef": "Beef", "Extra Lean Ground Beef": "Beef", "Marinating Steak": "Beef",
    "Beef Stew Cubes": "Beef", "Blade Roast": "Beef",
    "Pork Tenderloin": "Pork", "Pork Chops": "Pork", "Pork Ribs": "Pork", "Ground Pork": "Pork",
    "Mild Italian Sausages": "Sausages", "Hot Italian Sausages": "Sausages",
    "Honey Garlic Sausages": "Sausages",
    "Ham Steak": "Ham", "Black Forest Ham": "Ham", "Smoked Ham": "Ham",
    "Salmon": "Fish", "Trout": "Fish",
}


def load_ingredients():
    """Read every store's weekly specials. Each product gets a unique id."""
    items = []

    for store, filename in STORES.items():
        path = DATA_DIR / filename
        if not path.exists():
            continue  # a store without a CSV is simply skipped

        # Excel on Windows often saves CSVs as cp1252 rather than UTF-8 (e.g. "Quebon" with an accent).
        raw = path.read_bytes()
        try:
            text = raw.decode("utf-8-sig")
        except UnicodeDecodeError:
            text = raw.decode("cp1252")

        for row in csv.DictReader(io.StringIO(text, newline="")):
            row = {
                key.strip().lower().replace("_", " "): (value or "").strip()
                for key, value in row.items()
                if key is not None
            }

            full_name = clean_name(row.get("item name") or "")
            price = to_number(row.get("item price"))
            if not full_name or price is None:
                continue  # skip rows we can't price

            items.append({
                "id": len(items),
                "store": store,
                "category": row.get("category", "Other"),
                "name": simple_name(full_name),
                "broad": BROAD_NAMES.get(simple_name(full_name), simple_name(full_name)),
                "match": full_name.lower(),
                "allergens": sorted(allergens_in([full_name])),
                "price": price,
                "unit_price": unit_price_label(row.get("item price per kg")),
                "money_saved": to_number(row.get("money saved")) or 0.0,
            })

    return items


def group_ingredients(items):
    """One entry per short name (e.g. 'Potato') with its cheapest price across stores."""
    groups = {}
    for item in items:
        group = groups.setdefault(item["broad"], {
            "name": item["broad"],
            "matches": [],
            "allergens": set(),
            "price": item["price"],
            "store": item["store"],
            "money_saved": 0.0,
        })
        group["matches"].append(item["match"])
        group["allergens"] |= set(item["allergens"])
        group["money_saved"] = max(group["money_saved"], item["money_saved"])
        if item["price"] < group["price"]:
            group["price"], group["store"] = item["price"], item["store"]

    for group in groups.values():
        group["allergens"] = sorted(group["allergens"])
    return list(groups.values())


# ---------------------------------------------------------------------------
# 2. Recipes
#    Each recipe lists "slots". A slot is matched to the cheapest product in the
#    CSV whose name contains one of its keywords (or to the product the user
#    picked, if it fits that slot). "pantry" items are assumed to be at home,
#    so they are shown but not priced.
# ---------------------------------------------------------------------------

def slot(label, *keywords):
    return {"label": label, "keywords": [k.lower() for k in keywords]}


RECIPES = [
    # ---------------- Italian ----------------
    {
        "name": "Italian Sausage and Tomato Pasta",
        "type": "Italian",
        "time": "30 min",
        "servings": 4,
        "ingredients": [
            slot("Italian sausage", "italian pork sausages"),
            slot("Tomatoes", "tomato"),
            slot("Garlic", "chopped garlic", "minced garlic"),
            slot("Olive oil", "olive oil"),
            slot("Fresh basil", "basil"),
        ],
        "pantry": ["Pasta", "Salt and pepper"],
        "steps": [
            "Brown the sliced sausage in olive oil, then add garlic for 1 minute.",
            "Add the chopped tomatoes and simmer 15 minutes until saucy.",
            "Toss with cooked pasta and finish with torn basil.",
        ],
    },
    {
        "name": "Chicken Meatballs in Tomato Sauce",
        "type": "Italian",
        "time": "40 min",
        "servings": 4,
        "ingredients": [
            slot("Ground chicken", "ground chicken"),
            slot("Tomatoes", "tomato"),
            slot("Garlic", "chopped garlic", "minced garlic"),
            slot("Olive oil", "olive oil"),
            slot("Fresh basil", "basil"),
        ],
        "pantry": ["Spaghetti", "Breadcrumbs", "1 egg"],
        "steps": [
            "Mix ground chicken with garlic, breadcrumbs, egg and salt. Roll into balls.",
            "Brown the meatballs in olive oil, then add chopped tomatoes.",
            "Simmer 20 minutes, add basil and serve over spaghetti.",
        ],
    },
    {
        "name": "Roasted Trout with Garlic Potatoes",
        "type": "Italian",
        "time": "40 min",
        "servings": 2,
        "ingredients": [
            slot("Steelhead trout", "steelhead trout"),
            slot("Potatoes", "yellow potato"),
            slot("Garlic", "chopped garlic", "minced garlic"),
            slot("Olive oil", "olive oil"),
        ],
        "pantry": ["Lemon", "Salt and pepper"],
        "steps": [
            "Cube the potatoes, toss with olive oil and garlic, roast at 425°F for 25 minutes.",
            "Add the trout fillets to the pan and roast 12 minutes more.",
            "Finish with lemon, salt and pepper.",
        ],
    },

    # ---------------- Asian ----------------
    {
        "name": "Sesame Garlic Chicken Stir-fry",
        "type": "Asian",
        "time": "25 min",
        "servings": 4,
        "ingredients": [
            slot("Ground chicken", "ground chicken"),
            slot("Cabbage", "green cabbage"),
            slot("Garlic", "chopped garlic", "minced garlic"),
            slot("Sesame oil", "sesame oil"),
        ],
        "pantry": ["Rice", "Soy sauce"],
        "steps": [
            "Cook the rice. Heat sesame oil in a wok and brown the chicken.",
            "Add garlic and shredded cabbage, stir-fry 5 minutes.",
            "Season with soy sauce and serve over rice.",
        ],
    },
    {
        "name": "Salmon Rice Bowl",
        "type": "Asian",
        "time": "25 min",
        "servings": 2,
        "ingredients": [
            slot("Salmon", "wild pink salmon"),
            slot("Cucumber", "cucumber"),
            slot("Avocado", "avocado"),
            slot("Sesame oil", "sesame oil"),
        ],
        "pantry": ["Rice", "Soy sauce"],
        "steps": [
            "Pan-sear the salmon portions in a little sesame oil, 4 minutes per side.",
            "Slice the cucumber and avocado.",
            "Serve everything over warm rice with soy sauce.",
        ],
    },
    {
        "name": "Coconut Chicken Curry",
        "type": "Asian",
        "time": "45 min",
        "servings": 4,
        "ingredients": [
            slot("Chicken legs", "chicken leg", "drumsticks"),
            slot("Coconut milk", "coconut milk"),
            slot("Garlic", "chopped garlic", "minced garlic"),
            slot("Mushrooms", "mushrooms"),
        ],
        "pantry": ["Curry paste", "Rice"],
        "steps": [
            "Brown the chicken legs in a pot, then stir in garlic and curry paste.",
            "Add coconut milk and mushrooms, cover and simmer 30 minutes.",
            "Serve over rice.",
        ],
    },

    # ---------------- Mexican ----------------
    {
        "name": "Chicken Tacos",
        "type": "Mexican",
        "time": "20 min",
        "servings": 4,
        "ingredients": [
            slot("Ground chicken", "ground chicken"),
            slot("Taco seasoning", "taco seasoning"),
            slot("Tomatoes", "tomato"),
            slot("Avocado", "avocado"),
        ],
        "pantry": ["Tortillas", "Shredded cheese"],
        "steps": [
            "Brown the chicken, add taco seasoning and a splash of water.",
            "Dice the tomatoes and avocado.",
            "Fill warm tortillas and top with cheese.",
        ],
    },
    {
        "name": "Taco Salad",
        "type": "Mexican",
        "time": "20 min",
        "servings": 4,
        "ingredients": [
            slot("Ground chicken", "ground chicken"),
            slot("Taco seasoning", "taco seasoning"),
            slot("Garden salad", "garden salad"),
            slot("Tomatoes", "tomato"),
            slot("Dressing", "salad dressing"),
        ],
        "pantry": ["Tortilla chips"],
        "steps": [
            "Cook the chicken with taco seasoning.",
            "Toss the salad kit with diced tomatoes and dressing.",
            "Top with warm chicken and crushed tortilla chips.",
        ],
    },

    # ---------------- Comfort ----------------
    {
        "name": "Roast with Potatoes and Squash",
        "type": "Comfort",
        "time": "2 h 30 min",
        "servings": 6,
        "ingredients": [
            slot("Boneless blade roast", "blade roast"),
            slot("Potatoes", "yellow potato"),
            slot("Acorn squash", "acorn squash"),
            slot("Garlic", "chopped garlic", "minced garlic"),
            slot("Horseradish sauce", "horseradish"),
        ],
        "pantry": ["Salt and pepper"],
        "steps": [
            "Rub the roast with garlic, salt and pepper. Roast at 325°F for about 2 hours.",
            "Add cubed potatoes and squash halves for the last hour.",
            "Slice the roast and serve with horseradish sauce.",
        ],
    },
    {
        "name": "BBQ Chicken Legs with Coleslaw",
        "type": "Comfort",
        "time": "50 min",
        "servings": 4,
        "ingredients": [
            slot("Chicken legs", "chicken leg", "drumsticks"),
            slot("BBQ sauce", "bar-b-q", "bbq"),
            slot("Coleslaw", "coleslaw"),
        ],
        "pantry": ["Salt and pepper"],
        "steps": [
            "Season the chicken legs and bake at 400°F for 30 minutes.",
            "Brush with BBQ sauce and bake 15 minutes more.",
            "Serve with the coleslaw.",
        ],
    },
    {
        "name": "Ham Steak with Potatoes and Peppercorn Sauce",
        "type": "Comfort",
        "time": "30 min",
        "servings": 2,
        "ingredients": [
            slot("Ham steak", "ham steak"),
            slot("Potatoes", "yellow potato"),
            slot("Peppercorn sauce", "peppercorn sauce"),
        ],
        "pantry": ["Butter"],
        "steps": [
            "Boil cubed potatoes until tender, then pan-fry in butter until golden.",
            "Sear the ham steak 3 minutes per side.",
            "Warm the peppercorn sauce and spoon over the ham.",
        ],
    },
    {
        "name": "Bacon and Potato Chowder",
        "type": "Comfort",
        "time": "40 min",
        "servings": 4,
        "ingredients": [
            slot("Bacon", "bacon"),
            slot("Potatoes", "yellow potato"),
            slot("Milk", "1% milk", "2% milk", "homogenized", "skim milk"),
        ],
        "pantry": ["Onion", "Salt and pepper"],
        "steps": [
            "Cook chopped bacon until crisp, then soften the onion in the fat.",
            "Add cubed potatoes and water to cover, simmer until tender.",
            "Stir in milk, warm through and season.",
        ],
    },
    {
        "name": "Sausage and Cabbage Skillet",
        "type": "Comfort",
        "time": "30 min",
        "servings": 4,
        "ingredients": [
            slot("Honey garlic sausages", "honey garlic"),
            slot("Cabbage", "green cabbage"),
            slot("Potatoes", "yellow potato"),
        ],
        "pantry": ["Salt and pepper"],
        "steps": [
            "Brown the sliced sausages in a large skillet.",
            "Add diced potatoes and cover for 10 minutes.",
            "Add shredded cabbage and cook until tender.",
        ],
    },
    {
        "name": "Pork Tenderloin with Creamy Mushrooms",
        "type": "Comfort",
        "time": "35 min",
        "servings": 4,
        "ingredients": [
            slot("Pork tenderloin", "pork tenderloin"),
            slot("Mushrooms", "mushrooms"),
            slot("Garlic", "chopped garlic", "minced garlic"),
            slot("Cream", "coffee cream"),
            slot("Olive oil", "olive oil"),
        ],
        "pantry": ["Salt and pepper"],
        "steps": [
            "Sear the tenderloin in olive oil, then roast at 400°F for 15 minutes.",
            "Sauté mushrooms and garlic, then add the cream and reduce.",
            "Slice the pork and spoon the sauce over top.",
        ],
    },

    # ---------------- Light and fresh ----------------
    {
        "name": "Salmon Garden Salad",
        "type": "Light and fresh",
        "time": "20 min",
        "servings": 2,
        "ingredients": [
            slot("Salmon", "wild pink salmon"),
            slot("Garden salad", "garden salad"),
            slot("Cucumber", "cucumber"),
            slot("Dressing", "salad dressing"),
        ],
        "pantry": ["Lemon"],
        "steps": [
            "Pan-sear the salmon, 4 minutes per side.",
            "Toss the salad kit with sliced cucumber and dressing.",
            "Flake the salmon on top and squeeze over lemon.",
        ],
    },
    {
        "name": "Tomato, Basil and Avocado Salad",
        "type": "Light and fresh",
        "time": "10 min",
        "servings": 2,
        "ingredients": [
            slot("Tomatoes", "tomato"),
            slot("Avocado", "avocado"),
            slot("Fresh basil", "basil"),
            slot("Olive oil", "olive oil"),
        ],
        "pantry": ["Salt and pepper", "Crusty bread"],
        "steps": [
            "Slice the tomatoes and avocado onto a platter.",
            "Scatter with basil, drizzle with olive oil and season.",
            "Serve with crusty bread.",
        ],
    },
    {
        "name": "Fresh Fruit Salad",
        "type": "Light and fresh",
        "time": "10 min",
        "servings": 4,
        "ingredients": [
            slot("Grapes", "seedless grapes"),
            slot("Kiwis", "kiwis"),
            slot("Oranges", "oranges"),
            slot("Bananas", "bananas"),
        ],
        "pantry": ["Honey (optional)"],
        "steps": [
            "Halve the grapes, peel and slice the kiwis, oranges and bananas.",
            "Toss together and chill for 10 minutes.",
        ],
    },

    # ---------------- Breakfast ----------------
    {
        "name": "Bacon and Mushroom Omelette",
        "type": "Breakfast",
        "time": "15 min",
        "servings": 2,
        "ingredients": [
            slot("Bacon", "bacon"),
            slot("Mushrooms", "mushrooms"),
            slot("Milk", "1% milk", "2% milk", "homogenized", "skim milk"),
        ],
        "pantry": ["Eggs", "Shredded cheese"],
        "steps": [
            "Cook chopped bacon, then sauté the mushrooms in the pan.",
            "Whisk eggs with a splash of milk and pour over the filling.",
            "Fold, add cheese and cook until set.",
        ],
    },
    {
        "name": "Banana Berry Chocolate Milk Smoothie",
        "type": "Breakfast",
        "time": "5 min",
        "servings": 2,
        "ingredients": [
            slot("Bananas", "bananas"),
            slot("Chocolate milk", "chocolate milk"),
            slot("Raspberries", "raspberries"),
        ],
        "pantry": ["Ice"],
        "steps": [
            "Add everything to a blender with a handful of ice.",
            "Blend until smooth and serve cold.",
        ],
    },

    # ---------------- From the web (each has a "url" to the original recipe) ----------------
    {
        "name": "Coconut Chicken Curry with Potatoes",
        "type": "Asian",
        "time": "40 min",
        "servings": 6,
        "source": "Tea for Turmeric",
        "url": "https://www.teaforturmeric.com/coconut-chicken-curry-with-potatoes",
        "ingredients": [
            slot("Chicken", "chicken leg", "drumsticks"),
            slot("Coconut milk", "coconut milk"),
            slot("Potatoes", "yellow potato"),
            slot("Tomato", "tomato"),
            slot("Garlic", "chopped garlic", "minced garlic"),
        ],
        "pantry": ["Onion", "Ginger", "Curry spices", "Oil", "Cilantro"],
        "steps": [
            "Warm the oil, toast the whole spices and cook the onion until golden.",
            "Add garlic, ginger, tomato, potatoes and ground spices, then the chicken and coconut milk.",
            "Cover and simmer about 20 minutes until the chicken and potatoes are tender.",
        ],
    },
    {
        "name": "Ground Chicken Stir-fry with Vegetables",
        "type": "Asian",
        "time": "35 min",
        "servings": 4,
        "source": "Salt & Lavender",
        "url": "https://www.saltandlavender.com/ground-chicken-stir-fry/",
        "ingredients": [
            slot("Ground chicken", "ground chicken"),
            slot("Garlic", "chopped garlic", "minced garlic"),
            slot("Olive oil", "olive oil"),
        ],
        "pantry": ["Onion", "Snow peas", "Bell pepper", "Broccoli", "Carrots", "Cashews", "Hoisin and soy sauce"],
        "steps": [
            "Whisk the sauce, then brown the chicken in a skillet and set it aside.",
            "Cook the onion and vegetables with the garlic until crisp-tender.",
            "Return the chicken with the cashews, add the sauce and stir until thick.",
        ],
    },
    {
        "name": "Ground Chicken and Green Bean Stir-fry",
        "type": "Asian",
        "time": "25 min",
        "servings": 4,
        "source": "Well Fed Baker",
        "url": "https://wellfedbaker.com/ground-chicken-stir-fry/",
        "ingredients": [
            slot("Ground chicken", "ground chicken"),
            slot("Sesame oil", "sesame oil"),
            slot("Garlic", "chopped garlic", "minced garlic"),
        ],
        "pantry": ["Green beans", "Red bell pepper", "Ginger", "Soy sauce", "Honey", "Rice vinegar"],
        "steps": [
            "Brown the chicken, then remove it and drain the fat.",
            "Stir-fry the green beans and pepper in sesame oil, then add the chicken, ginger and garlic.",
            "Add the soy, honey and vinegar sauce and simmer until glossy.",
        ],
    },
    {
        "name": "Salmon, Avocado and Cucumber Salad",
        "type": "Light and fresh",
        "time": "18 min",
        "servings": 4,
        "source": "BBC Good Food Middle East",
        "url": "https://bbcgoodfoodme.com/recipes/salmon-avocado-and-cucumber-salad",
        "ingredients": [
            slot("Salmon", "wild pink salmon"),
            slot("Avocado", "avocado"),
            slot("Cucumber", "cucumber"),
            slot("Olive oil", "olive oil"),
        ],
        "pantry": ["Mixed salad leaves", "Mint", "Limes", "Honey"],
        "steps": [
            "Season and oil the salmon, then whisk a lime, honey and olive oil dressing.",
            "Pan-fry the salmon until crisp outside and still moist inside.",
            "Plate the leaves, cucumber and avocado, top with salmon and drizzle with dressing.",
        ],
    },
    {
        "name": "Creamy Mushroom Pork Tenderloin",
        "type": "Comfort",
        "time": "30 min",
        "servings": 4,
        "source": "Salt & Lavender",
        "url": "https://www.saltandlavender.com/creamy-mushroom-pork-tenderloin",
        "ingredients": [
            slot("Pork tenderloin", "pork tenderloin"),
            slot("Mushrooms", "mushrooms"),
            slot("Garlic", "chopped garlic", "minced garlic"),
            slot("Cream", "coffee cream"),
            slot("Olive oil", "olive oil"),
        ],
        "pantry": ["Butter", "Dijon mustard", "Italian seasoning", "Broth"],
        "steps": [
            "Slice the tenderloin into medallions, season and sear in oil, then set aside.",
            "Cook the mushrooms until dry, add garlic, mustard, seasoning and broth, then stir in the cream.",
            "Return the pork to the pan and simmer until cooked through and the sauce thickens.",
        ],
    },

    # ---------------- More meals using the extra products ----------------
    {
        "name": "Garlic Shrimp Pasta",
        "type": "Italian",
        "time": "20 min",
        "servings": 4,
        "ingredients": [
            slot("Shrimp", "shrimp"),
            slot("Garlic", "chopped garlic", "minced garlic"),
            slot("Olive oil", "olive oil"),
        ],
        "pantry": ["Pasta", "Lemon", "Salt and pepper"],
        "steps": [
            "Cook the pasta. Warm olive oil in a large pan and soften the garlic for 1 minute.",
            "Add the thawed shrimp and cook 2 to 3 minutes per side until pink.",
            "Toss with the pasta, a squeeze of lemon, salt and pepper.",
        ],
    },
    {
        "name": "Shrimp and Broccoli Stir-fry",
        "type": "Asian",
        "time": "25 min",
        "servings": 4,
        "ingredients": [
            slot("Shrimp", "shrimp"),
            slot("Broccoli", "broccoli"),
            slot("Garlic", "chopped garlic", "minced garlic"),
            slot("Soy sauce", "soy sauce"),
        ],
        "pantry": ["Rice", "Ginger", "Cornstarch"],
        "steps": [
            "Cook the rice. Stir-fry the broccoli in a hot wok for 4 minutes.",
            "Add the shrimp and garlic and cook until the shrimp turn pink.",
            "Stir in soy sauce mixed with a little cornstarch and water until glossy. Serve over rice.",
        ],
    },
    {
        "name": "Beef and Broccoli",
        "type": "Asian",
        "time": "30 min",
        "servings": 4,
        "ingredients": [
            slot("Beef steak", "marinating steak"),
            slot("Broccoli", "broccoli"),
            slot("Garlic", "chopped garlic", "minced garlic"),
            slot("Soy sauce", "soy sauce"),
        ],
        "pantry": ["Rice", "Brown sugar", "Cornstarch"],
        "steps": [
            "Slice the steak thinly and toss with soy sauce, a spoon of cornstarch and the garlic.",
            "Sear the beef in a hot pan in batches, then set aside.",
            "Steam the broccoli, return the beef with a splash of soy sauce and brown sugar, and serve over rice.",
        ],
    },
    {
        "name": "Ground Pork Pepper Stir-fry",
        "type": "Asian",
        "time": "25 min",
        "servings": 4,
        "ingredients": [
            slot("Ground pork", "ground pork"),
            slot("Bell peppers", "bell pepper"),
            slot("Garlic", "chopped garlic", "minced garlic"),
            slot("Soy sauce", "soy sauce"),
            slot("Sesame oil", "sesame oil"),
        ],
        "pantry": ["Rice"],
        "steps": [
            "Cook the rice. Brown the pork in sesame oil, breaking it up as it cooks.",
            "Add sliced peppers and garlic and stir-fry for 5 minutes.",
            "Season with soy sauce and serve over rice.",
        ],
    },
    {
        "name": "Beef Bolognese",
        "type": "Italian",
        "time": "40 min",
        "servings": 4,
        "ingredients": [
            slot("Ground beef", "ground beef"),
            slot("Tomatoes", "tomato"),
            slot("Onion", "yellow onion"),
            slot("Garlic", "chopped garlic", "minced garlic"),
            slot("Olive oil", "olive oil"),
        ],
        "pantry": ["Spaghetti", "Salt and pepper"],
        "steps": [
            "Soften the diced onion in olive oil, add garlic, then brown the beef.",
            "Add chopped tomatoes and simmer 25 minutes until thick.",
            "Season and serve over cooked spaghetti.",
        ],
    },
    {
        "name": "Creamy Garlic Chicken Pasta",
        "type": "Italian",
        "time": "35 min",
        "servings": 4,
        "ingredients": [
            slot("Chicken breasts", "chicken breast"),
            slot("Whipping cream", "whipping cream"),
            slot("Garlic", "chopped garlic", "minced garlic"),
            slot("Broccoli", "broccoli"),
            slot("Olive oil", "olive oil"),
        ],
        "pantry": ["Pasta", "Parmesan cheese", "Salt and pepper"],
        "steps": [
            "Slice the chicken and brown it in olive oil, then set aside.",
            "Cook the garlic, pour in the cream and simmer until slightly thick.",
            "Add the chicken and steamed broccoli back in, toss with pasta and parmesan.",
        ],
    },
    {
        "name": "Beef Tacos",
        "type": "Mexican",
        "time": "20 min",
        "servings": 4,
        "ingredients": [
            slot("Ground beef", "ground beef"),
            slot("Taco seasoning", "taco seasoning"),
            slot("Tomatoes", "tomato"),
            slot("Avocado", "avocado"),
        ],
        "pantry": ["Tortillas", "Shredded cheese"],
        "steps": [
            "Brown the beef, drain the fat, then add taco seasoning and a splash of water.",
            "Dice the tomatoes and avocado.",
            "Fill warm tortillas and top with cheese.",
        ],
    },
    {
        "name": "Hearty Beef Stew",
        "type": "Comfort",
        "time": "2 h 30 min",
        "servings": 6,
        "ingredients": [
            slot("Beef stew cubes", "stew cubes"),
            slot("Potatoes", "yellow potato"),
            slot("Onion", "yellow onion"),
            slot("Garlic", "chopped garlic", "minced garlic"),
        ],
        "pantry": ["Broth", "Carrots", "Flour", "Salt and pepper"],
        "steps": [
            "Toss the beef in flour and brown it in a heavy pot with the onion and garlic.",
            "Add broth and simmer, covered, for 1 hour 30 minutes.",
            "Add cubed potatoes and carrots and cook 45 minutes more until tender.",
        ],
    },
    {
        "name": "Steak Spice Steak and Potatoes",
        "type": "Comfort",
        "time": "40 min",
        "servings": 4,
        "ingredients": [
            slot("Beef steak", "marinating steak"),
            slot("Steak spice", "steak spice"),
            slot("Potatoes", "yellow potato"),
            slot("Onion", "yellow onion"),
        ],
        "pantry": ["Butter"],
        "steps": [
            "Rub the steak with steak spice and let it sit 15 minutes.",
            "Roast cubed potatoes and onion wedges at 425F for 30 minutes.",
            "Sear the steak 3 minutes per side, rest it, slice and serve with the potatoes.",
        ],
    },
    {
        "name": "Pork Chops with Peppers and Onions",
        "type": "Comfort",
        "time": "35 min",
        "servings": 4,
        "ingredients": [
            slot("Pork chops", "pork chops"),
            slot("Bell peppers", "bell pepper"),
            slot("Onion", "yellow onion"),
            slot("Olive oil", "olive oil"),
        ],
        "pantry": ["Salt and pepper"],
        "steps": [
            "Season the chops and sear in olive oil, 4 minutes per side. Set aside.",
            "Cook sliced peppers and onion in the same pan until soft.",
            "Return the chops, cover and cook 8 minutes until done.",
        ],
    },
    {
        "name": "Oven BBQ Pork Back Ribs",
        "type": "Comfort",
        "time": "2 h 15 min",
        "servings": 4,
        "ingredients": [
            slot("Pork back ribs", "back ribs"),
            slot("BBQ sauce", "bar-b-q", "bbq"),
            slot("Potatoes", "yellow potato"),
        ],
        "pantry": ["Salt and pepper"],
        "steps": [
            "Season the ribs, wrap in foil and bake at 300F for 1 hour 45 minutes.",
            "Unwrap, brush with BBQ sauce and broil 8 minutes until sticky.",
            "Serve with roasted potatoes.",
        ],
    },
    {
        "name": "Roasted Chicken Thighs with Potatoes and Onions",
        "type": "Comfort",
        "time": "55 min",
        "servings": 4,
        "ingredients": [
            slot("Chicken thighs", "chicken thighs"),
            slot("Potatoes", "yellow potato"),
            slot("Onion", "yellow onion"),
            slot("Garlic", "chopped garlic", "minced garlic"),
            slot("Olive oil", "olive oil"),
        ],
        "pantry": ["Salt and pepper"],
        "steps": [
            "Toss cubed potatoes, onion wedges and garlic with olive oil on a tray.",
            "Nestle in the seasoned chicken thighs, skin side up.",
            "Roast at 425F for 40 minutes until the skin is crisp.",
        ],
    },
    {
        "name": "Montreal Chicken Breast with Peppers",
        "type": "Comfort",
        "time": "30 min",
        "servings": 4,
        "ingredients": [
            slot("Chicken breasts", "chicken breast"),
            slot("Chicken seasoning", "montreal chicken seasoning"),
            slot("Bell peppers", "bell pepper"),
            slot("Olive oil", "olive oil"),
        ],
        "pantry": ["Rice"],
        "steps": [
            "Coat the chicken breasts in Montreal chicken seasoning.",
            "Sear in olive oil 6 minutes per side until cooked through.",
            "Saute sliced peppers in the same pan and serve with the chicken over rice.",
        ],
    },
    {
        "name": "Sticky BBQ Chicken Wings",
        "type": "Comfort",
        "time": "50 min",
        "servings": 4,
        "ingredients": [
            slot("Chicken wings", "chicken wings"),
            slot("BBQ sauce", "bar-b-q", "bbq"),
            slot("Coleslaw", "coleslaw"),
        ],
        "pantry": ["Salt and pepper"],
        "steps": [
            "Season the wings and bake at 425F for 35 minutes, flipping once.",
            "Toss in BBQ sauce and bake 10 minutes more until sticky.",
            "Serve with the coleslaw.",
        ],
    },
]

# Each recipe gets one cuisine and one or more "feelings" so people can browse either way.
CUISINES = ["Italian", "Asian", "Mexican", "Home-style"]
FEELINGS = ["Cozy and comforting", "Light and fresh", "Quick and easy", "Breakfast"]

# Recipes whose feeling isn't obvious from their old type or cooking time.
EXTRA_FEELINGS = {
    "Cozy and comforting": {
        "Italian Sausage and Tomato Pasta", "Chicken Meatballs in Tomato Sauce",
        "Coconut Chicken Curry", "Coconut Chicken Curry with Potatoes",
        "Beef Bolognese", "Creamy Garlic Chicken Pasta",
    },
    "Light and fresh": {
        "Roasted Trout with Garlic Potatoes", "Salmon Rice Bowl", "Taco Salad",
        "Shrimp and Broccoli Stir-fry",
    },
}


def cooking_minutes(text):
    """'2 h 30 min' -> 150, '45 min' -> 45."""
    hours = re.search(r"(\d+)\s*h", text)
    mins = re.search(r"(\d+)\s*min", text)
    return (int(hours.group(1)) * 60 if hours else 0) + (int(mins.group(1)) if mins else 0)


for _recipe in RECIPES:
    _kind = _recipe["type"]
    _recipe["cuisine"] = _kind if _kind in CUISINES else "Home-style"

    _feelings = set()
    if _kind == "Comfort":
        _feelings.add("Cozy and comforting")
    if _kind == "Light and fresh":
        _feelings.add("Light and fresh")
    if _kind == "Breakfast":
        _feelings.add("Breakfast")
    if cooking_minutes(_recipe["time"]) <= 30:
        _feelings.add("Quick and easy")
    for _feeling, _names in EXTRA_FEELINGS.items():
        if _recipe["name"] in _names:
            _feelings.add(_feeling)
    _recipe["feelings"] = [f for f in FEELINGS if f in _feelings]

_all_names = {r["name"] for r in RECIPES}
assert all(names <= _all_names for names in EXTRA_FEELINGS.values()), "typo in EXTRA_FEELINGS"


# ---------------------------------------------------------------------------
# 3b. Food restrictions (common allergies and intolerances)
#     A recipe is flagged when any word below appears in its ingredients,
#     pantry items or the products matched to it. This is a best guess from
#     product names only, so people with allergies must still read the labels.
# ---------------------------------------------------------------------------

RESTRICTIONS = {
    "Dairy / lactose": ["milk", "cream", "butter", "cheese", "yogurt", "peppercorn sauce"],
    "Gluten / wheat": ["pasta", "spaghetti", "flour", "breadcrumbs", "bread", "tortilla", "tortillas",
                       "soy sauce", "hoisin", "sausage", "sausages", "peppercorn sauce"],
    "Eggs": ["egg", "eggs", "coleslaw", "dressing", "mayo", "mayonnaise"],
    "Peanuts": ["peanut", "peanuts"],
    "Tree nuts": ["cashew", "cashews", "almond", "almonds", "walnut", "walnuts", "pecan", "pecans"],
    "Soy": ["soy", "hoisin", "tofu"],
    "Fish": ["salmon", "trout", "fish", "tuna", "cod"],
    "Shellfish": ["shrimp", "crab", "lobster", "scallop", "scallops"],
    "Sesame": ["sesame"],
    "Pork": ["pork", "bacon", "ham", "sausage", "sausages"],
}


def allergens_in(texts):
    """Which restriction groups does this text mention? Returns a set of names."""
    words = " ".join(texts).lower().replace("coconut milk", " ")  # coconut milk isn't dairy
    padded = " " + " ".join(re.findall(r"[a-z0-9%]+", words)) + " "
    return {
        name for name, keywords in RESTRICTIONS.items()
        if any(" " + kw + " " in padded for kw in keywords)
    }


# ---------------------------------------------------------------------------
# 3. Matching recipes, pricing them, and checking the budget
# ---------------------------------------------------------------------------

def build_recipe_result(recipe, items, selected_names):
    """Match each recipe slot to the cheapest product (in any store given) and total it up.

    Returns None if the recipe can't be made from this week's specials.
    """
    lines = []
    used_ids = set()
    selected_used = set()

    for ingredient in recipe["ingredients"]:
        candidates = [
            item for item in items
            if item["id"] not in used_ids
            and any(word in item["match"] for word in ingredient["keywords"])
        ]
        if not candidates:
            return None  # a required ingredient isn't on special this week

        # Prefer products the user picked; otherwise take the cheapest match.
        preferred = [c for c in candidates if c["broad"] in selected_names]
        chosen = min(preferred or candidates, key=lambda c: c["price"])

        used_ids.add(chosen["id"])
        if chosen["broad"] in selected_names:
            selected_used.add(chosen["broad"])

        lines.append({
            "label": ingredient["label"],
            "item": chosen,
            "user_pick": chosen["broad"] in selected_names,
        })

    total = round(sum(line["item"]["price"] for line in lines), 2)
    saved = round(sum(line["item"]["money_saved"] for line in lines), 2)
    servings = recipe["servings"]

    allergens = allergens_in(
        [line["label"] for line in lines]
        + [line["item"]["match"] for line in lines]
        + recipe["pantry"]
    )

    return {
        "recipe": recipe,
        "allergens": sorted(allergens),
        "lines": lines,
        "stores": sorted({line["item"]["store"] for line in lines}),
        "total": total,
        "servings": servings,
        "per_meal": round(total / servings, 2),
        "saved": saved,
        "regular_price": round(total + saved, 2),
        "selected_used": selected_used,
    }


def popular_ingredients(groups, count=3):
    """The ingredients that fit the most recipes (ties go to the bigger saving)."""
    def uses(group):
        return sum(
            any(any(word in match for word in ing["keywords"])
                for ing in recipe["ingredients"] for match in group["matches"])
            for recipe in RECIPES
        )

    ranked = sorted(groups, key=lambda g: (-uses(g), -g["money_saved"], g["price"]))
    return [g["name"] for g in ranked[:count] if uses(g) > 0]


# Sort choices: key in the form -> (label, result field, biggest first?)
SORTS = {
    "meal_low": ("Price per meal: cheapest first", "per_meal", False),
    "meal_high": ("Price per meal: most expensive first", "per_meal", True),
    "total_low": ("Total price: cheapest first", "total", False),
    "total_high": ("Total price: most expensive first", "total", True),
}


def find_recipes(items, selected_names, cuisine, feeling, budget, restrictions=(), sort=""):
    results = []

    for recipe in RECIPES:
        if cuisine and recipe["cuisine"] != cuisine:
            continue
        if feeling and feeling not in recipe["feelings"]:
            continue

        result = build_recipe_result(recipe, items, selected_names)
        if result is None:
            continue

        # What the same recipe would cost if you did all your shopping at one store.
        single = []
        for store in sorted({item["store"] for item in items}):
            one_store = build_recipe_result(
                recipe, [i for i in items if i["store"] == store], selected_names)
            if one_store:
                single.append((store, one_store["total"]))
        result["single_store"] = sorted(single, key=lambda pair: pair[1])

        if set(restrictions) & set(result["allergens"]):
            continue  # contains something the user avoids

        if budget is None:
            result["fits"] = True
            result["over_by"] = 0.0
            result["left"] = None
        else:
            result["fits"] = result["total"] <= budget
            result["over_by"] = round(max(result["total"] - budget, 0), 2)
            result["left"] = round(max(budget - result["total"], 0), 2)

        results.append(result)

    if sort in SORTS:
        _, field, biggest_first = SORTS[sort]
        results.sort(key=lambda r: r[field], reverse=biggest_first)
        return results

    # Best first: fits the budget, uses most of your picks (picks are only suggestions), saves the most money.
    results.sort(key=lambda r: (
        not r["fits"],
        -len(r["selected_used"]),
        r["over_by"],
        -r["saved"],
        r["total"],
    ))
    return results


def parse_budget(text):
    number = to_number(text)
    return number if number and number > 0 else None


# ---------------------------------------------------------------------------
# 4. The page
# ---------------------------------------------------------------------------

@app.route("/")
def home():
    all_items = load_ingredients()

    # Which stores to shop at (all of them until the user narrows it down).
    chosen_stores = [st for st in request.args.getlist("stores") if st in STORES]
    active_stores = chosen_stores or [st for st in STORES if any(i["store"] == st for i in all_items)]
    items = [i for i in all_items if i["store"] in active_stores]

    ingredients = group_ingredients(items)
    popular_names = set(popular_ingredients(ingredients))

    searched = "food_type" in request.args  # form was submitted
    selected_names = set(request.args.getlist("ingredients"))
    # One "Type of food" dropdown holding two sub-lists, e.g. "cuisine:Italian" or "feeling:Quick and easy".
    food_type = request.args.get("food_type", "")
    kind, _, value = food_type.partition(":")
    cuisine = value if kind == "cuisine" and value in CUISINES else ""
    feeling = value if kind == "feeling" and value in FEELINGS else ""
    if not (cuisine or feeling):
        food_type = ""
    budget_text = request.args.get("budget", "").strip()
    budget = parse_budget(budget_text)
    restrictions = [r for r in request.args.getlist("restrictions") if r in RESTRICTIONS]
    sort = request.args.get("sort", "")
    if sort not in SORTS:
        sort = ""

    results = []
    unused_picks = []
    hidden_count = 0
    if searched:
        results = find_recipes(items, selected_names, cuisine, feeling, budget, restrictions, sort)
        hidden_count = len(find_recipes(items, selected_names, cuisine, feeling, budget)) - len(results)
        used = set().union(*(r["selected_used"] for r in results)) if results else set()
        unused_picks = [g["name"] for g in ingredients
                        if g["name"] in selected_names and g["name"] not in used]

    return render_template(
        "index.html",
        ingredients=ingredients,
        popular_names=popular_names,
        cuisines=CUISINES,
        feelings=FEELINGS,
        searched=searched,
        selected_names=selected_names,
        food_type=food_type,
        cuisine=cuisine,
        feeling=feeling,
        budget_text=budget_text,
        sort=sort,
        sorts={key: label for key, (label, _, _) in SORTS.items()},
        budget=budget,
        results=results,
        within=[r for r in results if r["fits"]],
        over=[r for r in results if not r["fits"]],
        unused_picks=unused_picks,
        restriction_names=list(RESTRICTIONS),
        restrictions=restrictions,
        hidden_count=hidden_count,
        store_logos={store: f for store, f in STORE_LOGOS.items() if (BASE_DIR / "static" / f).exists()},
        store_names=list(STORES),
        active_stores=active_stores,
    )


if __name__ == "__main__":
    app.run(debug=True, port=5000)