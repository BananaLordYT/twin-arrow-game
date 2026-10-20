"""Twin Arrow Arena — a tiny, pixel-art, two-player Python game."""

import math
import random
import sys
import colorsys
import queue
from pathlib import Path

import pygame
from online_client import OnlineClient


WIDTH, HEIGHT = 640, 360
SCALE = 2
FPS = 60
PLAYER_SIZE = 10
PLAYER_SPEED = 2.0
BULLET_SPEED = 4.5
FIRE_INTERVAL = 500  # milliseconds
WALL_SIZE = 24
WALL_COUNT = 42

BLACK = (12, 15, 26)
FLOOR = (25, 31, 48)
GRID = (31, 39, 58)
WHITE = (239, 244, 255)
BLUE = (68, 196, 255)
ORANGE = (255, 166, 76)
RED = (255, 79, 96)
WALL = (77, 88, 116)
WALL_LIGHT = (118, 135, 169)
PICKER_SIZE = (190, 145)
POWERUP_CHANCE = 0.10
POWERUP_CHECK_MS = 1000
POWERUP_DURATION_MS = 6000
POWERUP_LIFETIME_MS = 12000
RAPID_COLOR = (78, 226, 255)
DAMAGE_COLOR = (255, 83, 174)


def make_walls():
    """Build a random grid of cover, leaving room around both spawn points."""
    walls = []
    occupied = set()
    cols = WIDTH // WALL_SIZE
    rows = HEIGHT // WALL_SIZE
    spawn_clearance = [
        pygame.Rect(40, 40, 48, 48),
        pygame.Rect(WIDTH - 88, HEIGHT - 88, 48, 48),
    ]
    attempts = 0
    while len(walls) < WALL_COUNT and attempts < WALL_COUNT * 12:
        attempts += 1
        col = random.randrange(1, cols - 1)
        row = random.randrange(1, rows - 1)
        if (col, row) in occupied:
            continue
        rect = pygame.Rect(col * WALL_SIZE + 2, row * WALL_SIZE + 2,
                           WALL_SIZE - 4, WALL_SIZE - 4)
        if any(rect.colliderect(clearance) for clearance in spawn_clearance):
            continue
        occupied.add((col, row))
        walls.append(rect)
    return walls


def make_player(x, y, color, keys, angle):
    return {
        "x": float(x), "y": float(y), "color": color, "keys": keys,
        "angle": angle, "health": 5, "last_shot": 0, "hit_flash": 0,
        "rapid_until": 0, "damage_until": 0,
    }


def player_polygon(player):
    return arrow_points(player["x"], player["y"], player["angle"])


def point_in_polygon(point, polygon):
    x, y = point
    inside = False
    previous = polygon[-1]
    for current in polygon:
        x1, y1 = previous
        x2, y2 = current
        if (y1 > y) != (y2 > y):
            crossing_x = (x2 - x1) * (y - y1) / (y2 - y1) + x1
            if x < crossing_x:
                inside = not inside
        previous = current
    return inside


def orientation(a, b, c):
    return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])


def segments_intersect(a, b, c, d):
    o1 = orientation(a, b, c)
    o2 = orientation(a, b, d)
    o3 = orientation(c, d, a)
    o4 = orientation(c, d, b)
    # Strict crossings count as overlap; merely touching a wall edge does not.
    return ((o1 > 0 > o2 or o2 > 0 > o1) and
            (o3 > 0 > o4 or o4 > 0 > o3))


def polygon_hits_rect(polygon, rect):
    """Precise overlap between the visible arrow polygon and a rectangle."""
    left = min(point[0] for point in polygon)
    right = max(point[0] for point in polygon)
    top = min(point[1] for point in polygon)
    bottom = max(point[1] for point in polygon)
    if right < rect.left or left >= rect.right or bottom < rect.top or top >= rect.bottom:
        return False

    if any(rect.collidepoint(point) for point in polygon):
        return True

    corners = [(rect.left, rect.top), (rect.right - 1, rect.top),
               (rect.right - 1, rect.bottom - 1), (rect.left, rect.bottom - 1)]
    if any(point_in_polygon(corner, polygon) for corner in corners):
        return True

    rect_edges = list(zip(corners, corners[1:] + corners[:1]))
    poly_edges = list(zip(polygon, polygon[1:] + polygon[:1]))
    return any(segments_intersect(a, b, c, d)
               for a, b in poly_edges for c, d in rect_edges)


def polygons_intersect(first, second):
    """Check overlap between two visible arrow polygons."""
    if (max(point[0] for point in first) <= min(point[0] for point in second) or
            max(point[0] for point in second) <= min(point[0] for point in first) or
            max(point[1] for point in first) <= min(point[1] for point in second) or
            max(point[1] for point in second) <= min(point[1] for point in first)):
        return False
    if any(point_in_polygon(point, second) for point in first):
        return True
    if any(point_in_polygon(point, first) for point in second):
        return True
    first_edges = list(zip(first, first[1:] + first[:1]))
    second_edges = list(zip(second, second[1:] + second[:1]))
    return any(segments_intersect(a, b, c, d)
               for a, b in first_edges for c, d in second_edges)


def blocked(rect, walls):
    return any(rect.colliderect(wall) for wall in walls)


def move_player(player, dx, dy, walls, players):
    # Resolve each axis separately using the same polygon that is drawn onscreen.
    player["x"] += dx * PLAYER_SPEED
    points = player_polygon(player)
    outside = (min(point[0] for point in points) < 3 or
               max(point[0] for point in points) > WIDTH - 3)
    collides_with_wall = any(polygon_hits_rect(points, wall) for wall in walls)
    collides_with_player = any(
        other is not player and polygons_intersect(points, player_polygon(other))
        for other in players
    )
    if outside or collides_with_wall or collides_with_player:
        player["x"] -= dx * PLAYER_SPEED
    player["y"] += dy * PLAYER_SPEED
    points = player_polygon(player)
    outside = (min(point[1] for point in points) < 3 or
               max(point[1] for point in points) > HEIGHT - 3)
    collides_with_wall = any(polygon_hits_rect(points, wall) for wall in walls)
    collides_with_player = any(
        other is not player and polygons_intersect(points, player_polygon(other))
        for other in players
    )
    if outside or collides_with_wall or collides_with_player:
        player["y"] -= dy * PLAYER_SPEED


def arrow_points(x, y, angle, size=12):
    # A chunky arrowhead with a short tail, rotated to face the firing direction.
    local = [(size, 0), (1, -7), (2, -3), (-size + 3, -3),
             (-size + 3, 3), (2, 3), (1, 7)]
    cosine, sine = math.cos(angle), math.sin(angle)
    return [(round(x + px * cosine - py * sine),
             round(y + px * sine + py * cosine)) for px, py in local]


def draw_text(surface, font, text, x, y, color=WHITE):
    surface.blit(font.render(text, False, color), (x, y))


def draw_button(surface, rect, label, font, mouse_pos):
    hovered = rect.collidepoint(mouse_pos)
    pygame.draw.rect(surface, (8, 10, 18), rect.move(2, 3))
    pygame.draw.rect(surface, (67, 82, 116) if hovered else (42, 52, 76), rect)
    pygame.draw.rect(surface, (148, 171, 211) if hovered else WALL_LIGHT, rect, 2)
    text = font.render(label, False, WHITE)
    surface.blit(text, text.get_rect(center=rect.center))


def make_color_picker(size):
    """Create a hue and saturation field; brightness is controlled separately."""
    width, height = size
    picker = pygame.Surface(size)
    for x in range(width):
        hue = x / max(1, width - 1)
        for y in range(height):
            saturation = 1.0 - y / max(1, height - 1)
            rgb = colorsys.hsv_to_rgb(hue, saturation, 1.0)
            picker.set_at((x, y), tuple(round(channel * 255) for channel in rgb))
    return picker


def hex_color(text):
    value = text.strip().lstrip("#")
    if len(value) != 6:
        return None
    try:
        return tuple(int(value[index:index + 2], 16) for index in (0, 2, 4))
    except ValueError:
        return None


def color_hex(color):
    return "#" + "".join(f"{channel:02X}" for channel in color)


def reset_round(colors):
    walls = make_walls()
    players = [
        make_player(64, 64, colors[0],
                    {"up": pygame.K_w, "down": pygame.K_s,
                     "left": pygame.K_a, "right": pygame.K_d}, 0),
        make_player(WIDTH - 64, HEIGHT - 64, colors[1],
                    {"up": pygame.K_UP, "down": pygame.K_DOWN,
                     "left": pygame.K_LEFT, "right": pygame.K_RIGHT}, math.pi),
    ]
    return walls, players, []


def spawn_powerup(walls, players, now):
    """Choose a clear spot for a collectible boost."""
    for _ in range(100):
        x = random.randrange(28, WIDTH - 28)
        y = random.randrange(44, HEIGHT - 28)
        rect = pygame.Rect(x - 9, y - 9, 18, 18)
        if blocked(rect, walls):
            continue
        if any(math.hypot(x - player["x"], y - player["y"]) < 42 for player in players):
            continue
        return {"x": x, "y": y, "kind": random.choice(("rapid", "damage")),
                "expires": now + POWERUP_LIFETIME_MS}
    return None


def main():
    pygame.init()
    screen = pygame.display.set_mode((WIDTH * SCALE, HEIGHT * SCALE))
    pygame.display.set_caption("Twin Arrow Arena")
    canvas = pygame.Surface((WIDTH, HEIGHT))
    clock = pygame.time.Clock()
    font = pygame.font.Font(None, 18)
    big_font = pygame.font.Font(None, 34)
    picker_font = pygame.font.Font(None, 15)
    color_picker = make_color_picker(PICKER_SIZE)
    random.seed()

    colors = [BLUE, ORANGE]
    walls, players, bullets = reset_round(colors)
    powerups = []
    winner = None
    scene = "menu"
    next_powerup_check = 0
    round_start_time = 0
    round_end_time = None
    picker_values = [1.0, 1.0]
    picker_hs = [colorsys.rgb_to_hsv(*(channel / 255 for channel in color))[:2]
                 for color in colors]
    hex_inputs = ["", ""]
    active_hex = None
    play_button = pygame.Rect(250, 193, 140, 36)
    customize_button = pygame.Rect(222, 238, 196, 36)
    online_button = pygame.Rect(250, 283, 140, 36)
    back_button = pygame.Rect(72, 320, 110, 32)
    start_button = pygame.Rect(458, 320, 110, 32)
    find_match_button = pygame.Rect(220, 205, 200, 40)
    online_back_button = pygame.Rect(250, 265, 140, 36)
    online_client = None
    online_status = ""
    online_game = False
    online_role = None
    remote_controls = {"up": False, "down": False, "left": False, "right": False}
    last_input_send = 0
    last_snapshot_send = 0

    running = True
    while running:
        now = pygame.time.get_ticks()
        clock.tick(FPS)

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    if scene == "menu":
                        running = False
                    elif scene == "game" and online_game:
                        if online_client:
                            online_client.close()
                            online_client = None
                        online_game = False
                        online_role = None
                        scene = "menu"
                    else:
                        if scene == "online_wait" and online_client:
                            online_client.close()
                            online_client = None
                        online_game = False
                        online_role = None
                        scene = "menu"
                        active_hex = None
                elif scene == "customize" and active_hex is not None:
                    if event.key == pygame.K_RETURN:
                        picked = hex_color(hex_inputs[active_hex])
                        if picked is not None:
                            colors[active_hex] = picked
                            picker_hs[active_hex] = colorsys.rgb_to_hsv(
                                *(channel / 255 for channel in picked))[:2]
                            picker_values[active_hex] = max(picked) / 255
                            hex_inputs[active_hex] = color_hex(picked)
                    elif event.key == pygame.K_BACKSPACE:
                        hex_inputs[active_hex] = hex_inputs[active_hex][:-1]
                    elif event.unicode and event.unicode.lower() in "0123456789abcdef#":
                        if len(hex_inputs[active_hex]) < 7:
                            hex_inputs[active_hex] += event.unicode.upper()
                            picked = hex_color(hex_inputs[active_hex])
                            if picked is not None:
                                colors[active_hex] = picked
                                hue, saturation, value = colorsys.rgb_to_hsv(
                                    *(channel / 255 for channel in picked))
                                picker_hs[active_hex] = (hue, saturation)
                                picker_values[active_hex] = value
                elif (event.key == pygame.K_r and scene == "game" and winner and
                      (not online_game or online_role == 1)):
                    walls, players, bullets = reset_round(colors)
                    powerups = []
                    next_powerup_check = now + POWERUP_CHECK_MS
                    winner = None
                    round_start_time = now
                    round_end_time = None
            elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                mouse_pos = (event.pos[0] // SCALE, event.pos[1] // SCALE)
                if scene == "menu":
                    if play_button.collidepoint(mouse_pos):
                        walls, players, bullets = reset_round(colors)
                        powerups = []
                        next_powerup_check = now + POWERUP_CHECK_MS
                        winner = None
                        round_start_time = now
                        round_end_time = None
                        scene = "game"
                    elif customize_button.collidepoint(mouse_pos):
                        scene = "customize"
                    elif online_button.collidepoint(mouse_pos):
                        scene = "online"
                        online_status = "Enter the public matchmaking queue."
                elif scene == "online":
                    if online_back_button.collidepoint(mouse_pos):
                        scene = "menu"
                    elif find_match_button.collidepoint(mouse_pos):
                        # In a frozen build, keep editable settings beside the
                        # executable so both the Desktop and app-data copies work.
                        app_dir = (Path(sys.executable).resolve().parent
                                   if getattr(sys, "frozen", False)
                                   else Path(__file__).resolve().parent)
                        config_path = app_dir / "server_url.txt"
                        try:
                            server_url = config_path.read_text().strip()
                        except OSError:
                            server_url = ""
                        if server_url.startswith("https://"):
                            server_url = "wss://" + server_url[len("https://"):]
                        if not server_url.startswith("wss://"):
                            online_status = "Set your Render wss:// URL in server_url.txt first."
                        else:
                            online_client = OnlineClient(server_url)
                            online_status = "Connecting to the matchmaker..."
                            scene = "online_wait"
                elif scene == "online_wait" and online_back_button.collidepoint(mouse_pos):
                    if online_client:
                        online_client.close()
                        online_client = None
                    scene = "online"
                elif scene == "customize":
                    if back_button.collidepoint(mouse_pos):
                        scene = "menu"
                    elif start_button.collidepoint(mouse_pos):
                        walls, players, bullets = reset_round(colors)
                        powerups = []
                        next_powerup_check = now + POWERUP_CHECK_MS
                        winner = None
                        round_start_time = now
                        round_end_time = None
                        scene = "game"
                    else:
                        active_hex = None
                        for player_index, panel_x in enumerate((0, WIDTH // 2)):
                            field = pygame.Rect(panel_x + 48, 278, 220, 30)
                            picker_rect = pygame.Rect(panel_x + 20, 112, *PICKER_SIZE)
                            value_rect = pygame.Rect(panel_x + 222, 112, 18, PICKER_SIZE[1])
                            if field.collidepoint(mouse_pos):
                                active_hex = player_index
                                if not hex_inputs[player_index]:
                                    hex_inputs[player_index] = color_hex(colors[player_index])
                            elif picker_rect.collidepoint(mouse_pos):
                                px = mouse_pos[0] - picker_rect.x
                                py = mouse_pos[1] - picker_rect.y
                                hue = px / max(1, picker_rect.w - 1)
                                saturation = 1.0 - py / max(1, picker_rect.h - 1)
                                picker_hs[player_index] = (hue, saturation)
                                rgb = colorsys.hsv_to_rgb(hue, saturation, picker_values[player_index])
                                colors[player_index] = tuple(round(channel * 255) for channel in rgb)
                                hex_inputs[player_index] = color_hex(colors[player_index])
                            elif value_rect.collidepoint(mouse_pos):
                                value = 1.0 - (mouse_pos[1] - value_rect.y) / max(1, value_rect.h - 1)
                                picker_values[player_index] = max(0.0, min(1.0, value))
                                # Preserve the selected hue and saturation while changing brightness.
                                hue, saturation = picker_hs[player_index]
                                rgb = colorsys.hsv_to_rgb(hue, saturation, picker_values[player_index])
                                colors[player_index] = tuple(round(channel * 255) for channel in rgb)
                                hex_inputs[player_index] = color_hex(colors[player_index])

        if online_client:
            while True:
                try:
                    message = online_client.incoming.get_nowait()
                except queue.Empty:
                    break
                kind = message.get("type")
                if kind == "waiting":
                    online_status = "Searching for another player..."
                elif kind == "matched":
                    online_role = message.get("player")
                    online_game = True
                    walls, players, bullets = reset_round(colors)
                    powerups = []
                    winner = None
                    round_start_time = now
                    round_end_time = None
                    next_powerup_check = now + POWERUP_CHECK_MS
                    remote_controls = {"up": False, "down": False,
                                       "left": False, "right": False}
                    last_input_send = 0
                    last_snapshot_send = 0
                    scene = "game"
                elif kind == "input" and online_game and online_role == 1:
                    remote_controls = message.get("keys", remote_controls)
                elif kind == "state" and online_game and online_role == 2:
                    colors[:] = [tuple(color) for color in message["colors"]]
                    walls = [pygame.Rect(*rect) for rect in message["walls"]]
                    players = []
                    controls = [
                        {"up": pygame.K_w, "down": pygame.K_s,
                         "left": pygame.K_a, "right": pygame.K_d},
                        {"up": pygame.K_UP, "down": pygame.K_DOWN,
                         "left": pygame.K_LEFT, "right": pygame.K_RIGHT},
                    ]
                    for index, data in enumerate(message["players"]):
                        player = make_player(data["x"], data["y"], colors[index],
                                             controls[index], data["angle"])
                        player["health"] = data["health"]
                        player["rapid_until"] = now + data["rapid_remaining"]
                        player["damage_until"] = now + data["damage_remaining"]
                        player["hit_flash"] = now + data["hit_flash_remaining"]
                        players.append(player)
                    bullets = []
                    for data in message["bullets"]:
                        bullets.append({
                            "x": data["x"], "y": data["y"],
                            "dx": data["dx"], "dy": data["dy"],
                            "owner": players[data["owner"]], "damage": data["damage"],
                        })
                    powerups = [dict(item) for item in message["powerups"]]
                    winner = message["winner"]
                    elapsed_ms = message["elapsed_ms"]
                    round_start_time = now - elapsed_ms
                    round_end_time = now if winner else None
                elif kind == "opponent_disconnected":
                    online_status = "The other player disconnected."
                    online_game = False
                    online_role = None
                    scene = "online"
                    online_client.close()
                    online_client = None
                    break
                elif kind == "error":
                    online_status = "Matchmaker connection failed: " + message.get("message", "")[:80]
                    online_game = False
                    online_role = None
                    scene = "online"
                    online_client.close()
                    online_client = None
                    break

        keys = pygame.key.get_pressed()
        if online_game and online_role == 2 and online_client and now - last_input_send >= 50:
            online_client.send({
                "type": "input",
                "keys": {"up": bool(keys[pygame.K_UP]), "down": bool(keys[pygame.K_DOWN]),
                         "left": bool(keys[pygame.K_LEFT]), "right": bool(keys[pygame.K_RIGHT])},
            })
            last_input_send = now

        if scene == "game" and not winner and (not online_game or online_role == 1):
            powerups = [item for item in powerups if item["expires"] > now]
            if now >= next_powerup_check:
                next_powerup_check = now + POWERUP_CHECK_MS
                if not powerups and random.random() < POWERUP_CHANCE:
                    pickup = spawn_powerup(walls, players, now)
                    if pickup:
                        powerups.append(pickup)

            for index, player in enumerate(players):
                if online_game and index == 1:
                    control = remote_controls
                    dx = float(control["right"]) - float(control["left"])
                    dy = float(control["down"]) - float(control["up"])
                else:
                    dx = float(keys[player["keys"]["right"]]) - float(keys[player["keys"]["left"]])
                    dy = float(keys[player["keys"]["down"]]) - float(keys[player["keys"]["up"]])
                if dx or dy:
                    length = math.hypot(dx, dy)
                    dx, dy = dx / length, dy / length
                    player["angle"] = math.atan2(dy, dx)
                    move_player(player, dx, dy, walls, players)

                fire_interval = 160 if now < player["rapid_until"] else FIRE_INTERVAL
                if now - player["last_shot"] >= fire_interval:
                    angle = player["angle"]
                    bullets.append({
                        "x": player["x"] + math.cos(angle) * 12,
                        "y": player["y"] + math.sin(angle) * 12,
                        "dx": math.cos(angle) * BULLET_SPEED,
                        "dy": math.sin(angle) * BULLET_SPEED,
                        "owner": player,
                        "damage": 2 if now < player["damage_until"] else 1,
                    })
                    player["last_shot"] = now

            for item in powerups[:]:
                item_rect = pygame.Rect(round(item["x"] - 9), round(item["y"] - 9), 18, 18)
                for player in players:
                    if polygon_hits_rect(player_polygon(player), item_rect):
                        effect_until = now + POWERUP_DURATION_MS
                        if item["kind"] == "rapid":
                            player["rapid_until"] = effect_until
                        else:
                            player["damage_until"] = effect_until
                        powerups.remove(item)
                        break

            for bullet in bullets[:]:
                bullet["x"] += bullet["dx"]
                bullet["y"] += bullet["dy"]
                bullet_rect = pygame.Rect(round(bullet["x"] - 2), round(bullet["y"] - 2), 4, 4)
                if (bullet_rect.left < 0 or bullet_rect.right >= WIDTH or
                        bullet_rect.top < 0 or bullet_rect.bottom >= HEIGHT or
                        blocked(bullet_rect, walls)):
                    bullets.remove(bullet)
                    continue
                for target in players:
                    if (target is not bullet["owner"] and
                            polygon_hits_rect(player_polygon(target), bullet_rect)):
                        target["health"] -= bullet["damage"]
                        target["hit_flash"] = now + 120
                        bullets.remove(bullet)
                        if target["health"] <= 0:
                            winner = "PLAYER 1 WINS!" if target is players[1] else "PLAYER 2 WINS!"
                            round_end_time = now
                        break

        if online_game and online_role == 1 and online_client and now - last_snapshot_send >= 50:
            elapsed_ms = max(0, (round_end_time if round_end_time is not None else now) - round_start_time)
            online_client.send({
                "type": "state",
                "colors": colors,
                "walls": [[wall.x, wall.y, wall.w, wall.h] for wall in walls],
                "players": [{
                    "x": player["x"], "y": player["y"], "angle": player["angle"],
                    "health": player["health"],
                    "rapid_remaining": max(0, player["rapid_until"] - now),
                    "damage_remaining": max(0, player["damage_until"] - now),
                    "hit_flash_remaining": max(0, player["hit_flash"] - now),
                } for player in players],
                "bullets": [{
                    "x": bullet["x"], "y": bullet["y"], "dx": bullet["dx"],
                    "dy": bullet["dy"],
                    "owner": 0 if bullet["owner"] is players[0] else 1,
                    "damage": bullet["damage"],
                } for bullet in bullets],
                "powerups": powerups,
                "winner": winner,
                "elapsed_ms": elapsed_ms,
            })
            last_snapshot_send = now

        # Pixel-art arena background and tiled grid.
        canvas.fill(FLOOR)
        for x in range(0, WIDTH, WALL_SIZE):
            pygame.draw.line(canvas, GRID, (x, 0), (x, HEIGHT))
        for y in range(0, HEIGHT, WALL_SIZE):
            pygame.draw.line(canvas, GRID, (0, y), (WIDTH, y))
        pygame.draw.rect(canvas, (50, 62, 85), (1, 1, WIDTH - 2, HEIGHT - 2), 2)

        for wall in walls:
            pygame.draw.rect(canvas, (10, 13, 23), wall.move(2, 2))
            pygame.draw.rect(canvas, WALL, wall)
            pygame.draw.line(canvas, WALL_LIGHT, (wall.x + 2, wall.y + 2),
                             (wall.right - 3, wall.y + 2), 2)
            pygame.draw.line(canvas, (54, 64, 88), (wall.x + 2, wall.bottom - 3),
                             (wall.right - 3, wall.bottom - 3), 2)

        if scene == "game":
            for item in powerups:
                color = RAPID_COLOR if item["kind"] == "rapid" else DAMAGE_COLOR
                box = pygame.Rect(round(item["x"] - 9), round(item["y"] - 9), 18, 18)
                pygame.draw.rect(canvas, (8, 10, 18), box.move(2, 2))
                pygame.draw.rect(canvas, color, box)
                pygame.draw.rect(canvas, WHITE, box, 1)
                icon = font.render("F" if item["kind"] == "rapid" else "D", False, BLACK)
                canvas.blit(icon, icon.get_rect(center=box.center))

        for bullet in bullets:
            color = bullet["owner"]["color"]
            pygame.draw.rect(canvas, color, (round(bullet["x"] - 2), round(bullet["y"] - 2), 4, 4))

        for player in players:
            color = RED if now < player["hit_flash"] else player["color"]
            pts = arrow_points(player["x"], player["y"], player["angle"])
            pygame.draw.polygon(canvas, (8, 10, 18), [(x + 2, y + 2) for x, y in pts])
            pygame.draw.polygon(canvas, color, pts)
            pygame.draw.polygon(canvas, WHITE, pts, 1)

        if scene == "game":
            # Heads-up display.
            draw_text(canvas, font, "P1  WASD", 12, 7, players[0]["color"])
            p2_x = WIDTH - 162
            draw_text(canvas, font, "P2  ARROWS", p2_x, 7, players[1]["color"])
            for index, player in enumerate(players):
                x = 12 if index == 0 else WIDTH - 162
                bar = pygame.Rect(x, 26, 150, 17)
                percent = max(0, min(100, round(player["health"] / 5 * 100)))
                pygame.draw.rect(canvas, (8, 10, 18), bar)
                fill_width = round(bar.width * percent / 100)
                if fill_width:
                    pygame.draw.rect(canvas, player["color"],
                                     (bar.x, bar.y, fill_width, bar.height))
                pygame.draw.rect(canvas, WHITE, bar, 1)
                percent_label = font.render(f"{percent}%", False, WHITE)
                center = percent_label.get_rect(center=bar.center)
                # A dark pixel outline keeps the percentage readable on bright colors.
                for offset in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                    canvas.blit(font.render(f"{percent}%", False, BLACK), center.move(*offset))
                canvas.blit(percent_label, center)
                statuses = []
                if now < player["rapid_until"]:
                    statuses.append("FAST FIRE")
                if now < player["damage_until"]:
                    statuses.append("2X DAMAGE")
                if statuses:
                    status_color = RAPID_COLOR if now < player["rapid_until"] else DAMAGE_COLOR
                    draw_text(canvas, picker_font, " + ".join(statuses), x, 47, status_color)
            draw_text(canvas, font, "AUTO FIRE  /  0.5 SEC", 216, 8, (168, 179, 205))
            timer_time = round_end_time if round_end_time is not None else now
            elapsed = max(0, timer_time - round_start_time) // 1000
            timer_label = f"{elapsed // 60:02d}:{elapsed % 60:02d}"
            draw_text(canvas, font, timer_label, 374, 8, WHITE)

        if scene in ("menu", "customize", "online", "online_wait"):
            shade = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
            shade.fill((4, 7, 15, 240))
            canvas.blit(shade, (0, 0))
            mouse_pos = (pygame.mouse.get_pos()[0] // SCALE,
                         pygame.mouse.get_pos()[1] // SCALE)
            if scene == "menu":
                title = big_font.render("TWIN ARROW ARENA", False, WHITE)
                canvas.blit(title, title.get_rect(center=(WIDTH // 2, 75)))
                draw_text(canvas, font, "PIXEL DUEL  /  LOCAL 2 PLAYER", 220, 101, (168, 179, 205))
                pygame.draw.polygon(canvas, colors[0], arrow_points(260, 157, 0, 15))
                pygame.draw.polygon(canvas, colors[1], arrow_points(380, 157, math.pi, 15))
                draw_button(canvas, play_button, "PLAY", font, mouse_pos)
                draw_button(canvas, customize_button, "CUSTOMIZE", font, mouse_pos)
                draw_button(canvas, online_button, "ONLINE", font, mouse_pos)
                draw_text(canvas, picker_font, "WASD VS ARROW KEYS", 251, 333, (130, 146, 177))
            elif scene == "customize":
                title = big_font.render("CUSTOMIZE ARROWS", False, WHITE)
                canvas.blit(title, title.get_rect(center=(WIDTH // 2, 31)))
                draw_text(canvas, picker_font, "PICK ANY COLOR OR TYPE A HEX CODE", 223, 53,
                          (168, 179, 205))
                pygame.draw.rect(canvas, (17, 21, 35), (0, 72, WIDTH // 2, 240))
                pygame.draw.rect(canvas, (20, 25, 40), (WIDTH // 2, 72, WIDTH // 2, 240))
                pygame.draw.line(canvas, (92, 106, 137), (WIDTH // 2, 72),
                                 (WIDTH // 2, 312), 2)
                for player_index, panel_x in enumerate((0, WIDTH // 2)):
                    label = "PLAYER 1  /  WASD" if player_index == 0 else "PLAYER 2  /  ARROWS"
                    draw_text(canvas, font, label, panel_x + 20, 79, colors[player_index])
                    direction = 0 if player_index == 0 else math.pi
                    pygame.draw.polygon(canvas, colors[player_index],
                                        arrow_points(panel_x + 271, 89, direction, 13))

                    picker_rect = pygame.Rect(panel_x + 20, 112, *PICKER_SIZE)
                    canvas.blit(color_picker, picker_rect)
                    brightness = pygame.Surface(PICKER_SIZE, pygame.SRCALPHA)
                    brightness.fill((0, 0, 0, round((1 - picker_values[player_index]) * 255)))
                    canvas.blit(brightness, picker_rect)
                    pygame.draw.rect(canvas, WHITE, picker_rect, 1)

                    hue, saturation = picker_hs[player_index]
                    marker_x = picker_rect.x + round(hue * (picker_rect.w - 1))
                    marker_y = picker_rect.y + round((1 - saturation) * (picker_rect.h - 1))
                    pygame.draw.circle(canvas, (8, 10, 18), (marker_x, marker_y), 5, 2)
                    pygame.draw.circle(canvas, WHITE, (marker_x, marker_y), 4, 1)

                    value_rect = pygame.Rect(panel_x + 222, 112, 18, PICKER_SIZE[1])
                    for row in range(value_rect.h):
                        shade = round(255 * (1 - row / max(1, value_rect.h - 1)))
                        pygame.draw.line(canvas, (shade, shade, shade),
                                         (value_rect.x, value_rect.y + row),
                                         (value_rect.right - 1, value_rect.y + row))
                    pygame.draw.rect(canvas, WHITE, value_rect, 1)
                    value_y = value_rect.y + round((1 - picker_values[player_index]) * (value_rect.h - 1))
                    pygame.draw.rect(canvas, (255, 68, 82),
                                     (value_rect.x - 3, value_y - 2, value_rect.w + 6, 4))

                    draw_text(canvas, picker_font, "HEX COLOR", panel_x + 20, 266,
                              (168, 179, 205))
                    field = pygame.Rect(panel_x + 48, 278, 220, 30)
                    pygame.draw.rect(canvas, (12, 15, 26), field)
                    pygame.draw.rect(canvas, colors[player_index], field, 2)
                    field_text = hex_inputs[player_index] or color_hex(colors[player_index])
                    if active_hex == player_index:
                        field_text += "_"
                    draw_text(canvas, font, field_text, field.x + 8, field.y + 7, WHITE)
                draw_button(canvas, back_button, "BACK", font, mouse_pos)
                draw_button(canvas, start_button, "PLAY", font, mouse_pos)
            else:
                title = big_font.render("ONLINE DUEL", False, WHITE)
                canvas.blit(title, title.get_rect(center=(WIDTH // 2, 77)))
                draw_text(canvas, font, "PUBLIC MATCHMAKING", 255, 104, (168, 179, 205))
                status = online_status if scene == "online" else "Searching for another player..."
                status_surface = picker_font.render(status, False, WHITE)
                canvas.blit(status_surface,
                            status_surface.get_rect(center=(WIDTH // 2, 164)))
                if scene == "online":
                    draw_button(canvas, find_match_button, "FIND MATCH", font, mouse_pos)
                    draw_button(canvas, online_back_button, "BACK", font, mouse_pos)
                    draw_text(canvas, picker_font, "SET server_url.txt AFTER DEPLOYING THE MATCHMAKER",
                              159, 314, (130, 146, 177))
                else:
                    draw_button(canvas, online_back_button, "CANCEL", font, mouse_pos)

        if winner and scene == "game":
            shade = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
            shade.fill((4, 7, 15, 205))
            canvas.blit(shade, (0, 0))
            label = big_font.render(winner, False, WHITE)
            canvas.blit(label, label.get_rect(center=(WIDTH // 2, HEIGHT // 2 - 18)))
            hint_text = ("PLAYER 1: PRESS R TO REMATCH" if online_game and online_role == 1 else
                         "WAIT FOR PLAYER 1 TO PRESS R" if online_game else
                         "PRESS R FOR A NEW RANDOM ARENA")
            hint = font.render(hint_text, False, (183, 198, 225))
            canvas.blit(hint, hint.get_rect(center=(WIDTH // 2, HEIGHT // 2 + 15)))

        pygame.transform.scale(canvas, screen.get_size(), screen)
        pygame.display.flip()

    pygame.quit()
    return 0


if __name__ == "__main__":
    sys.exit(main())
