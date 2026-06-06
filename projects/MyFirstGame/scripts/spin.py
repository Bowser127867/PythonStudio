class SpinScript:
    def start(self):
        print('SpinScript started')

    def update(self, dt):
        self.object.rotation[1] += 90 * dt
