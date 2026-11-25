"""Schema (DDL + integrity triggers) and connect()."""
import sqlite3

SCHEMA = """
CREATE TABLE meta(key TEXT PRIMARY KEY, value TEXT NOT NULL);

CREATE TABLE locations(
  id TEXT PRIMARY KEY, name TEXT NOT NULL,
  kind TEXT NOT NULL CHECK (kind IN ('street','building','wild')),
  tags TEXT NOT NULL DEFAULT '[]', owner_id TEXT, is_public INT NOT NULL DEFAULT 1,
  safety INT NOT NULL DEFAULT 2 CHECK (safety BETWEEN 0 AND 3), lit INT NOT NULL DEFAULT 1,
  crowd INT NOT NULL DEFAULT 0 CHECK (crowd BETWEEN 0 AND 2), cover INT NOT NULL DEFAULT 0);

CREATE TABLE doors(
  id TEXT PRIMARY KEY, name TEXT NOT NULL, lock_dc INT, locked INT NOT NULL DEFAULT 0,
  is_open INT NOT NULL DEFAULT 0, key_item_id TEXT);

CREATE TABLE connections(
  from_id TEXT NOT NULL REFERENCES locations, to_id TEXT NOT NULL REFERENCES locations,
  door_id TEXT REFERENCES doors, PRIMARY KEY (from_id, to_id));

CREATE TABLE housing_tiers(tier INT PRIMARY KEY, windows INT, doors INT, lock_dc INT, cellar INT);

CREATE TABLE buildings(
  location_id TEXT PRIMARY KEY REFERENCES locations, tier INT REFERENCES housing_tiers,
  owner_id TEXT, cosmetic TEXT, wealth_display INT CHECK (wealth_display BETWEEN 1 AND 5), image_ref TEXT);

CREATE TABLE characters(
  id TEXT PRIMARY KEY, name TEXT NOT NULL, is_npc INT NOT NULL, role TEXT,
  location_id TEXT NOT NULL REFERENCES locations,
  status TEXT NOT NULL CHECK (status IN ('online','afk','offline','dead')),
  hp INT NOT NULL, max_hp INT NOT NULL, xp INT NOT NULL DEFAULT 0,
  coins INT NOT NULL DEFAULT 0 CHECK (coins >= 0),
  stats TEXT NOT NULL, skills TEXT NOT NULL DEFAULT '{}', skill_points INT NOT NULL DEFAULT 0,
  face_shape TEXT NOT NULL, appearance TEXT NOT NULL DEFAULT '{}', wanted_level INT NOT NULL DEFAULT 0,
  hidden INT NOT NULL DEFAULT 0, hidden_event INT, stealth_total INT);

CREATE TABLE reputation(
  character_id TEXT REFERENCES characters, scope TEXT, value INT NOT NULL DEFAULT 0,
  PRIMARY KEY (character_id, scope));

CREATE TABLE items(
  id TEXT PRIMARY KEY, type TEXT NOT NULL, name TEXT NOT NULL, aliases TEXT NOT NULL DEFAULT '[]',
  properties TEXT NOT NULL DEFAULT '{}', price INT,
  location_id TEXT REFERENCES locations, holder_id TEXT REFERENCES characters,
  flags TEXT NOT NULL DEFAULT '[]',
  CHECK ((location_id IS NULL) <> (holder_id IS NULL)));

CREATE TABLE provenance(
  id INTEGER PRIMARY KEY AUTOINCREMENT, item_id TEXT NOT NULL REFERENCES items,
  kind TEXT NOT NULL CHECK (kind IN ('created','bought','sold','gifted','given','dropped','taken',
                                     'stolen','looted','traded','transformed')),
  from_id TEXT, to_id TEXT, location_id TEXT, time INT NOT NULL, event_id INT);

CREATE TABLE events(
  id INTEGER PRIMARY KEY AUTOINCREMENT, time INT NOT NULL, actor_id TEXT NOT NULL, verb TEXT NOT NULL,
  target_id TEXT, item_id TEXT, location_id TEXT NOT NULL, outcome TEXT NOT NULL, crime TEXT,
  data TEXT NOT NULL DEFAULT '{}');

CREATE TABLE perceptions(
  event_id INT NOT NULL, observer_id TEXT NOT NULL, detected INT NOT NULL, recognized INT NOT NULL,
  appearance_seen TEXT, roll_id INT, PRIMARY KEY (event_id, observer_id));

CREATE TABLE traces(
  id INTEGER PRIMARY KEY AUTOINCREMENT, event_id INT NOT NULL,
  kind TEXT NOT NULL CHECK (kind IN ('bloodied_item','item_left','forced_lock','purchase','body')),
  item_id TEXT, location_id TEXT NOT NULL, detail TEXT NOT NULL DEFAULT '{}');

CREATE TABLE knowledge(
  id INTEGER PRIMARY KEY AUTOINCREMENT, observer_id TEXT NOT NULL, subject_id TEXT NOT NULL,
  fact TEXT NOT NULL CHECK (fact IN ('aware_of','seen_at','knows_identity','knows_crime')),
  location_id TEXT, time INT NOT NULL, event_id INT);

CREATE TABLE dice_log(
  id INT PRIMARY KEY, time INT, event_id INT, actor_id TEXT, purpose TEXT NOT NULL, sides INT NOT NULL,
  raw TEXT NOT NULL, mode TEXT NOT NULL CHECK (mode IN ('normal','advantage','disadvantage')),
  modifier INT NOT NULL, total INT NOT NULL, dc INT, success INT);

CREATE TABLE trades(
  id INTEGER PRIMARY KEY AUTOINCREMENT, from_id TEXT NOT NULL, to_id TEXT NOT NULL,
  give_items TEXT NOT NULL DEFAULT '[]', give_coins INT NOT NULL DEFAULT 0 CHECK (give_coins >= 0),
  want_items TEXT NOT NULL DEFAULT '[]', want_coins INT NOT NULL DEFAULT 0 CHECK (want_coins >= 0),
  status TEXT NOT NULL CHECK (status IN ('pending','accepted','declined','failed')),
  created INT NOT NULL, resolved INT);

CREATE TABLE inputs(
  id INTEGER PRIMARY KEY AUTOINCREMENT, kind TEXT NOT NULL CHECK (kind IN ('cmd','advance')),
  actor_id TEXT, payload TEXT NOT NULL);

-- evidence: one row per witness (perception) and per physical trace of every crime event
CREATE VIEW evidence AS
  SELECT e.id AS event_id, e.time, e.crime, e.actor_id, e.verb, e.outcome, e.location_id,
         'witness' AS kind, p.observer_id AS subject_id, p.detected, p.recognized, p.roll_id, NULL AS detail
    FROM events e JOIN perceptions p ON p.event_id = e.id WHERE e.crime IS NOT NULL
  UNION ALL
  SELECT e.id, e.time, e.crime, e.actor_id, e.verb, e.outcome, t.location_id,
         t.kind, t.item_id, NULL, NULL, NULL, t.detail
    FROM events e JOIN traces t ON t.event_id = e.id WHERE e.crime IS NOT NULL;

CREATE TRIGGER face_shape_immutable BEFORE UPDATE OF face_shape ON characters
  WHEN NEW.face_shape IS NOT OLD.face_shape
  BEGIN SELECT RAISE(ABORT, 'face_shape is immutable'); END;
"""

# nothing vanishes; history is append-only
SCHEMA += "".join(
    f"CREATE TRIGGER {t}_no_delete BEFORE DELETE ON {t} BEGIN SELECT RAISE(ABORT, '{t} cannot be deleted'); END;\n"
    for t in ("items", "characters", "locations"))
SCHEMA += "".join(
    f"CREATE TRIGGER {t}_no_{op.lower()} BEFORE {op} ON {t} BEGIN SELECT RAISE(ABORT, '{t} is append-only'); END;\n"
    for t in ("events", "provenance", "perceptions", "traces", "knowledge", "dice_log")
    for op in ("UPDATE", "DELETE"))


def connect(path=":memory:"):
    """Autocommit connection (isolation_level=None): callers open transactions explicitly."""
    conn = sqlite3.connect(path, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


def init(conn):
    conn.executescript(SCHEMA)
