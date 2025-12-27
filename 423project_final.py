from OpenGL.GL import *
from OpenGL.GLUT import *
from OpenGL.GLU import *
import math
import random

fovY = 120
GRID_LENGTH = 600
rand_var = 423

WINDOW_W, WINDOW_H = 1000, 800


camera_pos = (0, 500, 500)
LANE_HALF_WIDTH = 120
PATH_START_Z = -80
TILE_LENGTH = 160
NUM_TILES = 75

WALL_HEIGHT = 120
WALL_THICK = 18

PLAYER_RADIUS = 18

MOVE_SPEED = 8
ROT_SPEED = 2.4

GRAVITY = -0.9
JUMP_VEL = 20
BOOST_VEL = 40
BOOST_COOLDOWN_MS = 650

TIME_LIMIT_SEC = 160
BOOST_REQUIRED_Y = 70

CHECK_COLS = 6
CHECK_ROWS = 4

FAKE_SPAN_TILES = 2
FAKE_FALL_SPEED = 4.0
FAKE_FALL_KILL_Y = -120.0
FAKE_FAIL_TOUCH_EPS = 1.0

MOVING_PLATFORM_HALF_WIDTH = 70
MOVING_PLATFORM_MINX = -150
MOVING_PLATFORM_MAXX = 150

ENEMY_RADIUS = 15
ENEMY_BODY_SIZE = 20
ENEMY_LEG_COUNT = 6
ENEMY_LEG_LENGTH = 15
ENEMY_LEG_RADIUS = 3
ENEMY_ROAM_SPEED = 1.0
ENEMY_CHASE_SPEED = 2.5
ENEMY_CHASE_DISTANCE = 300
ENEMY_DAMAGE_DISTANCE = 25
ENEMY_DAMAGE_COOLDOWN_MS = 1000

HAZARD_SPAWN_INTERVAL_MS = 800
HAZARD_FALL_SPEED = 2
HAZARD_SIZE = 15
HAZARD_DAMAGE = 15
HAZARD_MIN_Z_OFFSET = -200
HAZARD_MAX_Z_OFFSET = 200

CLOSING_WALL_WIDTH = 30
CLOSING_WALL_HEIGHT = 100
CLOSING_WALL_SPEED = 1.5
CLOSING_WALL_MAX_OPEN = LANE_HALF_WIDTH
CLOSING_WALL_MIN_OPEN = 5

PLAYER_MAX_LIFE = 100
player_life = PLAYER_MAX_LIFE
last_damage_ms = -999999
last_hazard_spawn_ms = 0

keys_down = {b'w': False, b's': False, b'a': False, b'd': False}
jump_pressed = False

player_pos = [0.0, 0.0, 0.0]
player_yaw = 0.0
player_vel_y = 0.0
player_on_ground = True
last_boost_ms = -999999

game_over = False
win = False

tiles = []
rot_obstacles = []
moving_platforms = []
pink_gates = []
fake_segments = []
enemies = []
falling_hazards = []
closing_walls = []

finish_z = None
start_ms = None
quadric = None

game_paused = False
game_started = False

score = 0
gems = []
TOTAL_GEMS = 12

cheat_pass_obstacles = False
cheat_auto_collect_items = False

camera_first_person = False

difficulty_level = 1
checkpoint_tiles = [12, 28, 44, 58, 70]
next_checkpoint_idx = 0

# Dynamic speeds (scaled by difficulty_level)
move_speed = MOVE_SPEED
hazard_spawn_interval_ms = HAZARD_SPAWN_INTERVAL_MS
hazard_fall_speed = HAZARD_FALL_SPEED
max_hazards = 3


def draw_text(px, py, text, font=GLUT_BITMAP_HELVETICA_18):
    glDisable(GL_DEPTH_TEST)
    glColor3f(1, 1, 1)
    glWindowPos2f(float(px), float(py))
    for ch in text:
        glutBitmapCharacter(font, ord(ch))
    glEnable(GL_DEPTH_TEST)


def clamp(v, lo, hi):
    return lo if v < lo else (hi if v > hi else v)


def aabb_overlap(px, py, pz, pr, bx, by, bz, sx, sy, sz):
    dx = abs(px - bx)
    dy = abs(py - by)
    dz = abs(pz - bz)
    return (dx <= (pr + sx)) and (dy <= (pr + sy)) and (dz <= (pr + sz))


def distance_2d(x1, z1, x2, z2):
    return math.sqrt((x1 - x2) ** 2 + (z1 - z2) ** 2)


def distance_3d(x1, y1, z1, x2, y2, z2):
    return math.sqrt((x1 - x2) ** 2 + (y1 - y2) ** 2 + (z1 - z2) ** 2)


def increase_difficulty():

    global difficulty_level, move_speed, hazard_spawn_interval_ms, hazard_fall_speed, max_hazards

    difficulty_level += 1


    move_speed = MOVE_SPEED + 1.0 * (difficulty_level - 1)


    hazard_spawn_interval_ms = max(250, int(HAZARD_SPAWN_INTERVAL_MS * (0.92 ** (difficulty_level - 1))))
    hazard_fall_speed = HAZARD_FALL_SPEED + (difficulty_level - 1) * 0.5


    max_hazards = min(10, 3 + (difficulty_level - 1))


def maybe_trigger_checkpoint_and_scale():

    global next_checkpoint_idx, rot_obstacles, closing_walls

    if next_checkpoint_idx >= len(checkpoint_tiles):
        return

    ti = get_tile_index_from_z(player_pos[2])
    if ti is None:
        return

    if ti >= checkpoint_tiles[next_checkpoint_idx]:

        increase_difficulty()
        next_checkpoint_idx += 1


        new_tile = min(NUM_TILES - 2, ti + 6)
        new_z = PATH_START_Z + new_tile * TILE_LENGTH
        rot_obstacles.append({
            "x": 0.0,
            "y": 35.0,
            "z": new_z,
            "angle": 0.0,
            "speed": 3.0 + 0.4 * (difficulty_level - 1),
            "size": (240, 12, 12)
        })


def spawn_gems():
    """Place collectible gems along the path."""
    global gems
    gems = []

    gem_tiles = [6, 9, 13, 17, 21, 27, 34, 39, 45, 53, 61, 69]
    for idx, ti in enumerate(gem_tiles[:TOTAL_GEMS]):
        z = PATH_START_Z + ti * TILE_LENGTH
        x = 0.0 if idx % 3 == 0 else (70.0 if idx % 3 == 1 else -70.0)
        gems.append({
            "x": x,
            "y": 65.0,
            "z": z,
            "collected": False,
            "value": 10,
            "life_bonus": 6
        })


def check_gem_collection(auto_collect=False):

    global score, player_life

    px = player_pos[0]
    py = player_pos[1] + 65.0
    pz = player_pos[2]

    radius = 55.0 if auto_collect else 30.0

    for g in gems:
        if g["collected"]:
            continue
        d = distance_3d(px, py, pz, g["x"], g["y"], g["z"])
        if d <= radius:
            g["collected"] = True
            score += g["value"]
            player_life = min(PLAYER_MAX_LIFE, player_life + g["life_bonus"])


def draw_gems():
    for g in gems:
        if g["collected"]:
            continue
        glPushMatrix()
        glTranslatef(g["x"], g["y"], g["z"])
        glColor3f(1.0, 0.85, 0.1)
        gluSphere(quadric, 10.5, 16, 16)
        glPopMatrix()
def get_tile_index_from_z(z):
    i = int((z - PATH_START_Z) / TILE_LENGTH)
    if 0 <= i < NUM_TILES:
        return i
    return None


def player_in_fake_segment():
    ti = get_tile_index_from_z(player_pos[2])
    if ti is None:
        return None
    for seg in fake_segments:
        if seg["start_i"] <= ti <= seg["end_i"]:
            return seg
    return None


def tile_surface_y(i):
    if i is None:
        return None
    return tiles[i]["fall_y"]


def is_tile_solid(i):
    if i is None:
        return False
    t = tiles[i]
    if t["type"] == "fake" and t["falling"]:
        return False
    return True


def moving_platform_for_tile(i):
    for mp in moving_platforms:
        if mp["tile_i"] == i:
            return mp
    return None





def reset_game():
    global tiles, rot_obstacles, moving_platforms, pink_gates, fake_segments, enemies, falling_hazards, closing_walls
    global score, gems, cheat_pass_obstacles, cheat_auto_collect_items, camera_first_person
    global difficulty_level, next_checkpoint_idx, move_speed, hazard_spawn_interval_ms, hazard_fall_speed, max_hazards
    global player_pos, player_yaw, player_vel_y, player_on_ground, last_boost_ms
    global game_over, win, start_ms, finish_z
    global jump_pressed, player_life, last_damage_ms, last_hazard_spawn_ms
    global game_started

    for k in keys_down:
        keys_down[k] = False
    jump_pressed = False

    player_pos[:] = [0.0, 0.0, 0.0]
    player_yaw = 0.0
    player_vel_y = 0.0
    player_on_ground = True
    last_boost_ms = -999999
    player_life = PLAYER_MAX_LIFE
    last_damage_ms = -999999
    last_hazard_spawn_ms = 0

    score = 0
    cheat_pass_obstacles = False
    cheat_auto_collect_items = False
    camera_first_person = False

    difficulty_level = 1
    next_checkpoint_idx = 0
    move_speed = MOVE_SPEED
    hazard_spawn_interval_ms = HAZARD_SPAWN_INTERVAL_MS
    hazard_fall_speed = HAZARD_FALL_SPEED
    max_hazards = 3

    game_over = False
    win = False
    game_started = False
    start_ms = glutGet(GLUT_ELAPSED_TIME)

    finish_z = PATH_START_Z + (NUM_TILES - 1) * TILE_LENGTH + 120

    tiles = []
    for i in range(NUM_TILES):
        tiles.append({
            "z": PATH_START_Z + i * TILE_LENGTH,
            "type": "normal",
            "falling": False,
            "fall_y": 0.0
        })

    fake_start_indices = [14, 30, 46, 60]
    fake_segments = []
    for si in fake_start_indices:
        ei = min(NUM_TILES - 1, si + FAKE_SPAN_TILES - 1)
        fake_segments.append({"start_i": si, "end_i": ei, "triggered": False})
        for ti in range(si, ei + 1):
            tiles[ti]["type"] = "fake"

    rot_positions = [10, 22, 38, 52, 68]
    rot_obstacles = []
    for idx, ti in enumerate(rot_positions):
        zpos = PATH_START_Z + ti * TILE_LENGTH
        rot_obstacles.append({
            "x": 0.0,
            "y": 35.0,
            "z": zpos,
            "angle": 0.0,
            "speed": 2.6 if idx % 2 == 0 else -3.4,
            "size": (220 + 20 * (idx % 3), 12, 12)
        })

    moving_platforms = [
        {"tile_i": 20, "x": 0.0, "dir": 1, "minx": MOVING_PLATFORM_MINX, "maxx": MOVING_PLATFORM_MAXX, "speed": 2.8},
        {"tile_i": 36, "x": 0.0, "dir": -1, "minx": MOVING_PLATFORM_MINX, "maxx": MOVING_PLATFORM_MAXX, "speed": 3.0},
        {"tile_i": 55, "x": 0.0, "dir": 1, "minx": MOVING_PLATFORM_MINX, "maxx": MOVING_PLATFORM_MAXX, "speed": 3.2},
        {"tile_i": 71, "x": 0.0, "dir": -1, "minx": MOVING_PLATFORM_MINX, "maxx": MOVING_PLATFORM_MAXX, "speed": 3.0},
    ]

    gate_positions = [18, 40, 66]
    pink_gates = [{"z": PATH_START_Z + ti * TILE_LENGTH, "thickness": 24} for ti in gate_positions]

    enemy_spawn_tiles = [8, 16, 25, 33, 42, 50, 58, 65, 72]
    enemies = []
    for idx, ti in enumerate(enemy_spawn_tiles):
        z_pos = PATH_START_Z + ti * TILE_LENGTH
        x_offset = 60 if idx % 2 == 0 else -60
        enemies.append({
            "x": x_offset,
            "y": 20,
            "z": z_pos,
            "center_x": x_offset,
            "center_z": z_pos,
            "roam_radius": 50,
            "state": "roam",
            "roam_angle": idx * 60.0,
            "leg_phase": idx * 30.0
        })

    falling_hazards = []

    spawn_gems()

    wall_positions = [12, 28, 44, 58, 70]
    closing_walls = []
    for idx, ti in enumerate(wall_positions):
        z_pos = PATH_START_Z + ti * TILE_LENGTH
        closing_walls.append({
            "z": z_pos,
            "left_x": -CLOSING_WALL_MAX_OPEN,
            "right_x": CLOSING_WALL_MAX_OPEN,
            "direction": 1,
            "speed": CLOSING_WALL_SPEED + (idx * 0.2)
        })


def setupCamera():
    glMatrixMode(GL_PROJECTION)
    glLoadIdentity()
    gluPerspective(fovY, WINDOW_W / float(WINDOW_H), 0.1, 4500)

    glMatrixMode(GL_MODELVIEW)
    glLoadIdentity()

    yaw_rad = math.radians(player_yaw)

    if camera_first_person:

        forward_offset = 18.0
        head_height    = 55.0
        look_ahead     = 260.0
        look_down      = 25.0

        eye_x = player_pos[0] + forward_offset * math.sin(yaw_rad)
        eye_y = player_pos[1] + head_height
        eye_z = player_pos[2] + forward_offset * math.cos(yaw_rad)

        look_x = eye_x + math.sin(yaw_rad) * look_ahead
        look_y = eye_y - look_down
        look_z = eye_z + math.cos(yaw_rad) * look_ahead

        gluLookAt(eye_x, eye_y, eye_z, look_x, look_y, look_z, 0, 1, 0)
    else:

        behind_dist = 280
        up_height = 190

        cam_x = player_pos[0] - math.sin(yaw_rad) * behind_dist
        cam_y = player_pos[1] + up_height
        cam_z = player_pos[2] - math.cos(yaw_rad) * behind_dist

        look_x = player_pos[0] + math.sin(yaw_rad) * 140
        look_y = player_pos[1] + 65
        look_z = player_pos[2] + math.cos(yaw_rad) * 140

        gluLookAt(cam_x, cam_y, cam_z, look_x, look_y, look_z, 0, 1, 0)

def draw_checker_tile(center_x, center_y, center_z, half_width, is_fake=False):
    lane_w = half_width * 2
    sq_w = lane_w / CHECK_COLS
    sq_l = TILE_LENGTH / CHECK_ROWS

    for r in range(CHECK_ROWS):
        for c in range(CHECK_COLS):
            odd = (r + c) % 2 == 0
            if is_fake:
                glColor3f(0.55, 0.10, 0.10) if odd else glColor3f(0.05, 0.05, 0.05)
            else:
                glColor3f(0.2, 0.7, 0.9) if odd else glColor3f(0.9, 0.6, 0.2)

            x = center_x - half_width + (c + 0.5) * sq_w
            z = center_z - (TILE_LENGTH / 2) + (r + 0.5) * sq_l

            glPushMatrix()
            glTranslatef(x, center_y, z)
            glScalef((sq_w) / 60.0, 0.15, (sq_l) / 60.0)
            glutSolidCube(60)
            glPopMatrix()


def draw_floor_and_walls():
    for i, t in enumerate(tiles):
        z = t["z"]
        mp = moving_platform_for_tile(i)
        if mp:
            cx = mp["x"]
            halfw = MOVING_PLATFORM_HALF_WIDTH
        else:
            cx = 0.0
            halfw = LANE_HALF_WIDTH

        glPushMatrix()
        glTranslatef(cx, t["fall_y"], z)
        draw_checker_tile(0, 0, 0, halfw, is_fake=(t["type"] == "fake"))
        glPopMatrix()

        glPushMatrix()
        glTranslatef(-LANE_HALF_WIDTH - WALL_THICK, 60, z)
        glColor3f(0.3, 0.3, 0.6)
        glScalef((WALL_THICK * 2) / 60.0, (WALL_HEIGHT) / 60.0, (TILE_LENGTH) / 60.0)
        glutSolidCube(60)
        glPopMatrix()

        glPushMatrix()
        glTranslatef(LANE_HALF_WIDTH + WALL_THICK, 60, z)
        glColor3f(0.3, 0.3, 0.6)
        glScalef((WALL_THICK * 2) / 60.0, (WALL_HEIGHT) / 60.0, (TILE_LENGTH) / 60.0)
        glutSolidCube(60)
        glPopMatrix()

    glPushMatrix()
    glTranslatef(0, 70, finish_z)
    glColor3f(0.1, 0.9, 0.2)
    glScalef(6, 2.5, 0.4)
    glutSolidCube(60)
    glPopMatrix()


def draw_fake_platform_rings():
    for seg in fake_segments:
        z_center = (tiles[seg["start_i"]]["z"] + tiles[seg["end_i"]]["z"]) / 2.0
        glPushMatrix()
        glTranslatef(0, BOOST_REQUIRED_Y, z_center)
        glColor3f(1.0, 1.0, 0.2)
        gluSphere(quadric, 12.0, 16, 16)
        glPopMatrix()


def draw_player():
    glPushMatrix()
    glTranslatef(player_pos[0], player_pos[1], player_pos[2])
    glRotatef(player_yaw, 0, 1, 0)

    glColor3f(0.15, 0.15, 0.15)
    for side in (-1, 1):
        glPushMatrix()
        glTranslatef(10 * side, 0, 0)
        glRotatef(-90, 1, 0, 0)
        gluCylinder(quadric, 6, 6, 25, 10, 1)
        glPopMatrix()

    glPushMatrix()
    glTranslatef(0, 25, 0)
    glColor3f(0.9, 0.8, 0.2)
    glRotatef(-90, 1, 0, 0)
    gluCylinder(quadric, 10, 12, 28, 14, 1)
    glPopMatrix()

    glColor3f(0.9, 0.8, 0.2)
    for side in (-1, 1):
        glPushMatrix()
        glTranslatef(15 * side, 45, 0)
        glRotatef(-90, 1, 0, 0)
        gluCylinder(quadric, 4, 4, 20, 10, 1)
        glPopMatrix()

    glPushMatrix()
    glTranslatef(0, 65, 0)
    glColor3f(0.9, 0.7, 0.6)
    gluSphere(quadric, 12, 12, 12)
    glPopMatrix()

    glPushMatrix()
    glTranslatef(0, 78, 0)
    glColor3f(0.2, 0.2, 0.8)
    glRotatef(-90, 1, 0, 0)
    gluCylinder(quadric, 10, 0, 18, 12, 1)
    glPopMatrix()

    glPopMatrix()


def draw_enemies():
    for enemy in enemies:
        glPushMatrix()
        glTranslatef(enemy["x"], enemy["y"], enemy["z"])

        if enemy["state"] == "chase":
            glColor3f(0.9, 0.1, 0.1)
        else:
            glColor3f(0.5, 0.1, 0.5)
        gluSphere(quadric, ENEMY_BODY_SIZE, 12, 12)

        glColor3f(0.2, 0.2, 0.2)
        leg_angle_step = 360.0 / ENEMY_LEG_COUNT
        for i in range(ENEMY_LEG_COUNT):
            angle = i * leg_angle_step + enemy["leg_phase"]
            angle_rad = math.radians(angle)

            leg_x = math.cos(angle_rad) * (ENEMY_BODY_SIZE * 0.7)
            leg_z = math.sin(angle_rad) * (ENEMY_BODY_SIZE * 0.7)

            leg_bend = math.sin(math.radians(enemy["leg_phase"] * 4 + i * 60)) * 15

            glPushMatrix()
            glTranslatef(leg_x, -5, leg_z)
            glRotatef(angle, 0, 1, 0)
            glRotatef(45 + leg_bend, 1, 0, 0)
            gluCylinder(quadric, ENEMY_LEG_RADIUS, ENEMY_LEG_RADIUS * 0.5, ENEMY_LEG_LENGTH, 6, 1)
            glPopMatrix()

        glPopMatrix()


def draw_falling_hazards():
    for hazard in falling_hazards:
        glPushMatrix()
        glTranslatef(hazard["x"], hazard["y"], hazard["z"])

        glRotatef(hazard["rotation"], 1, 1, 0)

        if hazard["type"] == "cube":
            glColor3f(0.8, 0.3, 0.1)
            glutSolidCube(HAZARD_SIZE * 2)
        else:
            glColor3f(0.9, 0.5, 0.1)
            gluSphere(quadric, HAZARD_SIZE, 10, 10)

        glPopMatrix()


def draw_rotating_obstacles():
    for ob in rot_obstacles:
        glPushMatrix()
        glTranslatef(ob["x"], ob["y"], ob["z"])
        glRotatef(ob["angle"], 0, 1, 0)
        glColor3f(0.9, 0.2, 0.2)
        sx, sy, sz = ob["size"]
        glScalef(sx / 60.0, sy / 60.0, sz / 60.0)
        glutSolidCube(60)
        glPopMatrix()


def draw_moving_platform_hints():
    for mp in moving_platforms:
        i = mp["tile_i"]
        if 0 <= i < NUM_TILES:
            z = tiles[i]["z"]
            glPushMatrix()
            glTranslatef(mp["x"], 90, z)
            glColor3f(0.2, 0.95, 0.95)
            gluSphere(quadric, 14, 12, 12)
            glPopMatrix()


def draw_pink_gates():
    for g in pink_gates:
        z = g["z"]
        glPushMatrix()
        glTranslatef(0, 35, z)
        glColor3f(1.0, 0.0, 1.0)
        glScalef((LANE_HALF_WIDTH * 2 + 50) / 60.0, 0.35, 0.55)
        glutSolidCube(60)
        glPopMatrix()


def draw_closing_walls():
    for wall in closing_walls:
        z = wall["z"]

        glPushMatrix()
        glTranslatef(wall["left_x"], CLOSING_WALL_HEIGHT / 2, z)
        glColor3f(0.7, 0.1, 0.1)
        glScalef(CLOSING_WALL_WIDTH / 60.0, CLOSING_WALL_HEIGHT / 60.0, 0.3)
        glutSolidCube(60)
        glPopMatrix()

        glPushMatrix()
        glTranslatef(wall["right_x"], CLOSING_WALL_HEIGHT / 2, z)
        glColor3f(0.7, 0.1, 0.1)
        glScalef(CLOSING_WALL_WIDTH / 60.0, CLOSING_WALL_HEIGHT / 60.0, 0.3)
        glutSolidCube(60)
        glPopMatrix()


def spawn_falling_hazard():
    global last_hazard_spawn_ms

    now = glutGet(GLUT_ELAPSED_TIME)
    if (now - last_hazard_spawn_ms) < hazard_spawn_interval_ms:
        return

    if len(falling_hazards) >= max_hazards:
        return

    last_hazard_spawn_ms = now

    spawn_z = player_pos[2]
    spawn_x = player_pos[0]

    hazard_type = random.choice(["cube", "sphere"])

    falling_hazards.append({
        "x": spawn_x,
        "y": 300,
        "z": spawn_z,
        "type": hazard_type,
        "rotation": random.uniform(0, 360),
        "rot_speed": random.uniform(3, 8)
    })


def update_platforms():
    for mp in moving_platforms:
        mp["x"] += mp["dir"] * mp["speed"] * (1.0 + 0.08 * (difficulty_level - 1))
        if mp["x"] > mp["maxx"]:
            mp["x"] = mp["maxx"]
            mp["dir"] = -1
        elif mp["x"] < mp["minx"]:
            mp["x"] = mp["minx"]
            mp["dir"] = 1


def update_obstacles():
    for ob in rot_obstacles:
        ob["angle"] = (ob["angle"] + ob["speed"] * (1.0 + 0.10 * (difficulty_level - 1))) % 360


def update_closing_walls():
    for wall in closing_walls:
        wall["left_x"] += wall["direction"] * wall["speed"] * (1.0 + 0.12 * (difficulty_level - 1))
        wall["right_x"] -= wall["direction"] * wall["speed"] * (1.0 + 0.12 * (difficulty_level - 1))

        if wall["direction"] == 1:
            if wall["left_x"] >= -CLOSING_WALL_MIN_OPEN:
                wall["direction"] = -1
        else:
            if wall["left_x"] <= -CLOSING_WALL_MAX_OPEN:
                wall["direction"] = 1


def update_enemies():
    for enemy in enemies:
        enemy["leg_phase"] = (enemy["leg_phase"] + 2.5) % 360

        dist_to_player = distance_2d(enemy["x"], enemy["z"], player_pos[0], player_pos[2])

        if dist_to_player < ENEMY_CHASE_DISTANCE:
            enemy["state"] = "chase"
            dx = player_pos[0] - enemy["x"]
            dz = player_pos[2] - enemy["z"]
            dist = math.sqrt(dx * dx + dz * dz)
            if dist > 0.1:
                enemy["x"] += (dx / dist) * (ENEMY_CHASE_SPEED * (1.0 + 0.12 * (difficulty_level - 1)))
                enemy["z"] += (dz / dist) * (ENEMY_CHASE_SPEED * (1.0 + 0.12 * (difficulty_level - 1)))
        else:
            enemy["state"] = "roam"
            enemy["roam_angle"] = (enemy["roam_angle"] + (1.5 + 0.2 * (difficulty_level - 1))) % 360
            angle_rad = math.radians(enemy["roam_angle"])
            enemy["x"] = enemy["center_x"] + math.cos(angle_rad) * enemy["roam_radius"]
            enemy["z"] = enemy["center_z"] + math.sin(angle_rad) * enemy["roam_radius"]

        enemy["x"] = clamp(enemy["x"], -LANE_HALF_WIDTH + ENEMY_RADIUS, LANE_HALF_WIDTH - ENEMY_RADIUS)


def update_falling_hazards():
    global falling_hazards

    for hazard in falling_hazards[:]:
        hazard["y"] -= hazard_fall_speed
        hazard["rotation"] = (hazard["rotation"] + hazard["rot_speed"]) % 360

        if hazard["y"] < -50:
            falling_hazards.remove(hazard)


def check_hazard_collision():
    global player_life, game_over, last_damage_ms

    now = glutGet(GLUT_ELAPSED_TIME)
    if (now - last_damage_ms) < 500:
        return

    px, py, pz = player_pos[0], player_pos[1] + 25, player_pos[2]

    for hazard in falling_hazards[:]:
        dist = distance_3d(px, py, pz, hazard["x"], hazard["y"], hazard["z"])
        if dist < (PLAYER_RADIUS + HAZARD_SIZE):
            player_life -= HAZARD_DAMAGE
            last_damage_ms = now
            falling_hazards.remove(hazard)

            if player_life <= 0:
                player_life = 0
                game_over = True
            break


def check_enemy_damage():
    global player_life, game_over, last_damage_ms

    now = glutGet(GLUT_ELAPSED_TIME)
    if (now - last_damage_ms) < ENEMY_DAMAGE_COOLDOWN_MS:
        return

    px, pz = player_pos[0], player_pos[2]
    for enemy in enemies:
        dist = distance_2d(px, pz, enemy["x"], enemy["z"])
        if dist < ENEMY_DAMAGE_DISTANCE:
            player_life -= 10
            last_damage_ms = now
            if player_life <= 0:
                player_life = 0
                game_over = True
            break


def trigger_fake_segment_if_needed():
    seg = player_in_fake_segment()
    if seg is None or seg["triggered"]:
        return
    if player_pos[1] <= 1.0:
        seg["triggered"] = True
        for ti in range(seg["start_i"], seg["end_i"] + 1):
            tiles[ti]["falling"] = True


def update_falling_fake_tiles():
    for t in tiles:
        if t["type"] == "fake" and t["falling"]:
            if t["fall_y"] > FAKE_FALL_KILL_Y:
                t["fall_y"] -= FAKE_FALL_SPEED


def apply_physics_and_ground():
    global player_vel_y, player_on_ground, game_over

    player_vel_y += GRAVITY
    player_pos[1] += player_vel_y

    ti = get_tile_index_from_z(player_pos[2])
    seg = player_in_fake_segment()
    in_triggered_fake = (seg is not None and seg["triggered"])

    if in_triggered_fake:
        falling_y = tiles[ti]["fall_y"] if (ti is not None) else 0.0
        if player_pos[1] <= (falling_y + FAKE_FAIL_TOUCH_EPS):
            game_over = True
            return
        player_on_ground = False
        return

    if ti is not None and is_tile_solid(ti):
        mp = moving_platform_for_tile(ti)
        if mp:
            cx = mp["x"]
            halfw = MOVING_PLATFORM_HALF_WIDTH
        else:
            cx = 0.0
            halfw = LANE_HALF_WIDTH

        if not (cx - halfw <= player_pos[0] <= cx + halfw):
            player_on_ground = False
        else:
            surf_y = tile_surface_y(ti)
            if surf_y is not None and player_pos[1] <= surf_y:
                player_pos[1] = surf_y
                player_vel_y = 0.0
                player_on_ground = True
            else:
                player_on_ground = False
    else:
        player_on_ground = False

    if player_pos[1] < -250:
        game_over = True


def check_rot_obstacle_collision():
    global game_over
    px, py, pz = player_pos[0], player_pos[1] + 25, player_pos[2]
    for ob in rot_obstacles:
        sx, sy, sz = ob["size"][0] / 2, ob["size"][1] / 2, ob["size"][2] / 2
        if aabb_overlap(px, py, pz, PLAYER_RADIUS, ob["x"], ob["y"], ob["z"], sx, sy, sz):
            game_over = True
            return


def check_pink_gate_collision():
    global game_over

    px = player_pos[0]
    py = player_pos[1] + 25
    pz = player_pos[2]

    beam_y = 35.0
    beam_half_x = (LANE_HALF_WIDTH * 2 + 50) / 2.0
    beam_half_y = 0.35 * 60 / 2.0
    beam_half_z = 0.55 * 60 / 2.0

    for g in pink_gates:
        gz = g["z"]
        if aabb_overlap(px, py, pz, PLAYER_RADIUS, 0.0, beam_y, gz,
                        beam_half_x, beam_half_y, beam_half_z):
            game_over = True
            return


def check_closing_wall_collision():

    global player_pos, player_yaw, player_vel_y, player_on_ground

    px = player_pos[0]
    py = player_pos[1] + 25
    pz = player_pos[2]

    wall_half_width = CLOSING_WALL_WIDTH / 2.0
    wall_half_height = CLOSING_WALL_HEIGHT / 2.0
    wall_half_depth = 0.3 * 60 / 2.0

    for wall in closing_walls:
        gz = wall["z"]


        if aabb_overlap(px, py, pz, PLAYER_RADIUS,
                        wall["left_x"], wall_half_height, gz,
                        wall_half_width, wall_half_height, wall_half_depth):

            player_pos[0] = 0.0
            player_pos[1] = 0.0
            player_pos[2] = 0.0
            player_yaw = 0.0
            player_vel_y = 0.0
            player_on_ground = True
            return


        if aabb_overlap(px, py, pz, PLAYER_RADIUS,
                        wall["right_x"], wall_half_height, gz,
                        wall_half_width, wall_half_height, wall_half_depth):

            player_pos[0] = 0.0
            player_pos[1] = 0.0
            player_pos[2] = 0.0
            player_yaw = 0.0
            player_vel_y = 0.0
            player_on_ground = True
            return


def check_win_and_timer():
    global game_over, win
    if game_over or win:
        return
    elapsed = (glutGet(GLUT_ELAPSED_TIME) - start_ms) / 1000.0
    if (TIME_LIMIT_SEC - elapsed) <= 0:
        game_over = True
        return
    if player_pos[2] >= finish_z:
        win = True


def move_forward(sign):
    yaw_rad = math.radians(player_yaw)
    player_pos[0] += math.sin(yaw_rad) * move_speed * sign
    player_pos[2] += math.cos(yaw_rad) * move_speed * sign
    player_pos[0] = clamp(player_pos[0], -LANE_HALF_WIDTH + 18, LANE_HALF_WIDTH - 18)


def keyboardListener(key, x, y):
    global last_boost_ms, player_vel_y, player_on_ground, game_started, game_paused, camera_first_person, cheat_pass_obstacles, cheat_auto_collect_items


    if key == b's' and not game_started and not game_over and not win:
        game_started = True
        return


    if key == b'v' and game_started:
        game_paused = not game_paused
        return


    if key == b'c' and game_started:
        camera_first_person = not camera_first_person
        return


    if key == b'1':
        cheat_pass_obstacles = not cheat_pass_obstacles
        return


    if key == b'2':
        cheat_auto_collect_items = not cheat_auto_collect_items
        return

    if key == b'r':
        reset_game()
        return
    if game_over or win:
        return

    if key in keys_down:
        keys_down[key] = True

    if key == b' ':
        now = glutGet(GLUT_ELAPSED_TIME)
        if player_on_ground and (now - last_boost_ms) >= BOOST_COOLDOWN_MS:
            player_vel_y = BOOST_VEL
            player_on_ground = False
            last_boost_ms = now


def keyboardUpListener(key, x, y):
    if key in keys_down:
        keys_down[key] = False


def specialKeyListener(key, x, y):
    global player_vel_y, player_on_ground, jump_pressed
    if game_over or win:
        return
    if key == GLUT_KEY_UP and (not jump_pressed):
        jump_pressed = True
        if player_on_ground:
            player_vel_y = JUMP_VEL
            player_on_ground = False


def specialKeyUpListener(key, x, y):
    global jump_pressed
    if key == GLUT_KEY_UP:
        jump_pressed = False


def mouseListener(button, state, x, y):
    global camera_first_person
    if button == GLUT_RIGHT_BUTTON and state == GLUT_DOWN and game_started:
        camera_first_person = not camera_first_person



def idle():
    global player_yaw, game_over, player_vel_y, player_on_ground
    if start_ms is None:
        return

    if not (game_over or win) and game_started and not game_paused:
        if keys_down[b'a']:
            player_yaw = (player_yaw + ROT_SPEED) % 360
        if keys_down[b'd']:
            player_yaw = (player_yaw - ROT_SPEED) % 360

        if keys_down[b'w']:
            move_forward(+1)
        if keys_down[b's']:
            move_forward(-1)

        update_platforms()
        update_obstacles()
        update_closing_walls()
        update_enemies()
        spawn_falling_hazard()
        update_falling_hazards()
        trigger_fake_segment_if_needed()
        update_falling_fake_tiles()

        apply_physics_and_ground()


        maybe_trigger_checkpoint_and_scale()


        check_gem_collection(auto_collect=cheat_auto_collect_items)


        if cheat_pass_obstacles:
            if player_pos[1] < -200:
                player_pos[1] = 0.0
                player_vel_y = 0.0
                player_on_ground = True

                game_over = False
        else:
            check_rot_obstacle_collision()
            check_pink_gate_collision()
            check_closing_wall_collision()
            check_enemy_damage()
            check_hazard_collision()

        check_win_and_timer()

    glutPostRedisplay()


def showScreen():
    glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)
    glViewport(0, 0, WINDOW_W, WINDOW_H)

    setupCamera()

    draw_floor_and_walls()
    draw_fake_platform_rings()
    draw_rotating_obstacles()
    draw_pink_gates()
    draw_closing_walls()
    draw_moving_platform_hints()
    draw_falling_hazards()
    draw_enemies()
    draw_gems()
    draw_player()

    elapsed = (glutGet(GLUT_ELAPSED_TIME) - start_ms) / 1000.0
    remaining = max(0.0, TIME_LIMIT_SEC - elapsed)

    draw_text(10, WINDOW_H - 25,
              f"Life: {player_life}/{PLAYER_MAX_LIFE} | Score: {score} | Gems: {sum(1 for g in gems if g['collected'])}/{len(gems)} | Diff: {difficulty_level} | Timer: {remaining:0.1f}s")
    draw_text(10, WINDOW_H - 50, "Keys: W move | A/D rotate | Up jump | Space BOOST | C / RightClick cam | 1 cheat-pass | 2 cheat-items")
    draw_text(10, WINDOW_H - 75,
              f"Mode: {'FPS' if camera_first_person else '3rd'} | Cheat1(pass): {'ON' if cheat_pass_obstacles else 'OFF'} | Cheat2(items): {'ON' if cheat_auto_collect_items else 'OFF'}")

    if game_over:
        draw_text(int(WINDOW_W * 0.42), int(WINDOW_H * 0.52), "GAME OVER")
        draw_text(int(WINDOW_W * 0.33), int(WINDOW_H * 0.48), "Press R to restart")
    elif win:
        draw_text(int(WINDOW_W * 0.44), int(WINDOW_H * 0.52), "YOU WIN!")
        draw_text(int(WINDOW_W * 0.33), int(WINDOW_H * 0.48), "Press R to play again")



    if not game_started:
        draw_text(int(WINDOW_W * 0.35), int(WINDOW_H * 0.52), "Press 'S' to START")

    if game_paused and game_started:
        draw_text(int(WINDOW_W * 0.42), int(WINDOW_H * 0.52), "PAUSED")
        draw_text(int(WINDOW_W * 0.35), int(WINDOW_H * 0.48), "Press 'V' to Resume")




    glutSwapBuffers()


def main():
    global quadric

    glutInit()
    glutInitDisplayMode(GLUT_DOUBLE | GLUT_RGB | GLUT_DEPTH)
    glutInitWindowSize(WINDOW_W, WINDOW_H)
    glutInitWindowPosition(0, 0)
    glutCreateWindow(b"Rage Path")

    glEnable(GL_DEPTH_TEST)


    quadric = gluNewQuadric()
    reset_game()


    glutDisplayFunc(showScreen)
    glutKeyboardFunc(keyboardListener)
    glutKeyboardUpFunc(keyboardUpListener)
    glutSpecialFunc(specialKeyListener)
    glutSpecialUpFunc(specialKeyUpListener)
    glutMouseFunc(mouseListener)
    glutIdleFunc(idle)

    glutMainLoop()


if __name__ == "__main__":
    main()