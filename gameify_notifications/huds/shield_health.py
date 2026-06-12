"""Shared 'shield drains first, then health' damage model for two-bar HUDs
(Halo, GoldenEye).

The capacity is split into a shield share and a health share by `shield_fraction`
(rounded half-up so the odd unit lands on the shield); the shield depletes
ENTIRELY before health starts dropping. Mix into a Hud subclass -- it relies on
the host's capacity()/damage()/tuned() and a `shield_fraction` param."""


class ShieldHealthModel:
    def split(self, capacity, shield_fraction=0.5):
        """Capacity -> (shield_units, health_units), both ints; the odd unit
        rounds toward the shield."""
        n = max(1, int(round(capacity)))
        shield = max(0, min(n, int(n * shield_fraction + 0.5)))
        return shield, n - shield

    def shield_health(self, ctx):
        """-> (shield_units, health_units, shield_remaining, health_remaining) in
        chunk units. Shield drains first; health only once the shield hits 0."""
        shield_units, health_units = self.split(
            self.capacity(ctx), self.tuned(ctx)["shield_fraction"])
        cap = shield_units + health_units
        d = max(0.0, min(float(cap), self.damage(ctx)))
        shield_rem = max(0.0, shield_units - d)
        health_rem = float(health_units) if d <= shield_units else max(0.0, cap - d)
        return shield_units, health_units, shield_rem, health_rem
