
class Hero:
    def __init__(self, lvl = 0, bullet_dmg = 0., bullet_dmg_boon = 0., bps = 0., ammo = 0, reload_time = 0., light = 0, light_boon = 0., heavy = 0, heavy_boon = 0., spirit = 0, spirit_boon = 0.):
        # WEaPON
        self.bullet_dmg = bullet_dmg
        self.bps = bps # bullet per sec
        self.ammo = ammo
        self.reload_time = reload_time
        self.light = light
        self.heavy = heavy

        # Green
        # Spirit
        self.spirit = spirit

class Seven(Hero):
    def __init__(self, lvl = 0):
        super().__init__(lvl, 10.8, .24, 5.83, 29, 2.35, 50, 1.58, 116, 3.67, 0, 1.1)
        self.dps = self.bullet_dmg * self.bps
