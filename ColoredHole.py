import math
import random
import pygame

pygame.init()

screen = pygame.display.set_mode((960, 600))
pygame.display.set_caption("DemoHole")
canvas = pygame.Surface((320, 200))
fade = pygame.Surface(canvas.get_size())
fade.fill((5, 5, 10))
fade.set_alpha(40)
clock = pygame.time.Clock()

#tochki
ring_radii = [39, 46, 54, 63, 73, 84, 96, 109, 122]
ring_drift = 2.8
particles = []
for _ in range(1600):
    ring = random.randrange(len(ring_radii))
    offset = random.gauss(0, 0.9)
    radius = max(34.1, min(127.9, ring_radii[ring] + offset))
    heat = (128 - radius) / (128 - 34)
    particles.append({
        "ring": ring,
        "offset": offset,
        "radius": radius,
        "angle": random.uniform(0, math.tau),
        "speed": 1.8 * (60 / radius)**1.5,
        "color": (255, int(130 + 110 * heat), int(45 + 160 * heat)),
    })

running = True
#bg stars
stars = []
for _ in range(100):
    x = random.randrange(canvas.get_width())
    y = random.randrange(canvas.get_height())
    brightness = random.randint(35, 140)

    stars.append((x, y, brightness))
#Glow effect
glow_cache = {}

def draw_particle(point, tail, color):
    if max(color) < 6:
        return
    key = tuple(channel // 16 * 16 for channel in color)
    glow = glow_cache.get(key)
    if glow is None:
        glow = pygame.Surface((9, 9), pygame.SRCALPHA)
        pygame.draw.circle(glow, (*key, 20), (4, 4), 4)
        pygame.draw.circle(glow, (*key, 65), (4, 4), 2)
        glow_cache[key] = glow

    pygame.draw.line(canvas, tuple(int(channel * 0.4) for channel in color), tail, point)
    canvas.blit(glow, (point[0] - 4, point[1] - 4))
    pygame.draw.circle(canvas, color, point, 1)


def project_particle(angle, radius, scale, tilt):
    side = math.sin(angle)
    x = math.cos(angle) * radius
    y = side * radius * tilt
    if side < 0:
        arc_radius = min(radius, 36 + (radius - 34) * 0.18)
        arc_height = math.sqrt(max(0, arc_radius**2 - x**2))
        y -= max(0, arc_height + y) * (1 - tilt)
    return (
        round(160 + x * scale),
        round(100 + y * scale),
    )


def make_horizon_glow(scale):
    size = max(3, math.ceil(44 * scale))
    halo = pygame.Surface((size * 2 + 1, size * 2 + 1), pygame.SRCALPHA)
    width = max(0.7, 1.1 * scale)
    for radius in range(max(1, round(29 * scale)), size + 1):
        distance = radius - 33 * scale
        core = math.exp(-0.5 * (distance / width)**2)
        haze = math.exp(-0.5 * (distance / (width * 3))**2)
        alpha = min(255, round(190 * core + 32 * haze))
        if alpha:
            color = (255, round(160 + 80 * core), round(70 + 150 * core), alpha)
            pygame.draw.circle(halo, color, (size, size), radius, 1)
    return halo, size


star_shift = 0
simulation_time = 0
view_angle = 0
tilt = 0.15
zoom = 1.0
dragging = False
halo_key = None
halo = None
halo_size = 0

while running:
    dt = clock.tick(60) / 1000

    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            running = False
        elif event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
            running = False
        elif event.type == pygame.KEYDOWN and event.key == pygame.K_r:
            view_angle = 0
            tilt = 0.15
            zoom = 1.0
            canvas.fill((5, 5, 10))
        elif event.type == pygame.MOUSEWHEEL:
            zoom = max(0.5, min(2.5, zoom * 1.12**event.y))
            canvas.fill((5, 5, 10))
        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 3:
            dragging = True
        elif event.type == pygame.MOUSEBUTTONUP and event.button == 3:
            dragging = False
        elif event.type == pygame.WINDOWFOCUSLOST:
            dragging = False
        elif event.type == pygame.MOUSEMOTION and dragging:
            view_angle = (view_angle + event.rel[0] * 0.01) % math.tau
            tilt = max(0.04, min(1.0, tilt + event.rel[1] * 0.005))
            canvas.fill((5, 5, 10))

    if not running:
        break

    simulation_time += dt
    extent = max(128 * tilt, 36 + (128 - 34) * 0.18)
    view_scale = zoom * min(1.0, 85 / extent)
    canvas.blit(fade, (0, 0))

    star_shift = (star_shift + 4 * dt) % canvas.get_width()

    for star_x, star_y, brightness in stars:
        x = (star_x + star_shift) % canvas.get_width()
        y = star_y

        dx = x - 160
        dy = y - 100

        distance2 = dx * dx + dy * dy
        bend = 1 + 600 * view_scale**2 / (distance2 + 100)

        px = int(160 + dx * bend)
        py = int(100 + dy * bend)

        if 0 <= px < canvas.get_width() and 0 <= py < canvas.get_height():
            canvas.set_at((px, py), (brightness, brightness, brightness))

    front_particles = []
    recycled_rings = set()
    ring_follow = 1 - math.exp(-9 * dt)

    for index, radius in enumerate(ring_radii):
        radius -= ring_drift * dt
        if radius <= 34:
            radius = 128
            recycled_rings.add(index)
        ring_radii[index] = radius

    for particle in particles:
        ring = particle["ring"]
        ripple = 0.35 * math.sin(2 * particle["angle"] + simulation_time * 0.5)
        target_radius = max(34.1, min(127.9, ring_radii[ring] + particle["offset"] + ripple))
        if ring in recycled_rings:
            particle["radius"] = target_radius
            particle["angle"] = random.uniform(0, math.tau)
        else:
            particle["radius"] += (target_radius - particle["radius"]) * ring_follow

        particle["speed"] = 1.8 * (60 / particle["radius"])**1.5

        particle["angle"] = (particle["angle"] + particle["speed"] * dt) % math.tau
        world_angle = particle["angle"]
        angle = world_angle + view_angle
        radius = particle["radius"]
        side = math.sin(angle)

        point = project_particle(angle, radius, view_scale, tilt)
        tail_angle = angle - particle["speed"] * 0.035
        tail = project_particle(tail_angle, radius, view_scale, tilt)
        if side * math.sin(tail_angle) < 0:
            tail = point

        heat = (128 - particle["radius"]) / (128 - 34)
        heat = max(0, min(1, heat))

        phase = 3 * world_angle - radius * 0.12 - simulation_time * 0.4
        filament = (0.5 + 0.5 * math.sin(phase))**4
        turbulence = 0.85 + 0.15 * math.sin(7 * world_angle - radius * 0.45 + simulation_time * 1.8)
        beaming = (1 + 0.32 * math.cos(angle) * (1 - tilt))**2
        edge = min(1.0, max(0.0, (128 - radius) / 7))
        edge *= min(1.0, max(0.0, (radius - 34) / 2.5))
        intensity = (0.24 + 0.76 * filament) * turbulence * beaming
        intensity *= (0.45 + 2.6 * heat**1.5) * edge
        channels = (1.4, 0.30 + 1.05 * heat, 0.04 + 1.15 * heat**3)
        particle["color"] = tuple(
            round(255 * (1 - math.exp(-intensity * channel)))
            for channel in channels
        )

        if side >= 0:
            front_particles.append((point, tail, particle["color"]))
        else:
            draw_particle(point, tail, particle["color"])

    scale_key = round(view_scale, 3)
    if scale_key != halo_key:
        halo, halo_size = make_horizon_glow(view_scale)
        halo_key = scale_key
    canvas.blit(halo, (160 - halo_size, 100 - halo_size))
    pygame.draw.circle(canvas, (0, 0, 0), (160, 100), round(32 * view_scale))

    for point, tail, color in front_particles:
        draw_particle(point, tail, color)

    screen.blit(pygame.transform.scale(canvas, screen.get_size()), (0, 0))
    pygame.display.flip()

pygame.quit()
