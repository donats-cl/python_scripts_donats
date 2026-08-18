import os
import colorsys
import math
import sys
import numpy as np

# 1. Automatically check and install Pillow if not present
try:
    from PIL import Image, ImageDraw
except ImportError:
    import subprocess
    print("Pillow library not found. Installing Pillow...")
    try:
        subprocess.check_call([sys.executable, "-m", "pip", "install", "Pillow"])
        from PIL import Image, ImageDraw
        print("Pillow installed successfully.")
    except Exception as e:
        print(f"Error installing Pillow: {e}")
        sys.exit(1)

# 2. Automatically check and install Numba if not present
try:
    import numba
    from numba import njit
except ImportError:
    import subprocess
    print("Numba library not found. Installing Numba...")
    try:
        subprocess.check_call([sys.executable, "-m", "pip", "install", "numba"])
        import numba
        from numba import njit
        print("Numba installed successfully.")
    except Exception as e:
        print(f"Error installing Numba: {e}")
        sys.exit(1)

# Numba-optimized function to generate radial gradient, rhombus mask, and border in one pass
@njit
def make_perk_bg_numba(w, h, center_r, center_g, center_b, edge_r, edge_g, edge_b, pad, border_width):
    arr = np.zeros((h, w, 4), dtype=np.uint8)
    cx = w / 2.0
    cy = h / 2.0
    max_radius = math.sqrt(cx**2 + cy**2)
    r_rhombus = cx - pad
    
    for y in range(h):
        for x in range(w):
            dx = abs(x - cx)
            dy = abs(y - cy)
            dist_rhombus = dx + dy
            
            if dist_rhombus > r_rhombus:
                # Transparent outside the rhombus
                arr[y, x, 3] = 0
            elif dist_rhombus > r_rhombus - border_width:
                # Black border
                arr[y, x, 0] = 0
                arr[y, x, 1] = 0
                arr[y, x, 2] = 0
                arr[y, x, 3] = 255
            else:
                # Gradient background
                dist_radial = math.sqrt(dx**2 + dy**2)
                factor = dist_radial / max_radius
                if factor > 1.0:
                    factor = 1.0
                t = (1.0 - math.cos(factor * 3.141592653589793)) / 2.0
                
                arr[y, x, 0] = np.uint8(center_r + (edge_r - center_r) * t)
                arr[y, x, 1] = np.uint8(center_g + (edge_g - center_g) * t)
                arr[y, x, 2] = np.uint8(center_b + (edge_b - center_b) * t)
                arr[y, x, 3] = 255
                
    return arr

def adjust_color(r, g, b):
    # Convert RGB to HLS (Hue, Lightness, Saturation)
    h, l, s = colorsys.rgb_to_hls(r/255.0, g/255.0, b/255.0)
    
    # Check if the perk background is chromatic (colored) or achromatic (grey/white)
    is_chromatic = s >= 0.08
    
    if is_chromatic:
        # High saturation (0.85) settings for a vivid, rich color style
        new_l = 0.68
        new_s = 1
        center_l = 0.78
    else:
        # Uniform settings for grey/white perks
        new_l = 0.75
        new_s = 0.0
        center_l = 0.82
    
    # Convert both back to RGB
    r_edge, g_edge, b_edge = colorsys.hls_to_rgb(h, new_l, new_s)
    r_center, g_center, b_center = colorsys.hls_to_rgb(h, center_l, new_s)
    
    edge_color = (int(r_edge * 255), int(g_edge * 255), int(b_edge * 255))
    center_color = (int(r_center * 255), int(g_center * 255), int(b_center * 255))
    
    return edge_color, center_color

def get_bg_color(img):
    w, h = img.size
    # Coordinates near the 4 vertices of the diamond, well inside the border
    # but away from the center icon.
    points = []
    scale = h / 256.0
    offsets = [int(40 * scale), int(45 * scale), int(50 * scale)]
    
    for off in offsets:
        points.extend([
            (w // 2, off),          # near top vertex
            (w // 2, h - 1 - off),  # near bottom vertex
            (off, h // 2),          # near left vertex
            (w - 1 - off, h // 2)   # near right vertex
        ])
        
    valid_colors = []
    for x, y in points:
        pixel = img.getpixel((x, y))
        # Handle RGBA/RGB
        if len(pixel) == 4:
            r, g, b, a = pixel
            if a < 100:  # Skip transparent corners
                continue
        else:
            r, g, b = pixel
            
        # Compute luminance
        lum = 0.299 * r + 0.587 * g + 0.114 * b
        
        # Skip dark border/scratches and bright icon white spots
        if 25 < lum < 235:
            valid_colors.append((r, g, b))
            
    if not valid_colors:
        # Fallback: if all pixels were filtered, take the average of all points directly
        for x, y in points:
            pixel = img.getpixel((x, y))
            valid_colors.append(pixel[:3])
            
    avg_r = sum(c[0] for c in valid_colors) // len(valid_colors)
    avg_g = sum(c[1] for c in valid_colors) // len(valid_colors)
    avg_b = sum(c[2] for c in valid_colors) // len(valid_colors)
    
    return avg_r, avg_g, avg_b

def main():
    clean_dir = "clean_icons"
    dirty_dir = "dirty_textures"
    out_dir = "output_clean_textures"
    
    if not os.path.exists(clean_dir):
        print(f"Error: Directory '{clean_dir}' does not exist.")
        sys.exit(1)
    if not os.path.exists(dirty_dir):
        print(f"Error: Directory '{dirty_dir}' does not exist.")
        sys.exit(1)
        
    os.makedirs(out_dir, exist_ok=True)
    
    processed_count = 0
    skipped_count = 0
    
    # Allowed image file extensions
    valid_exts = ('.png', '.jpg', '.jpeg', '.bmp', '.webp')
    
    print("Starting processing of perk textures (highly saturated rhombus shape with Numba acceleration)...")
    
    for root, dirs, files in os.walk(clean_dir):
        for file in files:
            if not file.lower().endswith(valid_exts):
                continue
                
            clean_path = os.path.join(root, file)
            rel_path = os.path.relpath(clean_path, clean_dir)
            dirty_path = os.path.join(dirty_dir, rel_path)
            
            if not os.path.exists(dirty_path):
                print(f"Warning: Corresponding dirty texture not found for: {rel_path}")
                skipped_count += 1
                continue
                
            try:
                # Open images
                clean_img = Image.open(clean_path).convert("RGBA")
                dirty_img = Image.open(dirty_path).convert("RGBA")
                
                # Robustly extract background color from dirty texture
                avg_r, avg_g, avg_b = get_bg_color(dirty_img)
                
                # Adjust color (returns edge and center colors for gradient)
                edge_color, center_color = adjust_color(avg_r, avg_g, avg_b)
                
                w, h = clean_img.size
                
                # Create gradient, mask, and border using Numba JIT array generator
                pad = w / 32.0
                border_width = max(1.0, w / 50.0)
                
                bg_arr = make_perk_bg_numba(
                    w, h,
                    center_color[0], center_color[1], center_color[2],
                    edge_color[0], edge_color[1], edge_color[2],
                    pad, border_width
                )
                
                # Convert the array to an RGBA Image
                bg_img_rgba = Image.fromarray(bg_arr, "RGBA")
                
                # Paste clean transparent icon in the center
                icon_w, icon_h = clean_img.size
                paste_x = (w - icon_w) // 2
                paste_y = (h - icon_h) // 2
                
                bg_img_rgba.paste(clean_img, (paste_x, paste_y), clean_img)
                
                # Save as PNG
                out_path = os.path.join(out_dir, rel_path)
                out_path_png = os.path.splitext(out_path)[0] + ".png"
                os.makedirs(os.path.dirname(out_path_png), exist_ok=True)
                
                bg_img_rgba.save(out_path_png, "PNG")
                processed_count += 1
                
            except Exception as e:
                print(f"Error processing {rel_path}: {e}")
                skipped_count += 1
                
    print("\nProcessing completed!")
    print(f"Successfully processed: {processed_count} files.")
    print(f"Skipped/failed files: {skipped_count}")

if __name__ == "__main__":
    main()
