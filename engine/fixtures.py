"""Demo world "Mill Street", used by tests and the REPL. Plain data; world.load_fixture() writes it."""


def _char(id, name, location_id, **kw):
    c = dict(id=id, name=name, is_npc=1, role=None, location_id=location_id, status="online", hp=10, max_hp=10,
             coins=0, stats=dict(str=10, dex=10, con=10, int=10, wis=10, cha=10), skills={}, face_shape="oval",
             appearance={})
    c.update(kw)
    return c


_CHARACTERS = [
    _char("player", "Ash", "tavern", is_npc=0, hp=11, max_hp=11, coins=30,
          stats=dict(str=12, dex=14, con=12, int=10, wis=12, cha=10),
          skills=dict(stealth=2, perception=2, sleight=2, athletics=1, lockpicking=2),
          face_shape="angular", appearance=dict(hair="short black hair", clothes="a green cloak")),
    _char("bob", "Bob", "tavern", role="townsperson", coins=20, face_shape="round",
          appearance=dict(hair="balding", clothes="a stained apron")),
    _char("wren", "Wren", "tavern", role="traveller", coins=5, stats=dict(str=10, dex=12, con=10, int=10, wis=8, cha=10),
          face_shape="narrow", appearance=dict(hair="hidden", clothes="a hooded grey cloak")),
    _char("herbalist", "Mira", "shop", role="merchant", coins=50, stats=dict(str=8, dex=10, con=10, int=12, wis=12, cha=12),
          skills=dict(perception=2), face_shape="heart", appearance=dict(hair="long red braid", clothes="a leaf-green dress")),
    _char("guard", "Gareth", "street", role="guard", hp=12, max_hp=12,
          stats=dict(str=14, dex=12, con=14, int=10, wis=14, cha=10), skills=dict(perception=8, athletics=3),
          face_shape="square", appearance=dict(hair="cropped grey", clothes="a town guard tabard")),
    _char("tom", "Tom", "street", role="miller", coins=15, skills=dict(perception=1), face_shape="long",
          appearance=dict(hair="flour-dusted", clothes="a miller's smock")),
]

MILL_STREET = {
    "clock": 12 * 60,  # noon on day 0
    "housing_tiers": [dict(tier=1, windows=1, doors=1, lock_dc=15, cellar=0),
                      dict(tier=2, windows=2, doors=1, lock_dc=12, cellar=1)],
    "locations": [
        dict(id="street", name="Mill Street", kind="street", tags=["street", "outside", "road"], lit=1, crowd=1, cover=1),
        dict(id="tavern", name="The Rusty Tankard", kind="building", tags=["tavern", "inn", "pub"], lit=1, crowd=2, cover=1),
        dict(id="shop", name="Mira's Herbs", kind="building", tags=["herbalist", "shop", "herbs"]),
        dict(id="player_house", name="Ash's House", kind="building", tags=["home"], owner_id="player",
             is_public=0, safety=3, lit=0, cover=2),
        dict(id="tom_house", name="Tom's House", kind="building", tags=["miller's house"], owner_id="tom",
             is_public=0, lit=0, cover=2),
        dict(id="guard_post", name="Guard Post", kind="building", tags=["barracks", "post"], safety=3),
    ],
    "doors": [dict(id="player_door", name="green door", lock_dc=15, locked=1, is_open=0, key_item_id="player_key"),
              dict(id="tom_door", name="oak door", lock_dc=12, locked=1, is_open=0, key_item_id="tom_key")],
    "connections": [("street", "tavern", None), ("street", "shop", None), ("street", "guard_post", None),
                    ("street", "player_house", "player_door"), ("street", "tom_house", "tom_door")],
    "buildings": [dict(location_id="player_house", tier=1, owner_id="player", wealth_display=2,
                       cosmetic="A narrow timber house with a green door."),
                  dict(location_id="tom_house", tier=2, owner_id="tom", wealth_display=3,
                       cosmetic="A whitewashed cottage that smells of flour.")],
    "characters": _CHARACTERS,
    "items": [
        dict(id="knife", type="weapon", name="knife", aliases=["blade", "dagger"], properties=dict(damage=4, spot="table"),
             location_id="tavern"),
        dict(id="lockpick", type="lockpick", name="bent lockpick", aliases=["pick"], location_id="street"),
        dict(id="player_key", type="key", name="house key", aliases=["key"], holder_id="player"),
        dict(id="tom_key", type="key", name="iron key", aliases=["key"], holder_id="tom"),
        dict(id="watch", type="valuable", name="pocket watch", properties=dict(value=25), holder_id="bob"),
        dict(id="poison", type="poison", name="vial of nightshade", aliases=["poison", "nightshade"], price=15,
             properties=dict(poison=1), holder_id="herbalist"),
        dict(id="potion", type="potion", name="healing potion", aliases=["potion"], price=10, holder_id="herbalist",
             properties=dict(on_use=dict(effect="heal", amount=5,
                                         becomes=dict(type="vial", name="empty vial", aliases=["vial"])))),
        dict(id="sword", type="weapon", name="sword", properties=dict(damage=8), holder_id="guard"),
        dict(id="leather", type="armor", name="leather armor", aliases=["armor"], properties=dict(armor=2),
             holder_id="guard"),
        dict(id="plate", type="armor", name="plate armor", aliases=["armor", "plate"], properties=dict(armor=5, heavy=1),
             location_id="player_house"),
        dict(id="candlestick", type="valuable", name="silver candlestick", properties=dict(value=40),
             location_id="tom_house"),
    ],
    # everyone knows the townsfolk by name; nobody knows the newcomer Ash yet
    "knowledge": [(a["id"], b["id"], "knows_identity")
                  for a in _CHARACTERS for b in _CHARACTERS if a is not b and b["id"] != "player"],
}
