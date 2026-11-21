import cv2 as cv


class BinFinder:
    def __init__(self, b: int):
        self.a: int = 0
        self.b: int = b
        self.c: int = int(b / 2)

    def left(self):
        self.b = self.c
        self.c = int((self.a + self.b) / 2)

    def right(self):
        self.a = self.c
        self.c = int((self.a + self.b) / 2)


def save_frame(v: cv.VideoCapture, n: int):
    v.set(cv.CAP_PROP_POS_FRAMES, n)
    r, f = v.read()
    if r:
        cv.imwrite(f"f{n}.png", f)
        print(f"Save f{n}")
    else:
        print("wrong save_frame")


if __name__ == "__main__":
    v: cv.VideoCapture = cv.VideoCapture("o.mkv")

    c: int = int(v.get(cv.CAP_PROP_FRAME_COUNT))
    bf: BinFinder = BinFinder(c)

    for i in range(5):
        print(i)
        save_frame(v, bf.c)
        if i % 2 == 0:
            bf.left()
        else:
            bf.right()

    v.release()
