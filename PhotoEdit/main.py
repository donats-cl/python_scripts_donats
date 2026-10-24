# import numba as nb
import numpy as np
from PIL import Image

def resize(obj: Image, scale: int) -> Image:
    (w, h) = (int(obj.width * scale), int(obj.height * scale))
    return obj.resize((w, h))

def main():
    PHOTO_PATH = './img.jpg'

    img_pil = Image.open(PHOTO_PATH).convert("RGB")

    # h_img, w_img, _ = img.shape

    img_u = resize(img_pil, .4)
    img_u = img_u.resize((img_pil.width, img_pil.height))

    img_b = resize(img_pil, .05)
    img_b = img_b.resize((img_pil.width, img_pil.height))

    img = np.asarray(img_pil).astype(np.float64)
    img_u = np.asarray(img_u).astype(np.float64)
    img_b = np.asarray(img_b).astype(np.float64)

    img_cliped = 2*img_u - img_b #.clip(28, 277)

    img_res = Image.fromarray(img_cliped.clip(0, 255).astype(np.uint8))
    img_res.save('./res.png')

if __name__ == '__main__':
    print("start")
    main()
