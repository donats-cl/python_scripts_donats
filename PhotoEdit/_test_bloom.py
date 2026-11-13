import numpy as np
from PIL import Image

with Image.open("./img1.jpg") as img:
    img_gray: Image.Image = img.convert('L')
    ni: np.ndarray = np.asarray(img_gray, dtype=np.float32)

    k = np.max(ni)*.8

    print(k)
    r = np.where(ni*2 > k, 1, 0)
    r = r[:,:,None] * img

    Image.fromarray(np.clip(r, 0, 255).astype(np.uint8)).save("./img1_o.png")
