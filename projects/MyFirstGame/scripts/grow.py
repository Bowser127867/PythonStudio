class Grow:
    def start(self):
        print('started')
    
    
    def update(self, dt):
        self.object.scale[0] += 0.5 * dt
        self.object.scale[1] += 0.5 * dt
        self.object.scale[2] += 0.5 * dt


