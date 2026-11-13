import numpy as np
from PIL import Image

with Image.open("./inp.png") as img:
    a = np.asarray(img, dtype=np.float32)
    b = np.asarray(img.convert("L"), dtype=np.float32)

    c = 2*a-b[:,:,None]

    c = np.clip(c, 0, 255).astype(np.uint8)

    Image.fromarray(c).save("./o.png")
