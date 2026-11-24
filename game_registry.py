from dataclasses import dataclass
from importlib import import_module


@dataclass(frozen=True)
class GameSpec:
    key: str
    name: str
    command: str
    join_command: str
    description: str
    help_commands: tuple
    web_label: str
    callback_prefix: str
    min_players: int
    max_players: int
    npc_full: str
    rematch_phases: tuple
    cover: str
    module: str
    web_module: str
    static_assets: tuple = ()
    command_aliases: tuple = ()
    callback_prefix_aliases: tuple = ()
    start_prefix: str = ""
    supports_app_param: bool = True

    @property
    def start_prefix_or_key(self):
        return self.start_prefix or self.key

    @property
    def help_line(self):
        commands = " ".join(self.help_commands)
        return f"{self.command} - {self.description} (also {commands})"

    @property
    def catalog_row(self):
        return (self.key, self.name, self.command, self.join_command, self.description)

    def start_param(self, chat_id):
        if not self.supports_app_param:
            return str(chat_id)
        return f"{self.start_prefix_or_key}{chat_id}"


GAME_SPECS = (
    GameSpec(
        key="games", name="🎴 Flip 7", command="/flip7", join_command="/flip7_join",
        description="press-your-luck Flip 7",
        help_commands=("/flip7_join", "/flip7_start", "/flip7_rules", "/join_npc"),
        web_label="🎮 Play Flip 7 (HTML)", callback_prefix="f7",
        min_players=2, max_players=6, npc_full="⛔ Game is full.",
        rematch_phases=("game_end",), cover="flip7.jpg",
        module="game", web_module="flip7", static_assets=("flip7.js", "flip7-cards.webp"),
        supports_app_param=False,
    ),
    GameSpec(
        key="regicide", name="⚔️ Regicide", command="/regicide", join_command="/regicide_join",
        description="co-op vs 12 royals, private hands",
        help_commands=("/regicide_join", "/regicide_start", "/regicide_play", "/regicide_yield",
                       "/regicide_discard", "/regicide_rules", "/regicide_cancel"),
        web_label="🎮 Play Regicide (HTML)", callback_prefix="rg",
        min_players=2, max_players=4, npc_full="⛔ Regicide is 2-4 players (full).",
        rematch_phases=("won", "lost"), cover="regicide.jpg",
        module="regicide", web_module="regicide", static_assets=("regicide.js", "regicide-cards.webp"),
    ),
    GameSpec(
        key="odin", name="🛡️ Odin", command="/odin", join_command="/odin_join",
        description="card shedding, fewest points wins",
        help_commands=("/odin_join", "/odin_start", "/odin_play", "/odin_pass", "/odin_pickup",
                       "/odin_score", "/odin_cancel", "/odin_rules"),
        web_label="🎮 Play Odin (HTML)", callback_prefix="od",
        min_players=2, max_players=6, npc_full="⛔ Odin is 2-6 players (full).",
        rematch_phases=("game_end",), cover="odin.jpg",
        module="odin", web_module="odin", static_assets=("odin.js", "odin-cards.webp"),
    ),
    GameSpec(
        key="leaves", name="🍃 13 Leaves", command="/leaves", join_command="/leaves_join",
        description="shed sets, first to empty your hand",
        help_commands=("/leaves_join", "/leaves_start", "/leaves_play", "/leaves_pass",
                       "/leaves_rules", "/leaves_cancel"),
        web_label="🎮 Play 13 Leaves (HTML)", callback_prefix="lv",
        min_players=3, max_players=6, npc_full="⛔ 13 Leaves is 3-6 players (full).",
        rematch_phases=("game_end",), cover="",
        module="game_modules.leaves", web_module="leaves", static_assets=("leaves.js", "13leaves.png"),
    ),
    GameSpec(
        key="lsd", name="😈 Let's Summon Demons", command="/lsd", join_command="/lsd_join",
        description="dice activations, 3 demons + 10 souls",
        help_commands=("/lsd_join", "/lsd_start", "/lsd_roll", "/lsd_buy", "/lsd_summon",
                       "/lsd_end", "/lsd_score", "/lsd_cancel", "/lsd_rules"),
        web_label="🎮 Play Summon Demons (HTML)", callback_prefix="lsd",
        min_players=2, max_players=5, npc_full="⛔ Let's Summon Demons is 2-5 players (full).",
        rematch_phases=("game_end",), cover="lsd.jpg",
        module="lsd", web_module="lsd", static_assets=("lsd.js",),
    ),
    GameSpec(
        key="spots", name="🐶 Spots", command="/spots", join_command="/spots_join",
        description="dog dice push-your-luck, 6 scored wins",
        help_commands=("/spots_join", "/spots_start", "/spots_trick", "/spots_place",
                       "/spots_reroll", "/spots_score", "/spots_cancel", "/spots_rules"),
        web_label="🎮 Play Spots (HTML)", callback_prefix="spots",
        min_players=1, max_players=4, npc_full="⛔ Spots is 1-4 players (full).",
        rematch_phases=("game_end",), cover="spots.jpg",
        module="spots", web_module="spots", static_assets=("spots.js",),
    ),
    GameSpec(
        key="yahtzee", name="🎲 Yahtzee", command="/yahtzee", join_command="/yahtzee_join",
        description="dice scorecard, 13 boxes",
        help_commands=("/yahtzee_join", "/yahtzee_start", "/yahtzee_roll", "/yahtzee_score",
                       "/yahtzee_cancel", "/yahtzee_rules"),
        web_label="🎮 Play Yahtzee (HTML)", callback_prefix="yz",
        min_players=2, max_players=6, npc_full="⛔ Yahtzee is 2-6 players (full).",
        rematch_phases=("game_end",), cover="yahtzee.jpg",
        module="yahtzee", web_module="yahtzee", static_assets=("yahtzee.js",),
    ),
    GameSpec(
        key="fliptoons", name="🦋 Fliptoons", command="/fliptoons", join_command="/fliptoons_join",
        description="grid-building card market, first to 30 fame",
        help_commands=("/fliptoons_join", "/fliptoons_start", "/fliptoons_hire", "/fliptoons_dismiss",
                       "/fliptoons_skip", "/fliptoons_choose", "/fliptoons_cancel", "/fliptoons_rules"),
        web_label="🎮 Play Fliptoons (HTML)", callback_prefix="ft",
        min_players=2, max_players=4, npc_full="⛔ Fliptoons is 2-4 players (full).",
        rematch_phases=("game_end",), cover="fliptoons.jpg",
        module="fliptoons", web_module="fliptoons", static_assets=("fliptoons.js",),
    ),
    GameSpec(
        key="castlecombo", name="🏰 Castle Combo", command="/castlecombo", join_command="/castlecombo_join",
        description="deck-building tableau, 3×3 shields & sets",
        help_commands=("/castlecombo_join", "/castlecombo_start", "/castlecombo_buy", "/castlecombo_flip",
                       "/castlecombo_key", "/castlecombo_choose", "/castlecombo_cancel", "/castlecombo_rules"),
        web_label="🎮 Play Castle Combo (HTML)", callback_prefix="cc",
        min_players=2, max_players=5, npc_full="⛔ Castle Combo is 2-5 players (full).",
        rematch_phases=("game_end",), cover="castlecombo.jpg",
        module="castlecombo", web_module="castlecombo", static_assets=("castlecombo.js",),
    ),
    GameSpec(
        key="tornado", name="🛥️ Tornado Splash", command="/tornado", join_command="/tornado_join",
        description="jet-ski racing cards, first to the finish",
        help_commands=("/tornado_join", "/tornado_start", "/tornado_pick", "/tornado_play",
                       "/tornado_wait", "/tornado_hand", "/tornado_next", "/tornado_cancel", "/tornado_rules"),
        web_label="🎮 Play Tornado Splash (HTML)", callback_prefix="ts",
        min_players=2, max_players=5, npc_full="⛔ Tornado Splash is 2-5 players (full).",
        rematch_phases=("race_end", "game_end"), cover="tornado.jpg",
        module="tornado", web_module="tornado", static_assets=("tornado.js",),
    ),
    GameSpec(
        key="artichokes", name="🥬 Abandon All Artichokes", command="/artichokes", join_command="/artichokes_join",
        description="deck-wrecking veggies, draw a hand with no Artichokes",
        help_commands=("/artichokes_join", "/artichokes_start", "/artichokes_harvest", "/artichokes_play",
                       "/artichokes_end", "/artichokes_choose", "/artichokes_cancel", "/artichokes_rules"),
        web_label="🎮 Play Abandon All Artichokes (HTML)", callback_prefix="at",
        min_players=2, max_players=4, npc_full="⛔ Abandon All Artichokes is 2-4 players (full).",
        rematch_phases=("game_end",), cover="artichokes.jpg",
        module="artichokes", web_module="artichokes", static_assets=("artichokes.js",),
    ),
    GameSpec(
        key="fellowship", name="💍 Fellowship of the Ring", command="/fotr", join_command="/fotr_join",
        description="co-op trick-taking through 18 chapters",
        help_commands=("/fotr_join", "/fotr_start", "/fotr_chapter", "/fotr_choose", "/fotr_play",
                       "/fotr_ring", "/fotr_rules", "/fotr_cancel"),
        web_label="🎮 Play Fellowship (HTML)", callback_prefix="fotr",
        min_players=2, max_players=4, npc_full="⛔ Fellowship is 2-4 players (full).",
        rematch_phases=("chapter_end", "game_end"), cover="fellowship.png",
        module="fellowship", web_module="fellowship", static_assets=("fellowship.js",),
        command_aliases=("/fellowship",), callback_prefix_aliases=("fr",),
    ),
    GameSpec(
        key="azul", name="🔷 Azul", command="/azul", join_command="/azul_join",
        description="tile-drafting wall builder, most points wins",
        help_commands=("/azul_join", "/azul_join_npc", "/azul_start", "/azul_take",
                       "/azul_place", "/azul_rules", "/azul_cancel", "/azul_rematch"),
        web_label="🎮 Play Azul (HTML)", callback_prefix="az",
        min_players=2, max_players=4, npc_full="⛔ Azul is 2-4 players (full).",
        rematch_phases=("game_end",), cover="../azul_assets/gamemedia/box/en_280.png",
        module="azul", web_module="azul", static_assets=("azul.js",),
    ),
    GameSpec(
        key="toybattle", name="🎯 Toy Battle", command="/toybattle", join_command="/toybattle_join",
        description="2-player troops, medals and HQ capture",
        help_commands=("/toybattle_join", "/toybattle_start", "/toybattle_draw", "/toybattle_place",
                       "/toybattle_choose", "/toybattle_rules", "/toybattle_cancel"),
        web_label="🎮 Play Toy Battle (HTML)", callback_prefix="tb",
        min_players=2, max_players=2, npc_full="⛔ Toy Battle is 2 players (full).",
        rematch_phases=("game_end",), cover="toybattle.jpg",
        module="toybattle", web_module="toybattle",
        static_assets=("toybattle.js", "toybattle-tiles.webp", "toybattle-board.webp", "toybattle-medals.webp"),
    ),
    GameSpec(
        key="tokaidoduo", name="🗾 Tokaido Duo", command="/tokaidoduo", join_command="/tokaidoduo_join",
        description="2-player Shikoku journey, 3 characters each",
        help_commands=("/tokaidoduo_join", "/tokaidoduo_start", "/tokaidoduo_pick",
                       "/tokaidoduo_choose", "/tokaidoduo_rules", "/tokaidoduo_cancel"),
        web_label="🎮 Play Tokaido Duo (HTML)", callback_prefix="td",
        min_players=2, max_players=2, npc_full="⛔ Tokaido Duo is 2 players (full).",
        rematch_phases=("game_end",), cover="",
        module="tokaidoduo", web_module="tokaidoduo",
        static_assets=("tokaidoduo.js", "tokaidoduo-board.webp", "tokaidoduo-icons.webp"),
    ),
    GameSpec(
        key="altay", name="🏜️ Altay", command="/altay", join_command="/altay_join",
        description="2-player civilization: produce, build, conquer, develop",
        help_commands=("/altay_join", "/altay_join_npc", "/altay_seafarers", "/altay_start",
                       "/altay_play", "/altay_buy", "/altay_build", "/altay_attack",
                       "/altay_develop", "/altay_trade", "/altay_end", "/altay_score",
                       "/altay_rules", "/altay_cancel"),
        web_label="🎮 Play Altay (HTML)", callback_prefix="al",
        min_players=2, max_players=2, npc_full="⛔ Altay is 2 players (full).",
        rematch_phases=("over",), cover="altay.png",
        module="altay", web_module="altay",
        static_assets=("altay.js", "altay-board.webp", "altay-actions.webp",
                       "altay-achievements.webp", "altay-markers.webp", "altay-tokens.webp",
                       "altay-seafarers-actions.webp", "altay-seafarers-achievements.webp",
                       "altay-seafarers-tokens.webp", "altay-seafarers-ships.webp"),
    ),
    GameSpec(
        key="blackflag", name="🏴‍☠️ Black Flag", command="/blackflag", join_command="/blackflag_join",
        description="4-8 players: ship, shoot, sink and race the treasure chest to your flag",
        help_commands=("/blackflag_join", "/blackflag_join_npc", "/blackflag_start",
                       "/blackflag_ship", "/blackflag_play", "/blackflag_defend",
                       "/blackflag_pass", "/blackflag_end", "/blackflag_rules",
                       "/blackflag_cancel", "/blackflag_rematch"),
        web_label="🎮 Play Black Flag (HTML)", callback_prefix="bf",
        min_players=4, max_players=8, npc_full="⛔ Black Flag is 4-8 players (full).",
        rematch_phases=("game_end",), cover="blackflag.jpg",
        module="blackflag", web_module="blackflag",
        static_assets=("blackflag.js", "blackflag-cards.webp", "blackflag-ships.webp",
                       "blackflag-board.webp", "blackflag-cardback.webp"),
    ),
)

GAMES_BY_KEY = {spec.key: spec for spec in GAME_SPECS}
GAME_KEYS = tuple(spec.key for spec in GAME_SPECS)
CATALOG_ROWS = tuple(spec.catalog_row for spec in GAME_SPECS)
HELP_LINES = tuple(spec.help_line for spec in GAME_SPECS)
NPC_MAX = {spec.key: spec.max_players for spec in GAME_SPECS}
NPC_FULL = {spec.key: spec.npc_full for spec in GAME_SPECS}
REMATCH_END_PHASES = {spec.key: spec.rematch_phases for spec in GAME_SPECS}
CALLBACK_CODES = {}
for _spec in GAME_SPECS:
    CALLBACK_CODES[_spec.callback_prefix] = _spec.key
    for _alias in getattr(_spec, "callback_prefix_aliases", ()):
        CALLBACK_CODES[_alias] = _spec.key
WEB_JS_ROUTES = {
    f"/{spec.web_module}.js": spec.web_module + ".js" for spec in GAME_SPECS
}
WEB_JS_ROUTES["/flip7.js"] = "flip7.js"


def help_text(tail=()):
    lines = ["🎴 <b>Boardgame bot</b>", "/games - list the games you can start (and what's running here)"]
    lines.extend(HELP_LINES)
    lines.extend(tail)
    return "\n".join(lines)


def keyboard_label(key):
    spec = GAMES_BY_KEY.get(key) or GAMES_BY_KEY["games"]
    return spec.web_label


def supports_web_routing(key):
    spec = GAMES_BY_KEY.get(key)
    return bool(spec and spec.supports_app_param)


def load_game_module(spec):
    return import_module(spec.module)
