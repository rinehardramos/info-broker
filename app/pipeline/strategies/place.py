"""Place / route / navigation investigation strategy module."""

ENTITY_TYPE = "place"

STRATEGY = """
=== PLACE / ROUTE / NAVIGATION STRATEGY ===

goal: Provide accurate, actionable route guidance including LOCAL shortcuts invisible to official mapping apps.
execution_model: log_cycle(PIR + hypotheses) → BROADEN(≥1 search/hypothesis) → RANK → RECURSE → DELIVER

--- PIR TEMPLATE ---

PIR: What is the fastest or most practical route between these two points, including local shortcuts?
MANDATORY: At least one complete walkable/commutable path confirmed with landmarks | Local shortcut branches searched, not just official roads
SUPPORTING: Walking time estimates | Foot-traffic conditions | Named landmarks as waypoints
REJECT IF: Only official mapping data searched with no local knowledge check

--- HYPOTHESIS TABLE ---

H1 (official route): Main roads, official bridges, transit stops as shown on Google Maps / Moovit / OSM
  search: "[origin] to [destination] walking route" | "[bridge name] pedestrian access [year]"
  tools: run_web_search | run_web_crawl(OpenStreetMap)

H2 (local compound shortcuts): Residential compounds, housing projects, and named buildings that allow pedestrian cut-through
  TRIGGER: Any route passing through or near a barangay — always check for compound shortcuts
  search: "[barangay name] [compound name e.g. BLISS, subdivision, condo] shortcut pedestrian access"
  search: "[barangay] daan shortcut walking path" | "cut through [compound] [barangay]"
  PH-specific compounds to check: BLISS housing, NHA projects, Pag-IBIG subdivisions, BF Homes, MRB, government housing
  Note: BLISS (Better Living in Slum Sites) projects in Hulo, Mandaluyong; Bagong Ilog, Pasig; etc. are KNOWN pedestrian shortcuts locals use daily

H3 (community-documented shortcuts): Informal paths and tawiran documented by locals on social media, forums, community apps
  search: "[origin barangay] to [destination barangay] shortcut" site:reddit.com OR site:facebook.com
  search: "shortcut [street name] [barangay]" | "[landmark] tawid shortcut"
  search: Waze reports, Komyut app, PinoyExchange commuter threads, Facebook community groups
  Note: Locals document "lihim na daan" (hidden paths), bridge underpass access, railway shortcuts

H_last (time-of-day variants): Rush hour paths differ from off-peak — some shortcuts close, some open
  search: "[route] peak hour walking" | "[compound/area] open 24 hours pedestrian" | "[bridge] closed maintenance [year]"
  Check: Flood-prone areas that are impassable during rainy season

--- MANDATORY LOCAL-SHORTCUT BRANCH ---

For EVERY route query passing through a Philippine barangay or urban area:

1. Identify named compounds within 500m of each waypoint:
   - Search: "[barangay name] BLISS" | "[barangay name] housing project" | "[barangay name] compound shortcut"
   - Search: "[street name] cut-through" | "[origin] to [destination] tawid" | "paano makarating [destination] mula [origin]"

2. Check for pedestrian infrastructure invisible to routing apps:
   - Overpasses / underpasses not indexed by Google Maps
   - Footbridges over esteros or canals
   - Alleys ("eskinita") connecting parallel streets
   - Building lobbies open for pedestrian pass-through

3. Check community sources for local knowledge:
   - Facebook groups: "[barangay/city] commuters", "[city] riders and commuters"
   - Reddit: r/Philippines, r/Makati, r/Mandaluyong walking threads
   - PinoyExchange forum: transportation & commuting section
   - Waze map editor community edits in the area

--- PH-SPECIFIC ROUTE CONTEXT ---

BRIDGES crossing Pasig River (south to north):
  - Guadalupe → Estrella-Pantaleon → Makati-Mandaluyong → Lambingan → Nagtahan
  Known pedestrian shortcuts at Makati-Mandaluyong Bridge:
    - BLISS housing complex in Hulo (north bank) provides cut-through to interior Mandaluyong
    - Coronado Street north side has informal path connecting to Shaw Boulevard direction
    - Barangay Hulo eskinitas connect Coronado to Libertad Street

FLOOD ADVISORY: Check if shortcuts are on low-lying ground — flood season (June–October) may close them.

tools: run_web_search | run_web_crawl | run_google_news | run_multi_search
"""
