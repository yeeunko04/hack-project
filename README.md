# EcoBite

**Cheap, balanced dinners from this week's grocery specials.**

EcoBite is a website that bridges the gap between nutrition and expenses. It is built for young adults and people living alone who want to eat well without overspending. Set a budget, pick what you'd like to cook, and EcoBite returns recipes priced from this week's specials, with the cost per meal, the total cost and how much you save.

## The problem

Eating well on a tight budget is harder than it should be, especially for young adults and people who live alone. Grocery prices keep climbing, and the best deals are buried in separate flyers from every store. Most recipes never say what dinner will actually cost. Cooking for one also means buying more food than you need, and allergies or intolerances narrow your choices even further. Many people end up spending more on takeout, or skipping balanced meals altogether, because planning a cheap, safe dinner takes more time and effort than they have.

EcoBite does that planning for you. It turns this week's specials into dinner ideas you can afford, with the price of every meal shown up front.

## What it does

- **Budget slider:** choose anywhere from $0 (no limit) to $200. Recipes that fit your budget are listed first, and the rest are shown separately.
- **Price per meal:** each recipe shows the cost of one serving in large type, with the total ingredient cost below it and what you save compared with regular prices.
- **Compares stores:** tick Maxi, Super C and Walmart. Every ingredient is priced at the cheapest matching special across your chosen stores, and each recipe shows what it would cost if you shopped at only one.
- **Ingredient suggestions:** a search box with suggested ingredients you can click to add. Similar meats are grouped (picking "Chicken" covers every cut), while recipes name the exact cut. Your picks are only suggestions and never hide recipes.
- **Food restrictions:** avoid dairy / lactose, gluten / wheat, eggs, peanuts, tree nuts, soy, fish, shellfish, sesame or pork. Matching recipes are hidden and each card lists what it contains.
- **Type of food:** browse by cuisine (Italian, Asian, Mexican, Home-style) or by feeling (Cozy and comforting, Light and fresh, Quick and easy, Breakfast).
- **Sort recipes:** by price per meal or total price, cheapest or most expensive first.
- **Recipe cards in 4 columns:** expand "Ingredients and prices" to see which product to buy at which store, and "How to make it" for the steps.
- **Recipes from the web:** some recipes link straight to the original website.

## Impact

EcoBite helps people balance time, money and health in everyday life. It makes budget-friendly cooking easier for students, newcomers and anyone living alone.

## Run it locally

You need Python 3.10 or newer.

```bash
pip install -r requirements.txt
cd EcoBite
python app.py
```

Then open <http://127.0.0.1:5000> in your browser. Stop the server with `Ctrl+C`.

## How it works

- `EcoBite/app.py` is a small [Flask](https://flask.palletsprojects.com/) app. It reads each store's weekly specials from `EcoBite/data/`, matches products to recipe ingredients by keyword, prices every recipe, and applies your filters.
- `EcoBite/templates/index.html` and `EcoBite/static/style.css` are the page and its styling. There is no database, because prices come from CSV files that are re-read on every page load.

```
EcoBite/
  app.py            routes, recipes, matching and pricing
  data/             one weekly-specials CSV per store
  static/           stylesheet and logos
  templates/        the page
requirements.txt
```

### Adding or updating prices

Each store has a CSV in `EcoBite/data/` with these columns:

```
Category,Item name,Item price,Item price per kg,Money saved
```

Edit a file and refresh the page. To add another store, drop its CSV in `EcoBite/data/` and add one line to `STORES` at the top of `app.py`. Product names are mapped to short ingredient names with `SIMPLE_PATTERNS` in `app.py`, which is how different stores' products are compared.

### Adding recipes

Add an entry to `RECIPES` in `app.py` with its ingredients (matched by keyword), pantry items, servings, time and steps. Add a `url` and `source` to link out to an original recipe.

## Limitations

- **Sample prices:** the CSV files are sample data and not live prices. EcoBite does not scrape store websites.
- **Allergen filters are a best guess** from product and ingredient names. They cannot read labels. If you have an allergy, always check the package.
- **No nutrition data yet.** Recipes are tagged by cuisine and feeling, but calories, macros and portions are not calculated.
- Prices are for the whole package as sold, so you may have leftovers.
- Store logos belong to their owners and are used here for demonstration only.

## Future vision

- Nutrition goals: filter and rank recipes by nutrients, not only price.
- Live weekly prices from store flyers.
- Portions and leftovers planning.
- Expand internationally, with more stores, currencies and cuisines.

## Built with

Python, Flask, HTML, CSS and JavaScript.
