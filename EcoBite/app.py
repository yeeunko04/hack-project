import csv
import re
from pathlib import Path

from flask import Flask, render_template, request

app = Flask(__name__)

BASE_DIR = Path(__file__).resolve().parent
CSV_FILE = BASE_DIR / "data" / "maxi_weekly_grocery_specials.csv"


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


def load_ingredients():
    """Read the weekly specials. Every product gets a unique id (its row number)."""
    items = []

    with open(CSV_FILE, "r", encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file)

        for row in reader:
            row = {
                key.strip().lower().replace("_", " "): (value or "").strip()
                for key, value in row.items()
                if key is not None
            }

            name = row.get("item name")
            price = to_number(row.get("item price"))
            if not name or price is None:
                continue  # skip rows we can't price

            items.append({
                "id": len(items),
                "category": row.get("category", "Other"),
                "name": name,
                "price": price,
                "unit_price": unit_price_label(row.get("item price per kg")),
                "money_saved": to_number(row.get("money saved")) or 0.0,
            })

    return items


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
        "ingredients": [
            slot("Italian sausage", "italian pork sausages"),
            slot("Tomatoes", "tomato"),
            slot("Garlic", "chopped garlic"),
            slot("Olive oil", "olive oil"),
            slot("Fresh basil", "fresh basil"),
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
        "ingredients": [
            slot("Ground chicken", "ground chicken"),
            slot("Tomatoes", "tomato"),
            slot("Garlic", "chopped garlic"),
            slot("Olive oil", "olive oil"),
            slot("Fresh basil", "fresh basil"),
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
        "ingredients": [
            slot("Steelhead trout", "steelhead trout"),
            slot("Potatoes", "yellow potato"),
            slot("Garlic", "chopped garlic"),
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
        "ingredients": [
            slot("Ground chicken", "ground chicken"),
            slot("Cabbage", "green cabbage"),
            slot("Garlic", "chopped garlic"),
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
        "ingredients": [
            slot("Chicken legs", "chicken leg"),
            slot("Coconut milk", "coconut milk"),
            slot("Garlic", "chopped garlic"),
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
        "ingredients": [
            slot("Boneless blade roast", "blade roast"),
            slot("Potatoes", "yellow potato"),
            slot("Acorn squash", "acorn squash"),
            slot("Garlic", "chopped garlic"),
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
        "ingredients": [
            slot("Chicken legs", "chicken leg"),
            slot("BBQ sauce", "bar-b-q"),
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
        "ingredients": [
            slot("Bacon", "choice bacon"),
            slot("Potatoes", "yellow potato"),
            slot("Milk", "1% milk", "2% milk", "homogenized milk", "skim milk"),
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
        "ingredients": [
            slot("Honey garlic sausages", "honey garlic flavoured pork sausages"),
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
        "ingredients": [
            slot("Pork tenderloin", "pork tenderloin"),
            slot("Mushrooms", "mushrooms"),
            slot("Garlic", "chopped garlic"),
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
        "ingredients": [
            slot("Tomatoes", "tomato"),
            slot("Avocado", "avocado"),
            slot("Fresh basil", "fresh basil"),
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
        "ingredients": [
            slot("Bacon", "choice bacon"),
            slot("Mushrooms", "mushrooms"),
            slot("Milk", "1% milk", "2% milk", "homogenized milk", "skim milk"),
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
]

FOOD_TYPES = sorted({r["type"] for r in RECIPES})


# ---------------------------------------------------------------------------
# 3. Matching recipes, pricing them, and checking the budget
# ---------------------------------------------------------------------------

def build_recipe_result(recipe, items, selected_ids):
    """Match each recipe slot to a product and total up price and savings.

    Returns None if the recipe can't be made from this week's specials.
    """
    lines = []
    used_ids = set()
    selected_used = set()

    for ingredient in recipe["ingredients"]:
        candidates = [
            item for item in items
            if item["id"] not in used_ids
            and any(word in item["name"].lower() for word in ingredient["keywords"])
        ]
        if not candidates:
            return None  # a required ingredient isn't on special this week

        # Prefer products the user picked; otherwise take the cheapest match.
        preferred = [c for c in candidates if c["id"] in selected_ids]
        chosen = min(preferred or candidates, key=lambda c: c["price"])

        used_ids.add(chosen["id"])
        if chosen["id"] in selected_ids:
            selected_used.add(chosen["id"])

        lines.append({
            "label": ingredient["label"],
            "item": chosen,
            "user_pick": chosen["id"] in selected_ids,
        })

    total = round(sum(line["item"]["price"] for line in lines), 2)
    saved = round(sum(line["item"]["money_saved"] for line in lines), 2)

    return {
        "recipe": recipe,
        "lines": lines,
        "total": total,
        "saved": saved,
        "regular_price": round(total + saved, 2),
        "selected_used": selected_used,
    }


def find_recipes(items, selected_ids, food_type, budget):
    results = []

    for recipe in RECIPES:
        if food_type and recipe["type"] != food_type:
            continue

        result = build_recipe_result(recipe, items, selected_ids)
        if result is None:
            continue

        # If the user picked ingredients, the recipe must use at least one.
        if selected_ids and not result["selected_used"]:
            continue

        if budget is None:
            result["fits"] = True
            result["over_by"] = 0.0
            result["left"] = None
        else:
            result["fits"] = result["total"] <= budget
            result["over_by"] = round(max(result["total"] - budget, 0), 2)
            result["left"] = round(max(budget - result["total"], 0), 2)

        results.append(result)

    # Best first: fits the budget, uses most of your picks, saves the most money.
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
    items = load_ingredients()

    # Group products by category for the checklist (keeps CSV order).
    grouped = {}
    for item in items:
        grouped.setdefault(item["category"], []).append(item)

    searched = "food_type" in request.args  # form was submitted
    selected_ids = set(request.args.getlist("ingredients", type=int))
    food_type = request.args.get("food_type", "")
    budget_text = request.args.get("budget", "").strip()
    budget = parse_budget(budget_text)

    results = []
    unused_picks = []
    if searched:
        results = find_recipes(items, selected_ids, food_type, budget)
        used = set().union(*(r["selected_used"] for r in results)) if results else set()
        unused_picks = [i for i in items if i["id"] in selected_ids and i["id"] not in used]

    return render_template(
        "index.html",
        grouped=grouped,
        food_types=FOOD_TYPES,
        searched=searched,
        selected_ids=selected_ids,
        food_type=food_type,
        budget_text=budget_text,
        budget=budget,
        results=results,
        within=[r for r in results if r["fits"]],
        over=[r for r in results if not r["fits"]],
        unused_picks=unused_picks,
    )


if __name__ == "__main__":
    app.run(debug=True, port=5000)