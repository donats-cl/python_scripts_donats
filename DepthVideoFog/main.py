from transformers import pipeline
from time import time
from PIL import Image

m = "depth-anything/Depth-Anything-V2-Small-hf"
# m = "depth-anything/Depth-Anything-V2-Base-hf"
# m = "depth-anything/Depth-Anything-V2-Large-hf"

pipe = pipeline(
    "depth-estimation",
    model=m
)

image = Image.open("i.jpg")

result = pipe(image)
depth = result["depth"]

depth.save("depth_small.png")
