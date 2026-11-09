/* The agent bridge. See agent-bridge.h.
 *
 * It reads state and writes keys. It holds no tactics, no thresholds and no
 * valuations: every choice is the outside agent's (docs/SOURCES.md).
 *
 * The observation is built from what the player could know: the player's own
 * remembered map (player->cave, which is what the game draws for the player),
 * the monsters the player can see, the objects the player remembers on the
 * floor, the character sheet, the message log and the screen. The Borg's own
 * map and monster trackers are deliberately not used: they are only refreshed
 * inside borg_think(), which the agent replaces, so with the agent deciding
 * they would be stale. No field is read from a monster's or a grid's hidden
 * state, so no observation here carries a "true_state" block (R1.1).
 */
#define ALLOW_BORG
#include "angband.h"
#include "cave.h"
#include "game-world.h"
#include "init.h"
#include "mon-lore.h"
#include "mon-predicate.h"
#include "monster.h"
#include "obj-desc.h"
#include "obj-gear.h"
#include "obj-util.h"
#include "player.h"
#include "player-timed.h"
#include "store.h"
#include "ui-term.h"
#include "borg/borg.h"
#include "borg/borg-io.h"
#include "borg/borg-store.h"
#include "borg/borg-trait.h"
#include "agent-bridge.h"
#include <ctype.h>
#include <errno.h>

#define AGENT_LINE 65536
#define AGENT_SCHEMA "borg-agent/observation@1"
/* The widest a map row can be: the dungeon's own width. */
#define AUTO_MAX_X 198

static FILE *observations;   /* we write one line per decision */
static FILE *actions;        /* we read one line per decision */
static bool  tried;
static long  decisions;
static int   last_messages = -1;
static const char *run_id;

/*** Writing JSON by hand, so the bridge needs no library ***/

static void json_string(FILE *out, const char *text)
{
    const unsigned char *p = (const unsigned char *)(text ? text : "");
    fputc('"', out);
    for (; *p; ++p) {
        if (*p == '"' || *p == '\\')
            fprintf(out, "\\%c", *p);
        else if (*p < 0x20 || *p == 0x7f)
            fprintf(out, "\\u%04x", *p);
        else
            fputc(*p, out);
    }
    fputc('"', out);
}

static void json_field(FILE *out, const char *name, const char *text)
{
    json_string(out, name);
    fputc(':', out);
    json_string(out, text);
}

/*** The connection ***/

bool agent_active(void)
{
    const char *obs_path = getenv("BORG_AGENT_OBS");
    const char *act_path = getenv("BORG_AGENT_ACT");

    if (!obs_path || !act_path)
        return false;
    if (tried)
        return observations && actions;
    tried = true;
    run_id = getenv("BORG_AGENT_RUN_ID");
    if (!run_id)
        run_id = "unnamed";
    /* The order matters: the agent opens the observation pipe for reading
     * first, so opening it for writing here completes the handshake. */
    observations = fopen(obs_path, "w");
    if (!observations)
        quit("agent bridge: cannot open BORG_AGENT_OBS");
    actions = fopen(act_path, "r");
    if (!actions)
        quit("agent bridge: cannot open BORG_AGENT_ACT");
    return true;
}

/*** The observation ***/

static void write_character(FILE *out)
{
    int i;
    bool first = true;
    static const char *stat_names[] = { "str", "int", "wis", "dex", "con" };

    fprintf(out, "\"character\":{");
    json_field(out, "name", player->full_name);
    fprintf(out, ",");
    json_field(out, "race", player->race->name);
    fprintf(out, ",");
    json_field(out, "class", player->class->name);
    fprintf(out,
        ",\"level\":%d,\"max_level\":%d,\"exp\":%d,\"hp\":%d,\"max_hp\":%d,"
        "\"sp\":%d,\"max_sp\":%d,\"depth\":%d,\"max_depth\":%d,\"gold\":%d,"
        "\"ac\":%d,\"speed\":%d,\"food\":%d",
        (int)player->lev, (int)player->max_lev, (int)player->exp,
        (int)player->chp, (int)player->mhp, (int)player->csp, (int)player->msp,
        (int)player->depth, (int)player->max_depth, (int)player->au,
        (int)(player->state.ac + player->state.to_a),
        (int)player->state.speed, (int)player->food);
    fprintf(out, ",\"stats\":{");
    for (i = 0; i < STAT_MAX && i < (int)N_ELEMENTS(stat_names); ++i) {
        char buf[16];
        /* Exactly as the character sheet prints it (cnv_stat in ui-display.c):
         * padded to six columns, 18/09 not 18/9, and 18/*** at 18/220. */
        int value = (int)player->stat_cur[i];
        if (value >= 19) {
            int bonus = value - 18;
            if (bonus >= 220)
                my_strcpy(buf, "18/***", sizeof(buf));
            else if (bonus >= 100)
                strnfmt(buf, sizeof(buf), "18/%03d", bonus);
            else
                strnfmt(buf, sizeof(buf), " 18/%02d", bonus);
        } else {
            strnfmt(buf, sizeof(buf), "    %2d", value);
        }
        if (i)
            fputc(',', out);
        json_field(out, stat_names[i], buf);
    }
    fprintf(out, "},\"conditions\":[");
    for (i = 0; i < TMD_MAX; ++i) {
        if (!player->timed[i])
            continue;
        if (!first)
            fputc(',', out);
        first = false;
        json_string(out, timed_effects[i].name);
    }
    fprintf(out, "]}");
}

static void write_map(FILE *out)
{
    int y, x;
    struct chunk *known = player->cave;
    int height = known ? known->height : 0;
    int width  = known ? known->width : 0;
    int top = height, left = width, bottom = -1, right = -1;

    /* The whole of what the player knows, trimmed to its bounding box: a
     * window would make the agent blind to a corridor it has already walked,
     * and the box is small while little is known. The player's own square is
     * always inside it. */
    for (y = 0; y < height; ++y) {
        for (x = 0; x < width; ++x) {
            if (known->squares[y][x].feat == FEAT_NONE)
                continue;
            if (y < top) top = y;
            if (y > bottom) bottom = y;
            if (x < left) left = x;
            if (x > right) right = x;
        }
    }
    if (bottom < 0) {
        top = bottom = player->grid.y;
        left = right = player->grid.x;
    }
    if (player->grid.y < top) top = player->grid.y;
    if (player->grid.y > bottom) bottom = player->grid.y;
    if (player->grid.x < left) left = player->grid.x;
    if (player->grid.x > right) right = player->grid.x;

    fprintf(out, "\"map\":{\"player\":{\"x\":%d,\"y\":%d},\"origin\":{\"x\":%d,\"y\":%d},\"rows\":[",
        (int)player->grid.x, (int)player->grid.y, left, top);
    for (y = top; y <= bottom; ++y) {
        char row[AUTO_MAX_X + 1];
        int n = 0;
        for (x = left; x <= right && n < AUTO_MAX_X; ++x) {
            uint8_t feat = (y < height && x < width) ? known->squares[y][x].feat : FEAT_NONE;
            if (feat == FEAT_NONE)
                row[n++] = ' ';
            else if (known->squares[y][x].trap)
                row[n++] = '^';
            else
                row[n++] = (char)f_info[feat].d_char;
        }
        row[n] = '\0';
        if (y > top)
            fputc(',', out);
        json_string(out, row);
    }
    fprintf(out, "]}");
}

static void write_monsters(FILE *out)
{
    int i;
    bool first = true;

    fprintf(out, "\"monsters\":[");
    for (i = 1; cave && i < cave->mon_max; ++i) {
        struct monster *mon = cave_monster(cave, i);
        char letter[2];

        /* Only what the player can see. Nothing here is read from a monster's
         * hidden state: no hit points, and asleep is null because the player
         * cannot tell. */
        if (!mon || !mon->race || !monster_is_visible(mon))
            continue;
        letter[0] = (char)mon->race->d_char;
        letter[1] = '\0';
        if (!first)
            fputc(',', out);
        first = false;
        fprintf(out, "{");
        json_field(out, "letter", letter);
        fputc(',', out);
        json_field(out, "name", mon->race->name);
        fprintf(out, ",\"x\":%d,\"y\":%d,\"distance\":%d,\"asleep\":null,\"health\":null}",
            (int)mon->grid.x, (int)mon->grid.y,
            distance(player->grid, mon->grid));
    }
    fprintf(out, "]");
}

static void write_objects(FILE *out)
{
    int y, x;
    bool first = true;
    struct chunk *known = player->cave;

    fprintf(out, "\"objects\":[");
    /* The objects the player remembers seeing on the floor, described the way
     * the game describes them to the player. */
    for (y = 0; known && y < known->height; ++y) {
        for (x = 0; x < known->width; ++x) {
            struct object *obj;
            for (obj = known->squares[y][x].obj; obj; obj = obj->next) {
                char description[120];
                if (!obj->kind)
                    continue;
                object_desc(description, sizeof(description), obj,
                    ODESC_PREFIX | ODESC_FULL, player);
                if (!first)
                    fputc(',', out);
                first = false;
                fprintf(out, "{");
                json_field(out, "description", description);
                fprintf(out, ",\"x\":%d,\"y\":%d}", x, y);
            }
        }
    }
    fprintf(out, "]");
}

static void write_items(FILE *out, const char *field, bool equipment)
{
    int i;
    bool first = true;

    fprintf(out, "\"%s\":[", field);
    for (i = 0; i < (equipment ? player->body.count : z_info->pack_size); ++i) {
        struct object *obj = equipment ? slot_object(player, i)
                                       : player->upkeep->inven[i];
        char description[120];
        char label[2];

        if (!obj)
            continue;
        object_desc(description, sizeof(description), obj,
            ODESC_PREFIX | ODESC_FULL, player);
        label[0] = equipment ? gear_to_label(player, obj) : I2A(i);
        label[1] = '\0';
        if (!first)
            fputc(',', out);
        first = false;
        fprintf(out, "{");
        json_field(out, "label", label);
        fputc(',', out);
        json_field(out, "description", description);
        fprintf(out, ",\"count\":%d}", (int)obj->number);
    }
    fprintf(out, "]");
}

static void write_shop(FILE *out)
{
    struct store *store = cave ? store_at(cave, player->grid) : NULL;
    struct object **listed;
    int index, written = 0;
    size_t letters;

    if (!store) {
        fprintf(out, "\"shop\":null");
        return;
    }
    letters = strlen(SHOP_MENU_ITEMS);
    fprintf(out, "\"shop\":{");
    /* The store as the screen names it: its entrance terrain, exactly as
     * ui-store.c titles the page. */
    json_field(out, "kind", f_info[store->feat].name);
    fprintf(out, ",\"stock\":[");
    /* In the store menu's own order. The raw store->stock list is in
     * insertion order; the screen shows store_stock_list()'s order, and the
     * menu's letters follow that, so reading the raw list made a label point
     * at the wrong item (found by the milestone 2 review). Each item is
     * described as the store describes it -- ODESC_STORE hides what the player
     * has not learned -- and the letters are the store menu's own selection
     * string, which the Borg also uses. */
    listed = mem_zalloc(sizeof(*listed) * z_info->store_inven_max);
    store_stock_list(store, listed, z_info->store_inven_max);
    for (index = 0; index < z_info->store_inven_max; ++index) {
        struct object *obj = listed[index];
        char description[120];
        char label[2];

        if (!obj || !obj->kind)
            continue;
        /* The Home keeps the player's own things: its screen shows them in
         * full, with no prices, and so does this (ui-store.c). */
        bool home = store->feat == FEAT_HOME;
        object_desc(description, sizeof(description), obj,
            home ? (ODESC_PREFIX | ODESC_FULL)
                 : (ODESC_PREFIX | ODESC_FULL | ODESC_STORE), player);
        label[0] = (index < (int)letters) ? SHOP_MENU_ITEMS[index] : '?';
        label[1] = '\0';
        if (written++)
            fputc(',', out);
        fprintf(out, "{");
        json_field(out, "label", label);
        fputc(',', out);
        json_field(out, "description", description);
        fprintf(out, ",\"count\":%d", (int)obj->number);
        if (!home)
            fprintf(out, ",\"price\":%d", price_item(store, obj, false, 1));
        fprintf(out, "}");
    }
    mem_free(listed);
    fprintf(out, "]}");
}

static void write_messages(FILE *out)
{
    int total = messages_num();
    int fresh, i;

    if (last_messages < 0 || last_messages > total)
        last_messages = total;
    fresh = total - last_messages;
    last_messages = total;
    fprintf(out, "\"messages\":[");
    /* message_str(0) is the newest, so walk back to front for reading order. */
    for (i = fresh - 1; i >= 0; --i) {
        if (i < fresh - 1)
            fputc(',', out);
        json_string(out, message_str(i));
    }
    fprintf(out, "]");
}

static void write_prompt_and_screen(FILE *out)
{
    int y;
    uint8_t attributes[256];
    char line[256];
    char top[256];
    const char *kind = "none";

    if (borg_what_text(0, 0, -80, attributes, top) != 0)
        top[0] = '\0';
    if (strstr(top, "-more-"))
        kind = "more";
    else if (strstr(top, "[y/n]"))
        kind = "yes_no";
    else if (top[0] && top[strlen(top) - 1] == '?')
        kind = "text";

    fprintf(out, "\"prompt\":{");
    json_field(out, "kind", kind);
    fputc(',', out);
    json_field(out, "text", top);
    fprintf(out, "},\"screen\":[");
    for (y = 0; y < 24; ++y) {
        if (borg_what_text(0, y, -80, attributes, line) != 0)
            line[0] = '\0';
        if (y)
            fputc(',', out);
        json_string(out, line);
    }
    fprintf(out, "]");
}

static void write_observation(void)
{
    FILE *out = observations;

    fprintf(out, "{");
    json_field(out, "schema", AGENT_SCHEMA);
    fputc(',', out);
    json_field(out, "run_id", run_id);
    fprintf(out, ",\"decision\":%ld,\"turn\":%ld,", decisions, (long)turn);
    write_character(out);
    fputc(',', out);
    write_map(out);
    fputc(',', out);
    write_monsters(out);
    fputc(',', out);
    write_objects(out);
    fputc(',', out);
    write_items(out, "inventory", false);
    fputc(',', out);
    write_items(out, "equipment", true);
    fputc(',', out);
    write_messages(out);
    fputc(',', out);
    write_shop(out);
    fputc(',', out);
    write_prompt_and_screen(out);
    fprintf(out, "}\n");
    fflush(out);
}

/*** The action ***/

/* Values arrive percent-escaped, so one line never breaks on a space. */
static void unescape(char *text)
{
    char *in = text, *out = text;

    while (*in) {
        if (in[0] == '%' && isxdigit((unsigned char)in[1])
            && isxdigit((unsigned char)in[2])) {
            char hex[3] = { in[1], in[2], '\0' };
            *out++ = (char)strtol(hex, NULL, 16);
            in += 3;
        } else {
            *out++ = *in++;
        }
    }
    *out = '\0';
}

static const char *argument(char *fields[], int count, const char *name)
{
    int i;
    size_t length = strlen(name);

    for (i = 0; i < count; ++i) {
        if (!strncmp(fields[i], name, length) && fields[i][length] == '=')
            return fields[i] + length + 1;
    }
    return NULL;
}

static int direction_of(char *fields[], int count)
{
    const char *value = argument(fields, count, "dir");
    int dir = value ? atoi(value) : 0;

    if (dir < 1 || dir > 9 || dir == 5)
        quit("agent bridge: a direction must be 1-9 and not 5");
    return dir;
}

/* The command table: this is where an action becomes keys. The keys are the
 * ones the Borg itself sends for the same command, so the game sees nothing
 * new (RULES 9). */
static void apply_action(char *line)
{
    char *fields[32];
    int count = 0;
    char *saved = NULL;
    char *token = strtok_r(line, " \t\r\n", &saved);
    const char *kind;
    const char *name;

    while (token && count < (int)N_ELEMENTS(fields)) {
        unescape(token);
        fields[count++] = token;
        token = strtok_r(NULL, " \t\r\n", &saved);
    }
    if (count < 2)
        quit("agent bridge: an action needs a kind and a name");
    kind = fields[0];
    name = fields[1];

    if (!strcmp(kind, "keys")) {
        /* The escape hatch (R1.2), logged as raw keys. */
        borg_note(format("# AGENT raw keys <%s>", name));
        borg_keypresses(name);
        return;
    }
    if (strcmp(kind, "command"))
        quit(format("agent bridge: unknown action kind <%s>", kind));

    borg_note(format("# AGENT command %s", name));
    if (!strcmp(name, "walk")) {
        borg_keypress(';');
        borg_keypress(I2D(direction_of(fields, count)));
    } else if (!strcmp(name, "alter")) {
        borg_keypress('+');
        borg_keypress(I2D(direction_of(fields, count)));
    } else if (!strcmp(name, "stay")) {
        borg_keypress(',');
    } else if (!strcmp(name, "pickup")) {
        borg_keypress('g');
    } else if (!strcmp(name, "rest")) {
        const char *mode = argument(fields, count, "mode");
        borg_keypress('R');
        if (mode && !strcmp(mode, "turns")) {
            const char *turns = argument(fields, count, "count");
            if (!turns || atoi(turns) < 1)
                quit("agent bridge: rest mode=turns needs count");
            borg_keypresses(turns);
        } else if (mode && !strcmp(mode, "as_needed")) {
            borg_keypress('&');
        } else {
            borg_keypress('*');
        }
        borg_keypress(KC_ENTER);
    } else if (!strcmp(name, "go_down")) {
        borg_keypress('>');
    } else if (!strcmp(name, "go_up")) {
        borg_keypress('<');
    } else if (!strcmp(name, "answer")) {
        const char *text = argument(fields, count, "text");
        if (!text || !*text)
            quit("agent bridge: answer needs text");
        borg_keypresses(text);
    } else if (!strcmp(name, "read")) {
        const char *item = argument(fields, count, "item");
        if (!item || !*item)
            quit("agent bridge: read needs item");
        borg_keypress('r');
        borg_keypress((keycode_t)item[0]);
    } else if (!strcmp(name, "quaff")) {
        const char *item = argument(fields, count, "item");
        if (!item || !*item)
            quit("agent bridge: quaff needs item");
        borg_keypress('q');
        borg_keypress((keycode_t)item[0]);
    } else if (!strcmp(name, "buy") || !strcmp(name, "sell")) {
        /* The Borg's own sequence: in a store the item's letter moves the
         * cursor, the command acts on it, and two returns accept the quantity
         * and the price. */
        const char *item = argument(fields, count, "item");
        const char *quantity = argument(fields, count, "count");
        bool buying = !strcmp(name, "buy");
        if (!item || !*item)
            quit("agent bridge: a purchase needs item");
        if (buying) {
            borg_keypress((keycode_t)item[0]);
            borg_keypress('p');
        } else {
            borg_keypress('s');
            borg_keypress((keycode_t)item[0]);
        }
        if (quantity && atoi(quantity) > 1)
            borg_keypresses(quantity);
        borg_keypress(KC_ENTER);
        borg_keypress(KC_ENTER);
    } else if (!strcmp(name, "escape")) {
        borg_keypress(ESCAPE);
    } else {
        quit(format("agent bridge: no key translation for <%s>", name));
    }
}

void agent_think(void)
{
    char line[AGENT_LINE];

    if (!agent_active())
        quit("agent bridge: asked to think with no connection");
    write_observation();
    if (!fgets(line, sizeof(line), actions))
        quit("agent bridge: the agent closed the action pipe");
    ++decisions;
    apply_action(line);
}
