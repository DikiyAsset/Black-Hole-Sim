import math
import random
import pygame

pygame.init()

screen = pygame.display.set_mode((960, 600))
pygame.display.set_caption("DemoHole")
canvas = pygame.Surface(screen.get_size())
fade = pygame.Surface(canvas.get_size())
fade.fill((5, 5, 10))
fade.set_alpha(40)
clock = pygame.time.Clock()

view_angle = 0
view_tilt = 54 / 310
zoom = 1.0
dragging = False

color_stops = [
    (255, 110, 30),
    (255, 170, 80),
    (255, 220, 160),
    (255, 250, 235),
]

colors = []
for index in range(32):
    value = index / 31 * (len(color_stops) - 1)
    step = min(int(value), len(color_stops) - 2)
    mix = value - step
    color = tuple(round(a + (b - a) * mix)
                  for a, b in zip(color_stops[step], color_stops[step + 1]))
    colors.append(color)

glows = []
for color in colors:
    levels = []
    for level in range(8):
        opacity = level / 7
        glow = pygame.Surface((63, 63), pygame.SRCALPHA)
        pygame.draw.circle(glow, (*color, round(12 * opacity)), (31, 31), 27)
        pygame.draw.circle(glow, (*color, round(35 * opacity)), (31, 31), 18)
        pygame.draw.circle(glow, (*color, round(255 * opacity)), (31, 31), 9)
        levels.append(pygame.transform.smoothscale(glow, (21, 21)))
    glows.append(levels)

halo = pygame.Surface((780, 780), pygame.SRCALPHA)
for radius in range(282, 391):
    distance = abs(radius / 3 - 98)
    core = max(0, 1 - distance / 3)
    haze = max(0, 1 - distance / 24)
    alpha = round(190 * core + 24 * haze)
    color = (255, round(180 + 65 * core), round(90 + 135 * core), alpha)
    pygame.draw.circle(halo, color, (390, 390), radius, 1)
halo = pygame.transform.smoothscale(halo, (260, 260))

shadow = pygame.Surface((600, 600), pygame.SRCALPHA)
pygame.draw.circle(shadow, (0, 0, 0, 255), (300, 300), 288)
shadow = pygame.transform.smoothscale(shadow, (200, 200))


def smoothstep(value):
    value = max(0, min(1, value))
    return value * value * (3 - 2 * value)


def project_particle(angle, scale):
    angle += view_angle
    side = math.sin(angle)
    x = 310 * scale * math.cos(angle)
    y = 310 * scale * side * view_tilt
    if side < 0:
        radius = 100 + 14 * scale
        transition = smoothstep((radius - abs(x)) / 35)
        bend = max(0, radius * radius - x * x) * transition
        blend = smoothstep(-side * 4)
        strength = (1 - view_tilt) / (1 - 54 / 310)
        y = -math.sqrt(y * y + bend * blend * blend * strength)
    return (round(480 + x), round(300 + y)), side


def draw_particle(point, tail, color_index, brightness):
    level = round(brightness * 7)
    if level == 0:
        return
    tail_color = tuple(round(channel * brightness * 0.35)
                       for channel in colors[color_index])
    pygame.draw.aaline(canvas, tail_color, tail, point)
    canvas.blit(glows[color_index][level], (point[0] - 10, point[1] - 10))


ring_radii = [39, 46, 54, 63, 73, 84, 96, 109, 122]
ring_drift = 2.8
simulation_time = 0

particles = []
for _ in range(1600):
    ring = random.randrange(len(ring_radii))
    offset = random.gauss(0, 0.9)
    radius = max(34.1, min(127.9, ring_radii[ring] + offset))
    particles.append({
        "ring": ring,
        "offset": offset,
        "radius": radius,
        "angle": random.uniform(0, math.tau),
    })

stars = []
for _ in range(100):
    x = random.randrange(canvas.get_width())
    y = random.randrange(canvas.get_height())
    brightness = random.randint(35, 140)
    stars.append((x, y, brightness))

running = True
while running:
    dt = clock.tick(60) / 1000

    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            running = False
        elif event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
            running = False
        elif event.type == pygame.KEYDOWN and event.key == pygame.K_r:
            view_angle = 0
            view_tilt = 54 / 310
            zoom = 1.0
            canvas.fill((5, 5, 10))
        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 3:
            dragging = True
        elif event.type == pygame.MOUSEBUTTONUP and event.button == 3:
            dragging = False
        elif event.type == pygame.WINDOWFOCUSLOST:
            dragging = False
        elif event.type == pygame.MOUSEMOTION and dragging:
            view_angle = (view_angle + event.rel[0] * 0.008) % math.tau
            view_tilt = max(0.04, min(1, view_tilt - event.rel[1] * 0.004))
            canvas.fill((5, 5, 10))
        elif event.type == pygame.MOUSEWHEEL:
            zoom = max(0.5, min(2.0, zoom + event.y * 0.1))

    if not running:
        break

    simulation_time += dt
    canvas.blit(fade, (0, 0))

    for x, y, brightness in stars:
        canvas.set_at((x, y), (brightness, brightness, brightness))

    recycled_rings = set()
    ring_follow = 1 - math.exp(-9 * dt)
    for index, radius in enumerate(ring_radii):
        radius -= ring_drift * dt
        if radius <= 34:
            radius = 128
            recycled_rings.add(index)
        ring_radii[index] = radius

    front_particles = []
    for particle in particles:
        ring = particle["ring"]
        ripple = 0.35 * math.sin(2 * particle["angle"] + simulation_time * 0.5)
        target_radius = max(34.1, min(127.9,
                            ring_radii[ring] + particle["offset"] + ripple))
        if ring in recycled_rings:
            particle["radius"] = target_radius
            particle["angle"] = random.uniform(0, math.tau)
        else:
            particle["radius"] += (target_radius - particle["radius"]) * ring_follow

        radius = particle["radius"]
        speed = 1.8 * (60 / radius) ** 1.5
        particle["angle"] = (particle["angle"] + speed * dt) % math.tau
        angle = particle["angle"]
        heat = (128 - radius) / 94
        scale = 1.04 - 0.74 * heat
        point, side = project_particle(angle, scale)
        tail, tail_side = project_particle(angle - speed * 0.035, scale)
        if side * tail_side < 0:
            tail = point

        phase = 3 * angle - radius * 0.12 - simulation_time * 0.4
        filament = (0.5 + 0.5 * math.sin(phase)) ** 4
        turbulence = 0.85 + 0.15 * math.sin(
            7 * angle - radius * 0.45 + simulation_time * 1.8)
        beaming = (1 + 0.32 * math.cos(angle + view_angle) * (1 - view_tilt)) ** 2
        edge = min(1, max(0, (128 - radius) / 7))
        edge *= min(1, max(0, (radius - 34) / 2.5))
        intensity = (0.24 + 0.76 * filament) * turbulence * beaming
        intensity *= (0.45 + 2.6 * heat ** 1.5) * edge
        brightness = 1 - math.exp(-intensity)
        color_index = round(heat * (len(colors) - 1))
        if side >= 0:
            front_particles.append((point, tail, color_index, brightness))
        else:
            draw_particle(point, tail, color_index, brightness)

    canvas.blit(halo, (350, 170))
    canvas.blit(shadow, (380, 200))

    for point, tail, color_index, brightness in front_particles:
        draw_particle(point, tail, color_index, brightness)

    if zoom == 1.0:
        screen.blit(canvas, (0, 0))
    else:
        size = (round(canvas.get_width() * zoom),
                round(canvas.get_height() * zoom))
        frame = pygame.transform.smoothscale(canvas, size)
        screen.fill((5, 5, 10))
        screen.blit(frame, frame.get_rect(center=screen.get_rect().center))
    pygame.display.flip()

pygame.quit()
