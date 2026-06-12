class Test:
    def start(self):
        print("i am working currently")
        print(1+1)
                
    def update(self, dt):
        self.object.rotation[1] += 90 * dt
