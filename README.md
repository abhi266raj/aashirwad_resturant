# aashirwad_resturant

A separate static HTML, CSS and JavaScript restaurant website for Hazaribagh. The existing `aashirwad` repository is untouched.

## Shared configuration

Both Python scripts read `scripts/config.json`. Its `sheet.url` is the private spreadsheet link, `sheet.name` is the worksheet/tab name (currently `Menu2`), and `sheet.spreadsheet_title` is the workbook title. Image dimensions are defined by the menu layout in the updater code. Credentials never belong in this file.

## Scripts

- `python3 scripts/create_schema.py`: run locally with Google edit access to configure the sheet's columns, strict dropdowns, validation, and formatting. It preserves existing dishes and IDs. Use `--seed` only for an empty menu. Use `--new --spreadsheet-title "Workbook title" --sheet-name "Menu2"` to create a spreadsheet; successful creation saves its URL in the shared configuration.
- `python3 scripts/update.py`: reads the private sheet with read-only access, downloads supplied image URLs, resizes and compresses them, and updates the static files in `site/`. It never assigns or validates dish IDs.

Both accept `--sheet-url` and `--tab` overrides. `--csv data/menu-template.csv` lets the updater use the included starter data without Google authentication. All Python implementation code is under `scripts/`; tests are under `tests/`.

## Authentication

Run `python3 scripts/setup.py` once. Both functional scripts also invoke setup automatically if dependencies are missing. Setup creates a project `.venv`, verifies its packages, and reuses it on later runs. For local setup, supply an authorized Google user credential through `GOOGLE_OAUTH_TOKEN_JSON`, or an Editor service account credential through `GOOGLE_SERVICE_ACCOUNT_JSON`. For creation in your personal Drive, use your own authorized user credential. These credentials must be provisioned once; the Google authentication library obtains and refreshes short-lived access tokens automatically.

For GitHub, share this sheet with a dedicated service account as **Viewer**, then store its JSON credential in the repository Actions secret `GOOGLE_SERVICE_ACCOUNT_JSON`. The sheet stays private. The updater uses only the Sheets read-only scope. No Apps Script is used.

## Editing the menu

Each row is a dish. Add rows freely and choose a category from the dropdown. To add categories, edit `sheet.categories` in `scripts/config.json` and rerun the local setup script. Columns are `id`, `name`, `category`, `price`, `diet`, `description`, `popular`, `image`, `sort_priority`.

Google Sheets enforces unique positive numeric IDs, positive whole rupee prices, Veg/Non-Veg choices, Yes/No choices, optional HTTPS image links and non-negative whole sort prioritys when the setup script applies the schema. Existing IDs are stored values and move with their dishes. Enter a new permanent ID as one greater than the highest current ID. Native formulas cannot safely assign permanent IDs automatically. Python reads ID values without checking or changing them.

The `image` column accepts a public HTTP(S) image URL or a path under `site/assets/`. Leave it blank to try a name-matched image and then a generic placeholder. Downloaded photos are optimized progressive JPEGs, preserve aspect ratio and are never upscaled. The code uses an 800×600 maximum and quality 78 to support menu cards up to about 400 CSS pixels at 2x density.

## Deploy

The workflow **Deploy aashirwad_resturant** runs on pushes to `main` or through **Run workflow**. There is no schedule. It runs only the updater, commits generated JSON/images, and deploys `site/` to GitHub Pages. Choose **GitHub Actions** in repository Settings → Pages. The intended URL is `https://abhi266raj.github.io/aashirwad_resturant/`.

A failed fetch, invalid non-ID menu data or failed image download stops deployment; the previous live site remains available. The site exposes only generated menu data and local images, with no Google credential or sheet link in the deployed files. A public source repository would expose `scripts/config.json`, including its sheet URL; Google sharing permissions still control access.

For local preview, serve `site/` with any static file server. No Python process runs on GitHub Pages. Customers browse, filter, add dishes to a cart and send orders to `+91 70042 30188` by WhatsApp or SMS.

Duplicate sort prioritys are allowed. The display sorts by sort priority and keeps sheet row order for equal priorities; sorting never assigns or changes IDs.

Blank sort priorities default to the highest existing explicit priority, without incrementing it. Equal priorities follow sheet row order. These defaults are generated without writing to the sheet.

Double-click the root `index.html` or `site/index.html` for local viewing. The updater generates `menu-snapshot.js` alongside JSON for direct file access. Both local and hosted pages render the generated menu snapshot without runtime JSON requests. Styling still loads the existing Tailwind CDN and Google Fonts, so full styling requires internet access.

Manual cleanup: run `python3 scripts/update.py --clear-unused-assets --dry-run` to preview, then `python3 scripts/update.py --clear-unused-assets` to remove unused images. It uses the saved menu and static site references, requires no Google credentials, and preserves referenced photos, logos and placeholders. Run an update first when the sheet has changed.
