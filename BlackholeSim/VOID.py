import argparse
import os
import sys

sys.dont_write_bytecode = True

import numpy as np
import pygame

if __package__:
    from .renderer import BlackHoleRenderer
else:
    from renderer import BlackHoleRenderer

class Camera:
    def __init__(self, yaw=.45, pitch=.24, distance=19.):
        self.yaw, self.pitch, self.distance = yaw, pitch, distance
        self.fov = np.deg2rad(55.)
        self.update()

    def update(self):
        self.pitch = float(np.clip(self.pitch, -1.48, 1.48))
        self.distance = float(np.clip(self.distance, 11., 33.))
        self.position = self.distance * np.array([
            np.cos(self.pitch) * np.sin(self.yaw), np.sin(self.pitch),
            np.cos(self.pitch) * np.cos(self.yaw)])
        self.forward = -self.position / self.distance
        self.right = np.cross(self.forward, (0., 1., 0.))
        self.right /= np.linalg.norm(self.right)
        self.up = np.cross(self.right, self.forward)

    def orbit(self, dx, dy):
        self.yaw -= dx * .006
        self.pitch += dy * .006
        self.update()

    def zoom(self, steps):
        self.distance *= np.exp(-steps * .09)
        self.update()

    def project(self, points, width, height):
        relative = np.asarray(points) - self.position
        depth = relative @ self.forward
        focal = height / (2 * np.tan(self.fov / 2))
        safe_depth = np.maximum(depth, .01)
        x = width / 2 + (relative @ self.right) * focal / safe_depth
        y = height / 2 - (relative @ self.up) * focal / safe_depth
        return np.column_stack((x, y)), depth


def make_grid(camera, size):
    width, height = size
    grid = pygame.Surface(size)
    axis = np.linspace(-16, 16, 90)
    for value in range(-16, 17, 2):
        for swap in (False, True):
            x, z = (axis, np.full_like(axis, value)) if not swap else (np.full_like(axis, value), axis)
            radius = np.sqrt(x*x + z*z)
            points = np.column_stack((x, -1.7-3.8/(radius+.8), z))
            pixels, depth = camera.project(points, width, height)
            valid = (depth > 1) & (np.abs(pixels[:, 0]) < width*3) & (np.abs(pixels[:, 1]) < height*3)
            indices = np.flatnonzero(valid)
            for segment in np.split(indices, np.flatnonzero(np.diff(indices) > 1)+1):
                if len(segment) > 1:
                    pygame.draw.lines(grid, (33, 39, 31), False, pixels[segment].astype(int).tolist())
    return grid


def draw_grid(surface, camera, grid, shadow_mask):
    width, height = surface.get_size()
    image = pygame.surfarray.array3d(surface)
    overlay = grid.copy()
    pixels = pygame.surfarray.pixels3d(overlay)
    focal = height / (2 * np.tan(camera.fov / 2))
    xx, yy = np.ogrid[:width, :height]
    hidden = (image.max(axis=2) > 42) | shadow_mask.T
    hidden |= (xx-width/2)**2 + (yy-height/2)**2 < (focal*3.8/camera.distance)**2
    pixels[hidden] = 0
    del pixels
    surface.blit(overlay, (0, 0), special_flags=pygame.BLEND_RGB_ADD)


def main(renderer_class=BlackHoleRenderer, camera_factory=Camera,
         title="VOID / EVENT HORIZON", render_width=220,
         default_size=(1280, 800), view_pitches=(.24, .015, 1.45),
         view_distance=19.):
    parser = argparse.ArgumentParser(description=title)
    parser.add_argument("--smoke-test", action="store_true")
    parser.add_argument("--frames", type=int, default=0)
    parser.add_argument("--width", type=int, default=default_size[0])
    parser.add_argument("--height", type=int, default=default_size[1])
    args = parser.parse_args()
    if args.smoke_test:
        os.environ["SDL_VIDEODRIVER"] = "dummy"
        os.environ["SDL_AUDIODRIVER"] = "dummy"
    pygame.display.init()
    size = (max(800, args.width), max(540, args.height))
    screen = pygame.display.set_mode(size, pygame.RESIZABLE)
    pygame.display.set_caption(title)
    clock = pygame.time.Clock()
    camera = camera_factory()
    renderer = None
    paused, fullscreen = False, False
    grid_visible = True
    grid_key, cached_grid = None, None
    frames, simulation_time = 0, 0.
    dragging, running = False, True

    def resize_renderers():
        nonlocal renderer, grid_key
        width, height = screen.get_size()
        render_height = max(50, round(render_width*height/width))
        renderer = renderer_class(render_width, render_height)
        grid_key = None

    resize_renderers()
    while running:
        elapsed = min(clock.tick(60)/1000, .08)
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.VIDEORESIZE and not fullscreen:
                size = (max(800, event.w), max(540, event.h))
                screen = pygame.display.set_mode(size, pygame.RESIZABLE)
                resize_renderers()
            elif event.type == pygame.MOUSEWHEEL:
                camera.zoom(event.y)
            elif event.type == pygame.MOUSEBUTTONDOWN:
                if event.button == 3:
                    dragging = True
                    pygame.mouse.get_rel()
            elif event.type == pygame.MOUSEBUTTONUP and event.button == 3:
                dragging = False
            elif event.type == pygame.WINDOWFOCUSLOST:
                dragging = False
            elif event.type == pygame.MOUSEMOTION and dragging:
                camera.orbit(*event.rel)
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    running = False
                elif event.key == pygame.K_SPACE:
                    paused = not paused
                elif event.key == pygame.K_r:
                    simulation_time = 0.
                elif event.key == pygame.K_g:
                    grid_visible = not grid_visible
                elif event.key in (pygame.K_1, pygame.K_2, pygame.K_3):
                    camera.yaw = .45
                    camera.pitch = dict(zip((pygame.K_1, pygame.K_2, pygame.K_3), view_pitches))[event.key]
                    camera.distance = view_distance
                    camera.update()
                elif event.key == pygame.K_F11:
                    fullscreen = not fullscreen
                    screen = pygame.display.set_mode((0, 0) if fullscreen else size, pygame.FULLSCREEN if fullscreen else pygame.RESIZABLE)
                    resize_renderers()
        if not running:
            break
        if not paused:
            simulation_time += elapsed
        frame = renderer.render(camera, simulation_time)
        if grid_visible:
            key = (*camera.position, frame.get_size())
            if key != grid_key:
                cached_grid = make_grid(camera, frame.get_size())
                grid_key = key
            draw_grid(frame, camera, cached_grid, renderer.shadow_mask)
        screen.blit(pygame.transform.scale(frame, screen.get_size()), (0, 0))
        pygame.display.flip()
        frames += 1
        limit = args.frames or (60 if args.smoke_test else 0)
        if limit and frames >= limit:
            running = False
    pygame.quit()


if __name__ == "__main__":
    main()
