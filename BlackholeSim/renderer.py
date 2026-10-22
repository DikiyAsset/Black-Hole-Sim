from __future__ import annotations

import math
import time as clock

import numpy as np
import pygame


class BlackHoleRenderer:
    inner_radius = 2.78
    outer_radius = 8.0

    def __init__(self, width: int = 480, height: int = 300) -> None:
        self.width = int(width)
        self.height = int(height)
        self.shadow_mask = np.zeros((height, width), dtype=bool)
        self._key = None
        self._maps = None
        self._orbit_distance = None
        self._orbits = None
        self.trace_seconds = 0.0

    def invalidate(self) -> None:
        self._key = None

    def render(self, camera, time: float) -> pygame.Surface:
        camera_key = tuple(np.round(np.r_[camera.position, camera.right,
                                        camera.up, camera.forward, camera.fov], 5))
        if camera_key != self._key:
            self._key = camera_key
            self._maps = self._trace(camera, self.width, self.height)

        maps = self._maps
        pixels = maps["pixels"].copy()
        hit = maps["hit"]
        if np.any(hit):
            radius = maps["disk_radius"]
            phi = maps["disk_phi"]
            flow = phi - time * maps["rotation"]
            warp = np.sin(flow * 5.0 + radius * 1.35) * 1.1
            filaments = (
                0.64
                + 0.18 * np.sin(radius * 25.0 + warp + flow * 3.0)
                + 0.11 * np.sin(radius * 61.0 - flow * 17.0 + warp)
                + 0.065 * np.sin(radius * 137.0 + flow * 71.0)
            )
            grain = np.sin(flow * 239.0 + radius * 351.0) * np.sin(
                flow * 131.0 - radius * 177.0)
            filaments *= 0.86 + 0.14 * grain
            brightness = maps["brightness"] * filaments
            disk = np.empty((len(radius), 3), dtype=np.float32)
            disk[:, 0] = brightness * 1.65
            disk[:, 1] = brightness * maps["green_heat"]
            disk[:, 2] = brightness * maps["blue_heat"]
            disk += maps["disk_ring"]
            pixels[hit] = np.clip((1.0 - np.exp(-disk)) * 255.0, 0, 255).astype(np.uint8)
        surface = pygame.surfarray.make_surface(np.transpose(pixels, (1, 0, 2)))
        if surface.get_size() != (self.width, self.height):
            surface = pygame.transform.scale(surface, (self.width, self.height))

        light = np.maximum(pixels.astype(np.int16) - 108, 0).astype(np.uint8)
        light_surface = pygame.surfarray.make_surface(np.transpose(light, (1, 0, 2)))
        glow = pygame.transform.smoothscale(light_surface,
                                            (max(32, self.width // 22),
                                             max(20, self.height // 22)))
        glow = pygame.transform.smoothscale(glow, (self.width, self.height))
        glow.set_alpha(70)
        surface.blit(glow, (0, 0), special_flags=pygame.BLEND_RGB_ADD)
        return surface

    def _trace(self, camera, width: int, height: int) -> dict:
        started = clock.perf_counter()
        shape = (height, width)
        count = width * height
        focal = height / (2.0 * math.tan(float(camera.fov) * 0.5))
        sx, sy = np.meshgrid((np.arange(width, dtype=np.float32) + 0.5 - width / 2) / focal,
                             (height / 2 - np.arange(height, dtype=np.float32) - 0.5) / focal)
        directions = (np.asarray(camera.forward, np.float32)[None, :]
                      + sx.reshape(-1, 1) * np.asarray(camera.right, np.float32)
                      + sy.reshape(-1, 1) * np.asarray(camera.up, np.float32))
        directions /= np.linalg.norm(directions, axis=1)[:, None]
        observer = np.asarray(camera.position, np.float32)
        distance = float(np.linalg.norm(observer))
        radial_basis = observer / distance
        tangent = directions - (directions @ radial_basis)[:, None] * radial_basis
        tangent_length = np.linalg.norm(tangent, axis=1)
        plane_basis = tangent / np.maximum(tangent_length[:, None], 1e-8)
        impact = distance * tangent_length
        orbit = self._orbit_table(distance)
        b_index = np.clip(impact / orbit["b_step"], 0, orbit["u"].shape[1] - 1.001)
        b_low = b_index.astype(np.int32)
        b_fraction = b_index - b_low.astype(np.float32)

        def sample(angle):
            angle_index = np.clip(angle / orbit["angle_step"],
                                  0, orbit["u"].shape[0] - 1.001)
            a_low = angle_index.astype(np.int32)
            a_fraction = angle_index - a_low.astype(np.float32)
            a = orbit["u"][a_low, b_low] * (1 - b_fraction)
            a += orbit["u"][a_low, b_low + 1] * b_fraction
            b = orbit["u"][a_low + 1, b_low] * (1 - b_fraction)
            b += orbit["u"][a_low + 1, b_low + 1] * b_fraction
            return a + (b - a) * a_fraction

        first_angle = np.mod(np.arctan2(-radial_basis[1], plane_basis[:, 1]), np.pi)
        inverse_radius = sample(first_angle)
        hit = (inverse_radius >= 1 / self.outer_radius) & (inverse_radius <= 1 / self.inner_radius)
        angle = first_angle.copy()
        for winding in (1, 2):
            candidate_angle = first_angle + np.pi * winding
            candidate = sample(candidate_angle)
            valid = (~hit) & (candidate >= 1 / self.outer_radius) & (candidate <= 1 / self.inner_radius)
            inverse_radius[valid] = candidate[valid]
            angle[valid] = candidate_angle[valid]
            hit |= valid
        radii = 1.0 / np.maximum(inverse_radius, 0.001)
        disk_direction = (np.cos(angle)[:, None] * radial_basis
                          + np.sin(angle)[:, None] * plane_basis)
        phis = np.arctan2(disk_direction[:, 2], disk_direction[:, 0])
        derivative = (sample(angle + 0.006) - sample(np.maximum(0, angle - 0.006))) / 0.012
        orbit_tangent = (-np.sin(angle)[:, None] * radial_basis
                         + np.cos(angle)[:, None] * plane_basis)
        observer_direction = derivative[:, None] * disk_direction - inverse_radius[:, None] * orbit_tangent
        observer_direction /= np.maximum(np.linalg.norm(observer_direction, axis=1)[:, None], 1e-8)
        approaching = -np.sin(phis) * observer_direction[:, 0] + np.cos(phis) * observer_direction[:, 2]
        dopplers = 1.0 + 0.36 * approaching
        escape = orbit["escape"][b_low] * (1 - b_fraction) + orbit["escape"][b_low + 1] * b_fraction
        captured = escape <= 0
        escaped_directions = (np.cos(escape)[:, None] * radial_basis
                              + np.sin(escape)[:, None] * plane_basis)

        shadow = captured & ~hit
        background = self._starfield(escaped_directions, shape)
        background.reshape(-1, 3)[captured | hit] = 0.0
        ring = 0.17 * np.exp(-np.square((impact.reshape(shape) - 2.61) / 0.047))
        ring[hit.reshape(shape)] *= 0.35
        self.shadow_mask = self._resize_mask(shadow.reshape(shape))
        ring_color = np.array((0.65, 0.34, 0.055), np.float32)
        base_pixels = np.clip((1.0 - np.exp(-(background + ring[..., None] * ring_color))) * 255,
                              0, 255).astype(np.uint8)
        disk_radius = radii[hit].astype(np.float32)
        heat = np.clip((7.5 - disk_radius) / 5.0, 0.0, 1.0)
        envelope = (np.clip((disk_radius - self.inner_radius) / 0.40, 0.0, 1.0)
                    * np.clip((self.outer_radius - disk_radius) / 0.70, 0.0, 1.0)
                    * np.power(3.1 / disk_radius, 0.52))
        self.trace_seconds = clock.perf_counter() - started
        return {"background": background, "hit": hit.reshape(shape),
                "radius": radii.reshape(shape), "phi": phis.reshape(shape),
                "doppler": dopplers.reshape(shape), "ring": ring,
                "pixels": base_pixels, "disk_radius": disk_radius,
                "disk_phi": phis[hit].astype(np.float32),
                "rotation": 0.16 + 3.4 / np.power(disk_radius, 1.5),
                "brightness": envelope * np.power(dopplers[hit], 2.1) * 2.9,
                "green_heat": 0.64 + heat * 0.51,
                "blue_heat": 0.055 + heat * 0.29,
                "disk_ring": ring.reshape(-1)[hit, None] * ring_color}

    def _orbit_table(self, distance: float) -> dict:
        if self._orbit_distance is not None and abs(distance - self._orbit_distance) < 0.002:
            return self._orbits
        samples = 3072
        angle_step = 0.012
        steps = 805
        impacts = np.linspace(0, distance * 0.99, samples, dtype=np.float32)
        inverse_radius = np.full(samples, 1 / distance, dtype=np.float32)
        derivative = np.sqrt(np.maximum(1 / np.maximum(impacts, 0.01) ** 2
                                        - 1 / distance ** 2, 0))
        table = np.empty((steps + 1, samples), dtype=np.float32)
        table[0] = inverse_radius
        escape = np.zeros(samples, dtype=np.float32)
        done = np.zeros(samples, dtype=bool)
        half = angle_step * 0.5

        def acceleration(u):
            return 1.5 * u * u - u

        for step in range(1, steps + 1):
            a = acceleration(inverse_radius)
            k2u = derivative + half * a
            k2v = acceleration(inverse_radius + half * derivative)
            k3u = derivative + half * k2v
            k3v = acceleration(inverse_radius + half * k2u)
            k4u = derivative + angle_step * k3v
            k4v = acceleration(inverse_radius + angle_step * k3u)
            next_u = inverse_radius + angle_step / 6 * (derivative + 2 * k2u + 2 * k3u + k4u)
            next_v = derivative + angle_step / 6 * (a + 2 * k2v + 2 * k3v + k4v)
            escaped = (~done) & (next_u <= 0)
            escape[escaped] = ((step - 1) + inverse_radius[escaped]
                               / (inverse_radius[escaped] - next_u[escaped])) * angle_step
            swallowed = next_u >= 1.02
            done |= escaped | swallowed
            inverse_radius = np.clip(next_u, 0, 1.04)
            derivative = np.where(done, 0.0, next_v)
            table[step] = inverse_radius
        self._orbit_distance = distance
        self._orbits = {"u": table, "escape": escape,
                        "angle_step": angle_step, "b_step": float(impacts[1])}
        return self._orbits

    def _resize_mask(self, mask: np.ndarray) -> np.ndarray:
        if mask.shape == (self.height, self.width):
            return mask
        ys = np.minimum(np.arange(self.height) * mask.shape[0] // self.height,
                        mask.shape[0] - 1)
        xs = np.minimum(np.arange(self.width) * mask.shape[1] // self.width,
                        mask.shape[1] - 1)
        return mask[ys[:, None], xs[None, :]]

    @staticmethod
    def _starfield(directions: np.ndarray, shape: tuple) -> np.ndarray:
        directions = directions / np.linalg.norm(directions, axis=1)[:, None]
        longitude = np.arctan2(directions[:, 2], directions[:, 0]) / (2 * np.pi) + 0.5
        latitude = np.arcsin(np.clip(directions[:, 1], -1, 1)) / np.pi + 0.5
        u = longitude * 660.0
        v = latitude * 330.0
        cx = np.floor(u)
        cy = np.floor(v)
        seed = np.sin(cx * 127.1 + cy * 311.7) * 43758.5453
        seed -= np.floor(seed)
        shift_x = np.sin(cx * 269.5 + cy * 183.3) * 19481.17
        shift_x -= np.floor(shift_x)
        shift_y = np.sin(cx * 419.2 + cy * 371.9) * 17429.39
        shift_y -= np.floor(shift_y)
        distance2 = ((u - cx - 0.2 - shift_x * 0.6) ** 2
                     + (v - cy - 0.2 - shift_y * 0.6) ** 2)
        stars = np.where(seed > 0.985,
                         np.exp(-distance2 / 0.022) * (0.24 + (seed - 0.985) * 17.0), 0)
        haze = (np.sin(longitude * 21.0 + latitude * 13.0) * 0.5 + 0.5)
        rgb = np.empty((len(directions), 3), dtype=np.float32)
        rgb[:, 0] = 0.007 + haze * 0.002 + stars * 0.70
        rgb[:, 1] = 0.011 + haze * 0.003 + stars * 0.77
        rgb[:, 2] = 0.016 + haze * 0.005 + stars * 0.79
        return rgb.reshape((*shape, 3))
